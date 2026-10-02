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

    def test_04_autonomous_onchain_invariant_breach_liquidity(self):
        """GLM DEFI-R-C6: On-chain liquidity drain >= 20% autonomously trips breaker."""
        base_pool = self.sensor.sample_monitored_pool('PancakeSwap_WBNB_USDT')
        attack_pool = dict(base_pool)
        attack_pool['onchain_liquidity_drain_pct'] = 22.5
        attack_pool['tvl_usd'] = round(base_pool['tvl_usd'] * (1.0 - 0.225), 2)
        
        eval_res = self.engine.evaluate_pool_state(attack_pool, base_pool)
        self.assertTrue(eval_res['accounting_invariant']['invariant_breached'])
        self.assertGreaterEqual(eval_res['threat_score'], 0.82)
        self.assertEqual(eval_res['threat_level'], 'CRITICAL_EXPLOIT')
        
        breaker_res = self.breaker.process_telemetry(eval_res)
        self.assertEqual(breaker_res['action_executed'], 'BNB CHAIN_GLOBAL_EMERGENCY_PAUSE')
        self.assertEqual(breaker_res['execution_status'], 'PAUSE_DRY_RUN')
        self.assertIsNone(breaker_res['contract_pause_tx_hash'])

    def test_05_autonomous_onchain_invariant_breach_price(self):
        """GLM DEFI-R-C6: On-chain price drop >= 15% autonomously trips breaker."""
        base_pool = self.sensor.sample_monitored_pool('PancakeSwap_WBNB_USDT')
        attack_pool = dict(base_pool)
        attack_pool['onchain_price_drop_pct'] = 16.2
        
        eval_res = self.engine.evaluate_pool_state(attack_pool, base_pool)
        self.assertTrue(eval_res['accounting_invariant']['invariant_breached'])
        self.assertGreaterEqual(eval_res['threat_score'], 0.82)
        self.assertEqual(eval_res['threat_level'], 'CRITICAL_EXPLOIT')
        
        breaker_res = self.breaker.process_telemetry(eval_res)
        self.assertEqual(breaker_res['action_executed'], 'BNB CHAIN_GLOBAL_EMERGENCY_PAUSE')

    def test_06_catalog_metadata_and_token_ordering(self):
        """GLM DEFI-R-DATA: PancakeSwap token ordering adheres to sorted on-chain addresses."""
        pancake = self.sensor.pools_directory['BNB']['PancakeSwap_WBNB_USDT']
        self.assertEqual(pancake['token0'], 'USDT')
        self.assertEqual(pancake['token1'], 'WBNB')
        self.assertTrue(pancake['token0_address'].lower() < pancake['token1_address'].lower())

    def test_07_real_block_telemetry_fields(self):
        """GLM DEFI-R-UI4: Real block metrics query without static fallbacks."""
        summary = self.sensor.get_bnb_latest_block_summary()
        self.assertIn('block_number', summary)
        self.assertIn('tx_count', summary)
        self.assertIn('gas_utilization_pct', summary)
        self.assertIn('gas_price_gwei', summary)
        if summary.get('status') == 'online':
            self.assertIsInstance(summary['block_number'], int)
            self.assertIsInstance(summary['tx_count'], int)
            self.assertIsInstance(summary['gas_utilization_pct'], float)


if __name__ == '__main__':
    unittest.main()
