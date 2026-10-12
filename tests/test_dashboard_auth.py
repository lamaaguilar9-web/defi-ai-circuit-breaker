"""
Unit Tests for K-1 Security Mandate (defi-ai-circuit-breaker)
Spec from GLM 5.3 (CANAL_CTO_SPARK.md — SF-DEFI-DASH-K1-11OCT):
1. HTML servido NUNCA contiene el token real ni placeholders sensibles.
2. Fail-closed: Si SENTINEL_ADMIN_KEY no está definida -> 403 en los 3 endpoints privilegiados (jamás abiertos).
3. Comparación segura constante-en-tiempo (hmac.compare_digest).
4. Acceso autorizado exitoso con token válido.
"""

import unittest
import os
import sys
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

# Ensure project root is in sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import dashboard


class TestDashboardK1Auth(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(dashboard.app)

    def test_01_html_served_never_contains_admin_token(self):
        """K-1 (b, d): GET / serves HTML that NEVER leaks SENTINEL_ADMIN_KEY or template placeholders."""
        secret_token = "SUPER_SECRET_SENTINEL_ADMIN_KEY_ABC987654321"
        with patch.dict(os.environ, {"SENTINEL_ADMIN_KEY": secret_token}):
            resp = self.client.get("/")
            self.assertEqual(resp.status_code, 200)
            html_text = resp.text

            # Assert secret token is NOT leaked into served HTML source
            self.assertNotIn(secret_token, html_text, "CRITICAL: Real admin token leaked inside served HTML source")
            self.assertNotIn("{{SENTINEL_ADMIN_KEY_INJECTED}}", html_text, "Unrendered placeholder found in HTML")
            self.assertNotIn(f'const AUTH_TOKEN = "{secret_token}"', html_text)

    def test_02_fail_closed_without_env_returns_403_x3(self):
        """K-1 (a, d): When SENTINEL_ADMIN_KEY is not defined (or empty), all 3 endpoints MUST return 403 (never fail-open)."""
        env_without_key = dict(os.environ)
        env_without_key.pop("SENTINEL_ADMIN_KEY", None)

        with patch.dict(os.environ, env_without_key, clear=True):
            # 1. /api/simulate/{scenario}
            resp_sim = self.client.post("/api/simulate/flash_loan")
            self.assertEqual(resp_sim.status_code, 403, "simulate failed-open when SENTINEL_ADMIN_KEY was absent")
            self.assertIn("FORBIDDEN", resp_sim.json().get("error", ""))

            # 2. /api/reset
            resp_reset = self.client.post("/api/reset")
            self.assertEqual(resp_reset.status_code, 403, "reset failed-open when SENTINEL_ADMIN_KEY was absent")
            self.assertIn("FORBIDDEN", resp_reset.json().get("error", ""))

            # 3. /api/radar/test-alert
            resp_radar = self.client.post("/api/radar/test-alert")
            self.assertEqual(resp_radar.status_code, 403, "radar test-alert failed-open when SENTINEL_ADMIN_KEY was absent")
            self.assertIn("FORBIDDEN", resp_radar.json().get("error", ""))

    def test_03_invalid_auth_token_rejected_with_403(self):
        """K-1 (a): With SENTINEL_ADMIN_KEY configured, invalid or missing credentials return 403."""
        with patch.dict(os.environ, {"SENTINEL_ADMIN_KEY": "valid_secret_key_123"}):
            # Missing auth header
            resp = self.client.post("/api/simulate/oracle_manipulation")
            self.assertEqual(resp.status_code, 403)

            # Wrong key in X-Sentinel-Auth
            resp = self.client.post("/api/reset", headers={"X-Sentinel-Auth": "wrong_key_attacker"})
            self.assertEqual(resp.status_code, 403)

            # Wrong key in Authorization: Bearer
            resp = self.client.post("/api/radar/test-alert", headers={"Authorization": "Bearer fake_token"})
            self.assertEqual(resp.status_code, 403)

    def test_04_valid_auth_token_accepted_x_sentinel_auth(self):
        """K-1: Valid key in X-Sentinel-Auth header grants access to privileged endpoints."""
        valid_key = "secure_operator_token_555"
        with patch.dict(os.environ, {"SENTINEL_ADMIN_KEY": valid_key}):
            with patch.object(dashboard.radar, "send_test_alert") as mock_test_alert:
                mock_test_alert.return_value = {"status": "TEST_ALERT_DISPATCHED", "radar_mode": "SOLO_LECTURA"}

                # /api/radar/test-alert
                resp = self.client.post(
                    "/api/radar/test-alert",
                    headers={"X-Sentinel-Auth": valid_key}
                )
                self.assertEqual(resp.status_code, 200)

                # /api/reset
                resp = self.client.post(
                    "/api/reset",
                    headers={"X-Sentinel-Auth": valid_key}
                )
                self.assertEqual(resp.status_code, 200)

                # /api/simulate
                with patch("dashboard.simulate_multi_chain_attack") as mock_sim:
                    mock_sim.return_value = {"status": "ATTACK_SIMULATED", "threat_score": 0.95}
                    resp = self.client.post(
                        "/api/simulate/flash_loan",
                        headers={"X-Sentinel-Auth": valid_key}
                    )
                    self.assertEqual(resp.status_code, 200)

    def test_05_valid_auth_token_accepted_bearer_header(self):
        """K-1: Valid key in Authorization: Bearer header grants access to privileged endpoints."""
        valid_key = "secure_operator_token_777"
        with patch.dict(os.environ, {"SENTINEL_ADMIN_KEY": valid_key}):
            with patch.object(dashboard.radar, "send_test_alert") as mock_test_alert:
                mock_test_alert.return_value = {"status": "TEST_ALERT_DISPATCHED", "radar_mode": "SOLO_LECTURA"}

                resp = self.client.post(
                    "/api/radar/test-alert",
                    headers={"Authorization": f"Bearer {valid_key}"}
                )
                self.assertEqual(resp.status_code, 200)

    def test_06_non_ascii_header_rejected_with_403_no_type_error(self):
        """M1 Fix: Non-ASCII characters in auth header return False without TypeError."""
        with patch.dict(os.environ, {"SENTINEL_ADMIN_KEY": "valid_key_ascii_123"}):
            mock_request = MagicMock()
            mock_request.headers.get.side_effect = lambda k, default="": "clave_\xe9_invalida" if k == "x-sentinel-auth" else default
            result = dashboard.verify_admin_auth(mock_request)
            self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
