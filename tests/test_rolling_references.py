"""
Unit Tests for H-9d + H-9e Rolling References (defi-ai-circuit-breaker)
Spec from GLM 5.3 (CANAL_CTO_SPARK.md — SF-RADAR-H9E-11OCT):
1. test_drift_lento_no_dispara - Liquidity drift over 3h does NOT trigger breach.
2. test_cruce_ticks_liquidity_drop_no_alerta (H-9e 6a) - Tick crossing (liquidity -30% with flat price) does NOT alert.
3. test_crash_precio_si_alerta (H-9e 6b) - Price crash >= 15% in 120s DOES trigger breach + alert.
4. test_reinicio_no_enmascara_crash_precio - Fresh sensor restart with price crash >= 15% in 1m DOES trigger breach.
5. test_pool_v2_drenaje_brusco_si_dispara - V2 pool with 30% reserve drain DOES trigger breach.
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

    def test_cruce_ticks_liquidity_drop_no_alerta(self):
        """
        H-9e Test 6a: Cruce de ticks en PancakeSwap v3 (liquidity cae 30% en ventana de 45s con precio plano).
        MUST compute onchain_liquidity_drain_pct as informative metric, but MUST NOT trigger breach or alert.
        """
        start_ts = 1700000000.0
        initial_liq = 10000000
        dropped_liq = 7000000  # 30% tick liquidity drop
        price = 600.0          # Flat price

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

        # Cycle 2: 45s later, sudden 30% tick crossing drop, price remains flat
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

        # Informative metric reflects the in-range tick liquidity change
        self.assertAlmostEqual(pool_c2["onchain_liquidity_drain_pct"], 30.0, places=1)
        self.assertEqual(pool_c2["onchain_price_drop_pct"], 0.0)

        with patch("radar_engine.requests.post") as mock_tg:
            eval_res = self.radar.evaluate_and_alert(pool_c2)
            mock_tg.assert_not_called()

        # In v3 pools, tick liquidity drop alone MUST NOT trigger breach (H-9e mandate)
        self.assertFalse(eval_res["breach_detected"], "Tick crossing with flat price must NOT trigger breach")
        self.assertEqual(eval_res["status"], "NORMAL_SECURE")

    def test_crash_precio_si_alerta(self):
        """
        H-9e Test 6b: Crash de precio >= 15% en 120s en PancakeSwap v3 MUST trigger breach and alert.
        """
        start_ts = 1700000000.0
        initial_liq = 10000000
        price_before = 600.0
        price_after = 492.0  # -18% price crash

        # Baseline established
        mock_c1 = {
            "pool_address": TelemetrySensor.PANCAKESWAP_V3_WBNB_USDT,
            "onchain_verified": True,
            "sqrtPriceX96": 1234567890,
            "tick": -100,
            "liquidity": initial_liq,
            "price_usd": price_before,
            "latency_ms": 15.0,
            "timestamp": start_ts
        }
        with patch("time.time", return_value=start_ts), \
             patch.object(self.sensor, "get_pancakeswap_v3_onchain_state", return_value=mock_c1):
            pool_c1 = self.sensor.sample_monitored_pool("PancakeSwap_WBNB_USDT")

        # Crash 45s later
        ts_c2 = start_ts + 45.0
        mock_c2 = {
            "pool_address": TelemetrySensor.PANCAKESWAP_V3_WBNB_USDT,
            "onchain_verified": True,
            "sqrtPriceX96": 1000000000,
            "tick": -200,
            "liquidity": initial_liq,
            "price_usd": price_after,
            "latency_ms": 15.0,
            "timestamp": ts_c2
        }
        with patch("time.time", return_value=ts_c2), \
             patch.object(self.sensor, "get_pancakeswap_v3_onchain_state", return_value=mock_c2):
            pool_c2 = self.sensor.sample_monitored_pool("PancakeSwap_WBNB_USDT")

        self.assertAlmostEqual(pool_c2["onchain_price_drop_pct"], 18.0, places=1)
        self.assertGreaterEqual(pool_c2["onchain_price_drop_pct"], 15.0)

        with patch("radar_engine.requests.post") as mock_tg:
            mock_tg.return_value.status_code = 200
            with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "mock_token", "TELEGRAM_CHAT_ID": "123456"}):
                eval_res = self.radar.evaluate_and_alert(pool_c2, block_number=42800000)

        self.assertTrue(eval_res["breach_detected"], "Price crash >= 15% MUST trigger breach")
        self.assertEqual(eval_res["status"], "DISPATCHED")
        self.assertIn("incident", eval_res)
        self.assertTrue(any("PRICE_DROP_EXCEEDED" in r for r in eval_res["incident"]["breach_reasons"]))
        self.assertTrue(eval_res["telegram_notified"])

    def test_reinicio_no_enmascara_crash_precio(self):
        """
        H-9d/H-9e Test: Fresh sensor restart experiencing an 18% price crash in 1 minute
        MUST trigger breach despite no older history being present.
        """
        fresh_sensor = TelemetrySensor()
        fresh_sensor.RADAR_REF_WINDOW_SECONDS = 120.0

        ts_start = 1700050000.0
        liq = 8000000
        price_t0 = 600.0
        price_t1 = 492.0  # -18% crash

        # t=0: first sample after restart
        mock_t0 = {
            "pool_address": TelemetrySensor.PANCAKESWAP_V3_WBNB_USDT,
            "onchain_verified": True,
            "sqrtPriceX96": 1234567890,
            "tick": -100,
            "liquidity": liq,
            "price_usd": price_t0,
            "latency_ms": 15.0,
            "timestamp": ts_start
        }
        with patch("time.time", return_value=ts_start), \
             patch.object(fresh_sensor, "get_pancakeswap_v3_onchain_state", return_value=mock_t0):
            pool_t0 = fresh_sensor.sample_monitored_pool("PancakeSwap_WBNB_USDT")

        self.assertEqual(pool_t0["onchain_price_drop_pct"], 0.0)

        # t=60s (1 min later, within 120s window)
        ts_t1 = ts_start + 60.0
        mock_t1 = {
            "pool_address": TelemetrySensor.PANCAKESWAP_V3_WBNB_USDT,
            "onchain_verified": True,
            "sqrtPriceX96": 1000000000,
            "tick": -200,
            "liquidity": liq,
            "price_usd": price_t1,
            "latency_ms": 15.0,
            "timestamp": ts_t1
        }
        with patch("time.time", return_value=ts_t1), \
             patch.object(fresh_sensor, "get_pancakeswap_v3_onchain_state", return_value=mock_t1):
            pool_t1 = fresh_sensor.sample_monitored_pool("PancakeSwap_WBNB_USDT")

        self.assertAlmostEqual(pool_t1["onchain_price_drop_pct"], 18.0, places=1)

        with patch("radar_engine.requests.post") as mock_tg:
            mock_tg.return_value.status_code = 200
            with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "mock_token", "TELEGRAM_CHAT_ID": "123456"}):
                eval_res = self.radar.evaluate_and_alert(pool_t1)

        self.assertTrue(eval_res["breach_detected"], "Price crash after restart within window must trigger breach")
        self.assertEqual(eval_res["status"], "DISPATCHED")

    def test_pool_v2_drenaje_brusco_si_dispara(self):
        """
        In non-concentrated AMM pools (e.g. PancakeSwap v2), reserve drain >= 20% DOES trigger breach.
        """
        v2_pool = {
            "pool_name": "PancakeSwap_v2_WBNB_BUSD",
            "chain": "BNB Chain",
            "protocol": "PancakeSwap v2",
            "address": "0x58F876857a02D6762E0101bb5C46A8c1ED44Dc16",
            "tvl_usd": 7000000.0,
            "onchain_liquidity_drain_pct": 30.0,
            "onchain_price_drop_pct": 2.0,
            "live_price_usd": 590.0,
            "baseline_price_usd": 600.0
        }

        with patch("radar_engine.requests.post") as mock_tg:
            mock_tg.return_value.status_code = 200
            with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "mock_token", "TELEGRAM_CHAT_ID": "123456"}):
                eval_res = self.radar.evaluate_and_alert(v2_pool)

        self.assertTrue(eval_res["breach_detected"])
        self.assertEqual(eval_res["status"], "DISPATCHED")
        self.assertTrue(any("DRAIN_EXCEEDED" in r for r in eval_res["incident"]["breach_reasons"]))


if __name__ == "__main__":
    unittest.main()
