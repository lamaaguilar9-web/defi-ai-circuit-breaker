import unittest
import sys, os

# Ensure project root is in sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from telemetry_sensor import TelemetrySensor
from risk_engine import RiskEngine
from circuit_breaker import CircuitBreaker


class TestBNBCircuitBreaker(unittest.TestCase):
    def setUp(self):
        self.sensor = TelemetrySensor()
        self.engine = RiskEngine()
        self.breaker = CircuitBreaker()

    def test_01_pancakeswap_v3_flashloan_detection(self):
        base_pool = self.sensor.sample_monitored_pool('PancakeSwap_WBNB_USDT')
        attack_pool = dict(base_pool)
        attack_pool['tvl_usd'] = 7800000.0
        
        tx_context = {
            'flash_loan_borrow_usd': 12500000.0,
            'gas_multiplier': 5.4,
            'observed_slippage_pct': 14.8,
            'attack_type': 'Flash-Loan Price Invariant Breach (PancakeSwap v3)'
        }
        
        eval_res = self.engine.evaluate_pool_state(attack_pool, base_pool, tx_context)
        self.assertEqual(eval_res['threat_level'], 'CRITICAL_EXPLOIT')
        self.assertGreaterEqual(eval_res['threat_score'], 0.82)
        
        breaker_res = self.breaker.process_telemetry(eval_res)
        self.assertEqual(breaker_res['action_executed'], 'BNB CHAIN_GLOBAL_EMERGENCY_PAUSE')
        self.assertEqual(breaker_res['execution_status'], 'PAUSE_DRY_RUN')
        self.assertIsNone(breaker_res['contract_pause_tx_hash'])
        self.assertLess(breaker_res['mitigation_latency_ms'], 45.0)

    def test_02_venus_protocol_oracle_drain(self):
        base_pool = self.sensor.sample_monitored_pool('Venus_Protocol_vBNB')
        attack_pool = dict(base_pool)
        attack_pool['tvl_usd'] = 8200000.0
        
        tx_context = {
            'collateral_outflow_usd': 10000000.0,
            'debt_repaid_usd': 0.0,
            'gas_multiplier': 4.5,
            'observed_slippage_pct': 12.0,
            'attack_type': 'Oracle Manipulation & Unbacked Borrow (Venus Protocol)'
        }
        
        eval_res = self.engine.evaluate_pool_state(attack_pool, base_pool, tx_context)
        self.assertIn(eval_res['threat_level'], ['CRITICAL_EXPLOIT', 'HIGH_VOLATILITY'])
        
        breaker_res = self.breaker.process_telemetry(eval_res)
        # GLM DEFI-C4: In dry-run mode without key, assert tx_hash is None and status is PAUSE_DRY_RUN
        self.assertIsNone(breaker_res['contract_pause_tx_hash'])
        self.assertEqual(breaker_res['execution_status'], 'PAUSE_DRY_RUN')
        self.assertLess(breaker_res['mitigation_latency_ms'], 45.0)

    def test_03_sub_45ms_mitigation_sla(self):
        base_pool = self.sensor.sample_monitored_pool('PancakeSwap_WBNB_USDT')
        attack_pool = dict(base_pool)
        attack_pool['tvl_usd'] = 6000000.0
        tx_context = {'flash_loan_borrow_usd': 20000000.0, 'gas_multiplier': 6.0, 'observed_slippage_pct': 20.0}
        
        eval_res = self.engine.evaluate_pool_state(attack_pool, base_pool, tx_context)
        breaker_res = self.breaker.process_telemetry(eval_res)
        self.assertLessEqual(breaker_res['mitigation_latency_ms'], 45.0)
        self.assertIsNone(breaker_res['contract_pause_tx_hash'])
        self.assertEqual(breaker_res['execution_status'], 'PAUSE_DRY_RUN')


if __name__ == '__main__':
    unittest.main()
