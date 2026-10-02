"""
Unit and Integration Tests for Radar "Modo Sombra" v1 (defi-ai-circuit-breaker)
Tests passive surveillance thresholds, Telegram anti-spam, config catalog, and append-only evidence.
"""

import unittest
import os
import sys
import json
import time
import tempfile
import shutil
from unittest.mock import patch, MagicMock

# Ensure project root is in sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from radar_engine import (
    RadarModoSombra,
    COOLDOWN_SECONDS,
    MAX_DAILY_ALERTS,
    DRAIN_THRESHOLD_PCT,
    PRICE_DROP_THRESHOLD_PCT
)


class TestRadarModoSombra(unittest.TestCase):
    def setUp(self):
        # Use a temporary directory for incident logs and config during testing
        self.test_dir = tempfile.mkdtemp()
        self.incidents_path = os.path.join(self.test_dir, "radar_incidents.jsonl")
        self.config_path = os.path.join(self.test_dir, "radar_pools.json")

        # Create a mock catalog config
        self.sample_catalog = [
            {
                "pool_name": "PancakeSwap_WBNB_USDT",
                "chain": "BNB Chain",
                "protocol": "PancakeSwap v3",
                "address": "0x36696169C63e42cd08ce11f5deeBbCeBae652050",
                "tvl_usd": 14500000.0,
                "enabled": True
            },
            {
                "pool_name": "Uniswap_v3_WETH_USDC",
                "chain": "Ethereum",
                "protocol": "Uniswap v3",
                "address": "0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640",
                "tvl_usd": 58800000.0,
                "enabled": True
            }
        ]
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.sample_catalog, f)

        self.radar = RadarModoSombra(
            config_path=self.config_path,
            incidents_path=self.incidents_path,
            cooldown_seconds=900,
            max_daily_alerts=20
        )

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_catalog_loaded_from_config(self):
        """AR-2: Pools catalog loaded from JSON config without touching code."""
        pools = self.radar.get_catalog_pools()
        self.assertEqual(len(pools), 2)
        self.assertEqual(pools[0]["pool_name"], "PancakeSwap_WBNB_USDT")
        self.assertEqual(pools[1]["chain"], "Ethereum")

        pool = self.radar.get_pool_by_name("PancakeSwap_WBNB_USDT")
        self.assertIsNotNone(pool)
        self.assertEqual(pool["protocol"], "PancakeSwap v3")

    @patch("radar_engine.requests.post")
    def test_02_breach_detection_on_drain_threshold(self, mock_post):
        """AR-1, AR-4: Invariant breach triggers alert on liquidity drain >= 20%."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        # Set mock Telegram credentials
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "mock_token", "TELEGRAM_CHAT_ID": "123456"}):
            base_pool = {"tvl_usd": 10000000.0, "live_price_usd": 500.0}
            # Drain 25% ($2.5M loss)
            attack_pool = {
                "pool_name": "PancakeSwap_WBNB_USDT",
                "chain": "BNB Chain",
                "protocol": "PancakeSwap v3",
                "address": "0x36696169C63e42cd08ce11f5deeBbCeBae652050",
                "tvl_usd": 7500000.0,
                "onchain_liquidity_drain_pct": 25.0,
                "onchain_price_drop_pct": 5.0,
                "live_price_usd": 475.0,
                "baseline_price_usd": 500.0
            }

            res = self.radar.evaluate_and_alert(attack_pool, base_pool, block_number=42718950)
            self.assertTrue(res["breach_detected"])
            self.assertEqual(res["status"], "DISPATCHED")
            self.assertTrue(res["telegram_notified"])

            # Verify mock HTTP call contains [RADAR solo lectura] and breach details
            mock_post.assert_called_once()
            call_kwargs = mock_post.call_args[1]
            payload = call_kwargs["json"]
            self.assertIn("[RADAR solo lectura]", payload["text"])
            self.assertIn("PancakeSwap_WBNB_USDT", payload["text"])
            self.assertIn("25.00%", payload["text"])
            self.assertIn("#42718950", payload["text"])

    @patch("radar_engine.requests.post")
    def test_03_breach_detection_on_price_drop_threshold(self, mock_post):
        """AR-1, AR-4: Invariant breach triggers alert on price crash >= 15%."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "mock_token", "TELEGRAM_CHAT_ID": "123456"}):
            base_pool = {"tvl_usd": 10000000.0, "live_price_usd": 600.0}
            # Price drop 18%
            attack_pool = {
                "pool_name": "PancakeSwap_WBNB_USDT",
                "chain": "BNB Chain",
                "protocol": "PancakeSwap v3",
                "address": "0x36696169C63e42cd08ce11f5deeBbCeBae652050",
                "tvl_usd": 9500000.0,
                "onchain_liquidity_drain_pct": 5.0,
                "onchain_price_drop_pct": 18.0,
                "live_price_usd": 492.0,
                "baseline_price_usd": 600.0
            }

            res = self.radar.evaluate_and_alert(attack_pool, base_pool, block_number=42718955)
            self.assertTrue(res["breach_detected"])
            self.assertEqual(res["status"], "DISPATCHED")

    def test_04_normal_state_no_alert(self):
        """AR-4: Normal market fluctuations below thresholds trigger zero alerts."""
        base_pool = {"tvl_usd": 10000000.0, "live_price_usd": 600.0}
        normal_pool = {
            "pool_name": "PancakeSwap_WBNB_USDT",
            "chain": "BNB Chain",
            "protocol": "PancakeSwap v3",
            "tvl_usd": 9800000.0,
            "onchain_liquidity_drain_pct": 2.0,
            "onchain_price_drop_pct": 1.5,
            "live_price_usd": 591.0,
            "baseline_price_usd": 600.0
        }

        res = self.radar.evaluate_and_alert(normal_pool, base_pool, block_number=42718960)
        self.assertFalse(res["breach_detected"])
        self.assertEqual(res["status"], "NORMAL_SECURE")

    @patch("radar_engine.requests.post")
    def test_05_anti_spam_cooldown_per_pool(self, mock_post):
        """AR-3: Cooldown suppresses rapid repeat alerts for the same pool within 15 minutes."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "mock_token", "TELEGRAM_CHAT_ID": "123456"}):
            base_pool = {"tvl_usd": 10000000.0}
            breach_pool = {
                "pool_name": "PancakeSwap_WBNB_USDT",
                "chain": "BNB Chain",
                "tvl_usd": 7000000.0,
                "onchain_liquidity_drain_pct": 30.0,
                "onchain_price_drop_pct": 0.0
            }

            # First breach: Dispatched
            res1 = self.radar.evaluate_and_alert(breach_pool, base_pool, block_number=42718965)
            self.assertEqual(res1["status"], "DISPATCHED")

            # Second immediate breach: Suppressed by 15m cooldown
            res2 = self.radar.evaluate_and_alert(breach_pool, base_pool, block_number=42718966)
            self.assertTrue(res2["breach_detected"])
            self.assertEqual(res2["status"], "SUPPRESSED_COOLDOWN")
            self.assertGreater(res2["remaining_cooldown_seconds"], 800)

            # Different pool: Not suppressed by first pool's cooldown
            diff_pool = {
                "pool_name": "Uniswap_v3_WETH_USDC",
                "chain": "Ethereum",
                "tvl_usd": 30000000.0,
                "onchain_liquidity_drain_pct": 25.0
            }
            res3 = self.radar.evaluate_and_alert(diff_pool, {"tvl_usd": 40000000.0}, block_number=20890000)
            self.assertEqual(res3["status"], "DISPATCHED")

    @patch("radar_engine.requests.post")
    def test_06_anti_spam_daily_quota_limit(self, mock_post):
        """AR-3: Maximum 20 alerts per day cap is strictly enforced."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        # Create radar with 0-second cooldown to test pure daily quota limit
        quota_radar = RadarModoSombra(
            config_path=self.config_path,
            incidents_path=self.incidents_path,
            cooldown_seconds=0,
            max_daily_alerts=20
        )

        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "mock_token", "TELEGRAM_CHAT_ID": "123456"}):
            base_pool = {"tvl_usd": 10000000.0}
            breach_pool = {
                "pool_name": "PancakeSwap_WBNB_USDT",
                "chain": "BNB Chain",
                "tvl_usd": 7000000.0,
                "onchain_liquidity_drain_pct": 30.0
            }

            # Fire 20 alerts
            for i in range(20):
                res = quota_radar.evaluate_and_alert(breach_pool, base_pool, block_number=42718900 + i)
                self.assertEqual(res["status"], "DISPATCHED")

            # 21st alert: Suppressed by daily quota
            res_21 = quota_radar.evaluate_and_alert(breach_pool, base_pool, block_number=42718921)
            self.assertEqual(res_21["status"], "SUPPRESSED_DAILY_QUOTA")
            self.assertEqual(res_21["daily_count"], 20)

    @patch("radar_engine.requests.post")
    def test_07_append_only_incidents_evidence(self, mock_post):
        """AR-5: Incidents written as append-only records to data/radar_incidents.jsonl."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "mock_token", "TELEGRAM_CHAT_ID": "123456"}):
            base_pool = {"tvl_usd": 10000000.0, "live_price_usd": 550.0}
            breach_pool = {
                "pool_name": "PancakeSwap_WBNB_USDT",
                "chain": "BNB Chain",
                "protocol": "PancakeSwap v3",
                "address": "0x36696169C63e42cd08ce11f5deeBbCeBae652050",
                "tvl_usd": 7500000.0,
                "onchain_liquidity_drain_pct": 25.0,
                "onchain_price_drop_pct": 16.0,
                "live_price_usd": 462.0,
                "baseline_price_usd": 550.0
            }

            self.radar.evaluate_and_alert(breach_pool, base_pool, block_number=42718980)

            # Check that file exists and has 1 line
            self.assertTrue(os.path.exists(self.incidents_path))
            with open(self.incidents_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            self.assertEqual(len(lines), 1)

            entry = json.loads(lines[0])
            self.assertEqual(entry["radar_mode"], "SOLO_LECTURA")
            self.assertEqual(entry["pool_name"], "PancakeSwap_WBNB_USDT")
            self.assertEqual(entry["drain_pct"], 25.0)
            self.assertEqual(entry["price_drop_pct"], 16.0)
            self.assertEqual(entry["block_number"], 42718980)
            self.assertFalse(entry["is_test"])

            # Check get_recent_incidents helper
            incidents = self.radar.get_recent_incidents()
            self.assertEqual(len(incidents), 1)
            self.assertEqual(incidents[0]["pool_name"], "PancakeSwap_WBNB_USDT")

    @patch("radar_engine.requests.post")
    def test_08_send_test_alert_pathway(self, mock_post):
        """AR-6: Test alert pathway with [TEST] [RADAR solo lectura] label and incident persistence."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "mock_token", "TELEGRAM_CHAT_ID": "123456"}):
            res = self.radar.send_test_alert(pool_name="PancakeSwap_WBNB_USDT", block_number=42718999)
            self.assertEqual(res["status"], "TEST_ALERT_DISPATCHED")
            self.assertEqual(res["radar_mode"], "SOLO_LECTURA")
            self.assertTrue(res["telegram_notified"])

            # Verify call payload has [TEST] and [RADAR solo lectura]
            call_kwargs = mock_post.call_args[1]
            text = call_kwargs["json"]["text"]
            self.assertIn("[TEST]", text)
            self.assertIn("[RADAR solo lectura]", text)

            # Verify recorded in incidents with is_test == True
            with open(self.incidents_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            last_entry = json.loads(lines[-1])
            self.assertTrue(last_entry["is_test"])
            self.assertEqual(last_entry["breach_reasons"], ["TEST_ALERT_VERIFICATION"])

    def test_09_zero_onchain_actions_solo_lectura(self):
        """AR-4: Radar operates strictly in read-only mode with zero transaction keys."""
        status = self.radar.get_status()
        self.assertEqual(status["radar_mode"], "SOLO_LECTURA")
        self.assertEqual(status["drain_threshold_pct"], 20.0)
        self.assertEqual(status["price_drop_threshold_pct"], 15.0)

        # Confirm no private key attributes exist anywhere on RadarModoSombra
        self.assertFalse(hasattr(self.radar, "private_key"))
        self.assertFalse(hasattr(self.radar, "wallet_address"))
        self.assertFalse(hasattr(self.radar, "signer"))

    def test_10_api_radar_endpoints(self):
        """AR-6: Test dashboard API endpoints /api/radar/status, /api/radar/incidents, /api/radar/test-alert."""
        from fastapi.testclient import TestClient
        import dashboard
        client = TestClient(dashboard.app)

        # GET /api/radar/status
        resp = client.get("/api/radar/status")
        self.assertEqual(resp.status_code, 200)
        status_data = resp.json()
        self.assertEqual(status_data["radar_mode"], "SOLO_LECTURA")
        self.assertEqual(status_data["status"], "ARMED_AND_WATCHING")

        # GET /api/radar/incidents
        resp = client.get("/api/radar/incidents")
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.json(), list)

        # POST /api/radar/test-alert
        with patch.object(dashboard.radar, "send_test_alert") as mock_send:
            mock_send.return_value = {
                "status": "TEST_ALERT_DISPATCHED",
                "radar_mode": "SOLO_LECTURA",
                "pool_name": "PancakeSwap_WBNB_USDT",
                "telegram_notified": True
            }
            resp = client.post("/api/radar/test-alert")
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json()["status"], "TEST_ALERT_DISPATCHED")


if __name__ == "__main__":
    unittest.main()
