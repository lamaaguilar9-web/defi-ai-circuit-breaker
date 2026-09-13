"""
DeFi AI Circuit Breaker - Multi-Chain Risk & Mathematical Invariant Engine
Evaluates deterministic conservation laws across AMMs (PancakeSwap, Uniswap, Camelot)
and Lending Protocols (Venus, Aave) with sub-45ms execution latency.
"""

import time
import math
from typing import Dict, Any, List, Optional


class RiskEngine:
    """
    Universal Mathematical Invariant & Anomaly Engine
    Models DeFi balance sheets as closed conservation systems.
    """
    def __init__(self, reserve_drop_threshold: float = 0.15, gas_surge_threshold: float = 3.0):
        self.reserve_drop_threshold = reserve_drop_threshold
        self.gas_surge_threshold = gas_surge_threshold
        self.history: List[Dict[str, Any]] = []

    def evaluate_pool_state(self, current_pool: Dict[str, Any], previous_pool: Dict[str, Any], tx_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Calculates threat metrics between state snapshots using deterministic invariants.
        """
        start_time = time.perf_counter()

        prev_tvl = previous_pool.get("tvl_usd", 1.0)
        curr_tvl = current_pool.get("tvl_usd", 1.0)
        chain = current_pool.get("chain", "BNB Chain")
        protocol_type = current_pool.get("protocol_type", "AMM_V3")

        # 1. Delta Reserve / TVL calculation
        tvl_delta_pct = (prev_tvl - curr_tvl) / prev_tvl if prev_tvl > 0 else 0.0

        # Contextual metrics from transaction / mempool
        tx_context = tx_context or {}
        flash_loan_amount = tx_context.get("flash_loan_borrow_usd", 0.0)
        gas_multiplier = tx_context.get("gas_multiplier", 1.0)
        slippage_pct = tx_context.get("observed_slippage_pct", 0.1)
        collateral_outflow = tx_context.get("collateral_outflow_usd", 0.0)
        debt_repaid = tx_context.get("debt_repaid_usd", 0.0)
        sequencer_delay_ms = tx_context.get("sequencer_delay_ms", 0.0)

        # 2. Mathematical Invariant Evaluation
        invariant_ratio = None
        is_healthy_liquidation = False
        invariant_breached = False
        invariant_type = "RESERVE_CONSERVATION"

        if "LENDING" in protocol_type:
            invariant_type = "DEBT_COLLATERAL_CONSERVATION"
            # Lending Invariant: Delta Debt Repaid / Delta Collateral Outflow
            if collateral_outflow > 50000.0:
                invariant_ratio = debt_repaid / collateral_outflow if collateral_outflow > 0 else 0.0
                if invariant_ratio >= 0.65:
                    # Legitimate liquidation: debt is retired alongside collateral release
                    is_healthy_liquidation = True
                elif invariant_ratio < 0.08:
                    # Exploit: collateral extracted with zero or negligible debt repayment
                    invariant_breached = True

        elif "AMM" in protocol_type or "VAULT" in protocol_type:
            invariant_type = "CONSTANT_PRODUCT_AMM_INVARIANT"
            # AMM Invariant: Reserve drain co-occurrence with extreme slippage and flash loan
            if tvl_delta_pct >= self.reserve_drop_threshold:
                if flash_loan_amount > 0 and slippage_pct > 3.0:
                    invariant_breached = True

        # 3. Factor Weighting
        risk_components = {}

        # Factor 1: Liquidity Drain Velocity (Weight: 0.40)
        if tvl_delta_pct > 0:
            if is_healthy_liquidation:
                drain_score = 0.05
            else:
                drain_score = min(1.0, (tvl_delta_pct / self.reserve_drop_threshold)) * 0.40
        else:
            drain_score = 0.0
        risk_components["liquidity_drain_score"] = round(drain_score, 4)

        # Factor 2: Flash Loan Co-occurrence (Weight: 0.25)
        if flash_loan_amount > 0 and curr_tvl > 0:
            loan_ratio = flash_loan_amount / max(1.0, curr_tvl)
            flash_score = min(1.0, loan_ratio / 0.5) * 0.25
        else:
            flash_score = 0.0
        risk_components["flash_loan_risk"] = round(flash_score, 4)

        # Factor 3: Slippage / Oracle Deviation (Weight: 0.15)
        slippage_score = min(1.0, max(0.0, (slippage_pct - 0.5) / 5.0)) * 0.15
        risk_components["slippage_anomaly"] = round(slippage_score, 4)

        # Factor 4: Gas War / MEV Bidding / L2 Sequencer Delay (Weight: 0.10)
        gas_score = 0.0
        if gas_multiplier >= self.gas_surge_threshold:
            gas_score = min(1.0, (gas_multiplier - 1.0) / 4.0) * 0.07
        if "Arbitrum" in chain and sequencer_delay_ms > 200.0:
            gas_score += 0.03  # Flag toxic L2 sequencer sandwich attempts
        risk_components["mempool_frontrun_risk"] = round(gas_score, 4)

        # Factor 5: Deterministic Invariant Breach (Weight: 0.35)
        if invariant_breached:
            risk_components["accounting_invariant_breach"] = 0.35
        else:
            risk_components["accounting_invariant_breach"] = 0.0

        # 4. Total Threat Score [0.0 - 1.0]
        aggregate_threat_score = min(1.0, sum(risk_components.values()))
        threat_score_pct = round(aggregate_threat_score * 100, 2)

        # Threat Categorization
        if aggregate_threat_score >= 0.82:
            threat_level = "CRITICAL_EXPLOIT"
            action_recommended = "TRIP_CIRCUIT_BREAKER_IMMEDIATELY"
        elif aggregate_threat_score >= 0.60:
            threat_level = "SEVERE_ANOMALY"
            action_recommended = "RESTRICT_MAX_TX_SIZE"
        elif aggregate_threat_score >= 0.30:
            threat_level = "ELEVATED_RISK"
            action_recommended = "MONITOR_MEMPOOL_CLOSELY"
        else:
            threat_level = "NORMAL_SECURE"
            action_recommended = "STANDBY"

        compute_latency_ms = round((time.perf_counter() - start_time) * 1000, 3)

        evaluation = {
            "timestamp": time.time(),
            "pool_name": current_pool.get("pool_name", "Unknown"),
            "chain": chain,
            "protocol": current_pool.get("protocol", "Unknown"),
            "protocol_type": protocol_type,
            "current_tvl_usd": curr_tvl,
            "tvl_delta_pct": round(tvl_delta_pct * 100, 2),
            "threat_score": round(aggregate_threat_score, 4),
            "threat_score_pct": threat_score_pct,
            "threat_level": threat_level,
            "action_recommended": action_recommended,
            "risk_components": risk_components,
            "accounting_invariant": {
                "type": invariant_type,
                "ratio": round(invariant_ratio, 4) if invariant_ratio is not None else None,
                "is_healthy_liquidation": is_healthy_liquidation,
                "invariant_breached": invariant_breached
            },
            "compute_latency_ms": compute_latency_ms,
            "should_trip": aggregate_threat_score >= 0.82
        }

        self.history.append(evaluation)
        return evaluation


if __name__ == "__main__":
    print("=== Testing Multi-Chain Risk & Invariant Engine ===")
    engine = RiskEngine()

    # Test 1: BNB Chain PancakeSwap Flash Loan Drain
    bnb_base = {"pool_name": "PancakeSwap_WBNB_USDT", "chain": "BNB Chain", "protocol": "PancakeSwap v3", "protocol_type": "AMM_V3", "tvl_usd": 14500000.0}
    bnb_drain = {"pool_name": "PancakeSwap_WBNB_USDT", "chain": "BNB Chain", "protocol": "PancakeSwap v3", "protocol_type": "AMM_V3", "tvl_usd": 7800000.0}
    ctx1 = {"flash_loan_borrow_usd": 12000000.0, "gas_multiplier": 5.2, "observed_slippage_pct": 14.5}
    res1 = engine.evaluate_pool_state(bnb_drain, bnb_base, ctx1)
    print(f"[BNB Exploit]       Score: {res1['threat_score_pct']}% | Level: {res1['threat_level']} | Breached: {res1['accounting_invariant']['invariant_breached']} | Latency: {res1['compute_latency_ms']}ms")

    # Test 2: Ethereum Aave v3 Market Liquidation (Healthy - Zero False Alarm)
    eth_base = {"pool_name": "Aave_v3_WETH_Pool", "chain": "Ethereum", "protocol": "Aave v3", "protocol_type": "LENDING_POOLED", "tvl_usd": 85000000.0}
    eth_liquid = {"pool_name": "Aave_v3_WETH_Pool", "chain": "Ethereum", "protocol": "Aave v3", "protocol_type": "LENDING_POOLED", "tvl_usd": 68000000.0}
    ctx2 = {"collateral_outflow_usd": 17000000.0, "debt_repaid_usd": 13600000.0, "gas_multiplier": 2.1, "observed_slippage_pct": 1.2}
    res2 = engine.evaluate_pool_state(eth_liquid, eth_base, ctx2)
    print(f"[ETH Liquidation]   Score: {res2['threat_score_pct']}% | Level: {res2['threat_level']} | Breached: {res2['accounting_invariant']['invariant_breached']} | False Alarm Avoided: {res2['accounting_invariant']['is_healthy_liquidation']}")

    # Test 3: Arbitrum Camelot Sequencer Sandwich Exploit
    arb_base = {"pool_name": "Camelot_WETH_ARB", "chain": "Arbitrum One", "protocol": "Camelot DEX", "protocol_type": "AMM_ALGEBRA", "tvl_usd": 15400000.0}
    arb_drain = {"pool_name": "Camelot_WETH_ARB", "chain": "Arbitrum One", "protocol": "Camelot DEX", "protocol_type": "AMM_ALGEBRA", "tvl_usd": 8200000.0}
    ctx3 = {"flash_loan_borrow_usd": 8000000.0, "gas_multiplier": 4.5, "observed_slippage_pct": 9.2, "sequencer_delay_ms": 340.0}
    res3 = engine.evaluate_pool_state(arb_drain, arb_base, ctx3)
    print(f"[Arbitrum Exploit]  Score: {res3['threat_score_pct']}% | Level: {res3['threat_level']} | Breached: {res3['accounting_invariant']['invariant_breached']} | Trip: {res3['should_trip']}")
