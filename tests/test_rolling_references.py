"""
Unit Tests for H-9d Rolling References (defi-ai-circuit-breaker)
Spec from G:\\Mi unidad\\PARCHE_H9D_RADAR_REFERENCIAS_RODANTES.md (GLM 5.3):
1. test_drift_lento_no_dispara - Liquidity dropping 25% over 3 hours does NOT trigger breach.
2. test_drenaje_brusco_si_dispara - Sudden 30% drop in <= 2 cycles DOES trigger breach + CRITICAL.
3. test_reinicio_no_enmascara - Fresh instance experiencing 25% drop in 1 min DOES trigger breach.
"""

import unittest
import os
import sys
import time
import tempfile
import shutil
from unittest.mock import patch

# Ensure project root is in sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from telemetry_sensor import TelemetrySensor
from radar_engine import RadarModoSombra


class TestH9dRollingReferences(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.incidents_path = os.path.join(self.test_dir, "radar_incidents.jsonl")
        self.radar = RadarModoSombra(
            incidents_path=self.incidents_path,
            cooldown_seconds=900,
            max_daily_alerts=20
        )
        self.sensor = TelemetrySensor()
        self.sensor.RADAR_REF_WINDOW_SECONDS = 120.0

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_drift_lento_no_dispara(self):
        """
        H-9d Test 1: Liquidity falling 25% spread across 3 hours (~0.28% per 120s cycle)
        MUST NOT trigger invariant breach against rolling window (window=120s).
        """
        start_ts = 1700000000.0
        initial_liq = 10000000  # 10M
        final_liq = 7500000    # 7.5M (-25% total drop over 3h)
        total_steps = 90       # 90 steps * 120s = 10,800s (3 hours)
        step_drop = (initial_liq - final_liq) / total_steps

        current_liq = initial_liq
        price = 600.0

        for i in range(total_steps + 1):
            current_ts = start_ts + (i * 120.0)
            mock_onchain = {
                "pool_address": TelemetrySensor.PANCAKESWAP_V3_WBNB_USDT,
                "onchain_verified": True,
                "sqrtPriceX96": 1234567890,
                "tick": -100,
                "liquidity": int(current_liq),
                "price_usd": price,
                "latency_ms": 15.0,
                "timestamp": current_ts
            }

            with patch("time.time", return_value=current_ts), \
                 patch.object(self.sensor, "get_pancakeswap_v3_onchain_state", return_value=mock_onchain):
                pool = self.sensor.sample_monitored_pool("PancakeSwap_WBNB_USDT")

            # Drain in any single 120s window should be ~0.28%, far below 20%
            self.assertLess(pool["onchain_liquidity_drain_pct"], 20.0,
                            f"Step {i}: drain {pool['onchain_liquidity_drain_pct']}% breached threshold unexpectedly")

            eval_res = self.radar.evaluate_and_alert(pool)
            self.assertFalse(eval_res["breach_detected"],
                             f"Step {i}: breach detected during slow drift")

            current_liq -= step_drop

        # Verify that informative HWM stayed at the historical peak, but didn't trigger false positives
        self.assertEqual(self.sensor.hwm_liquidity, initial_liq)

    def test_drenaje_brusco_si_dispara(self):
        """
        H-9d Test 2: Sudden drop of 30% in <= 2 cycles MUST trigger breach + CRITICAL alert.
        """
        start_ts = 1700000000.0
        initial_liq = 10000000
        dropped_liq = 7000000  # 30% drain
        price = 600.0

        # Cycle 1: baseline established
        mock_c1 = {
            "pool_address": TelemetrySensor.PANCAKESWAP_V3_WBNB_USDT,
            "onchain_verified": True,
            "sqrtPriceX96": 1234567890,
            "tick": -100,
            "liquidity": initial_liq,
            "price_usd": price,
            "latency_ms": 15.0,
            "timestamp": start_ts
        }
        with patch("time.time", return_value=start_ts), \
             patch.object(self.sensor, "get_pancakeswap_v3_onchain_state", return_value=mock_c1):
            pool_c1 = self.sensor.sample_monitored_pool("PancakeSwap_WBNB_USDT")

        self.assertEqual(pool_c1["onchain_liquidity_drain_pct"], 0.0)

        # Cycle 2: 45s later, sudden 30% drain
        ts_c2 = start_ts + 45.0
        mock_c2 = {
            "pool_address": TelemetrySensor.PANCAKESWAP_V3_WBNB_USDT,
            "onchain_verified": True,
            "sqrtPriceX96": 1234567890,
            "tick": -100,
            "liquidity": dropped_liq,
            "price_usd": price,
            "latency_ms": 15.0,
            "timestamp": ts_c2
        }
        with patch("time.time", return_value=ts_c2), \
             patch.object(self.sensor, "get_pancakeswap_v3_onchain_state", return_value=mock_c2):
            pool_c2 = self.sensor.sample_monitored_pool("PancakeSwap_WBNB_USDT")

        self.assertAlmostEqual(pool_c2["onchain_liquidity_drain_pct"], 30.0, places=1)
        self.assertGreaterEqual(pool_c2["onchain_liquidity_drain_pct"], 20.0)

        with patch("radar_engine.requests.post") as mock_tg:
            mock_tg.return_value.status_code = 200
            eval_res = self.radar.evaluate_and_alert(pool_c2)

        self.assertTrue(eval_res["breach_detected"], "Sudden drain must trigger breach")
        self.assertIn("incident", eval_res)
        self.assertTrue(any("DRAIN_EXCEEDED" in r for r in eval_res["incident"]["breach_reasons"]))

    def test_reinicio_no_enmascara(self):
        """
        H-9d Test 3: Fresh sensor restart experiencing a 25% drop in 1 minute
        MUST trigger breach despite no older history being present.
        """
        fresh_sensor = TelemetrySensor()
        fresh_sensor.RADAR_REF_WINDOW_SECONDS = 120.0

        ts_start = 1700050000.0
        liq_t0 = 8000000
        liq_t1 = 6000000  # -25% drop
        price = 550.0

        # t=0: first sample after restart
        mock_t0 = {
            "pool_address": TelemetrySensor.PANCAKESWAP_V3_WBNB_USDT,
            "onchain_verified": True,
            "sqrtPriceX96": 1234567890,
            "tick": -100,
            "liquidity": liq_t0,
            "price_usd": price,
            "latency_ms": 15.0,
            "timestamp": ts_start
        }
        with patch("time.time", return_value=ts_start), \
             patch.object(fresh_sensor, "get_pancakeswap_v3_onchain_state", return_value=mock_t0):
            pool_t0 = fresh_sensor.sample_monitored_pool("PancakeSwap_WBNB_USDT")

        self.assertEqual(pool_t0["onchain_liquidity_drain_pct"], 0.0)

        # t=60s (1 min later, within 120s window)
        ts_t1 = ts_start + 60.0
        mock_t1 = {
            "pool_address": TelemetrySensor.PANCAKESWAP_V3_WBNB_USDT,
            "onchain_verified": True,
            "sqrtPriceX96": 1234567890,
            "tick": -100,
            "liquidity": liq_t1,
            "price_usd": price,
            "latency_ms": 15.0,
            "timestamp": ts_t1
        }
        with patch("time.time", return_value=ts_t1), \
             patch.object(fresh_sensor, "get_pancakeswap_v3_onchain_state", return_value=mock_t1):
            pool_t1 = fresh_sensor.sample_monitored_pool("PancakeSwap_WBNB_USDT")

        self.assertAlmostEqual(pool_t1["onchain_liquidity_drain_pct"], 25.0, places=1)
        self.assertGreaterEqual(pool_t1["onchain_liquidity_drain_pct"], 20.0)

        with patch("radar_engine.requests.post") as mock_tg:
            mock_tg.return_value.status_code = 200
            eval_res = self.radar.evaluate_and_alert(pool_t1)

        self.assertTrue(eval_res["breach_detected"], "25% drain after restart within window must trigger breach")


if __name__ == "__main__":
    unittest.main()
