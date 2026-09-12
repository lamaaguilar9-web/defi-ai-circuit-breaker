"""
DeFi AI Circuit Breaker - Risk & Anomaly Intelligence Engine
Analyzes on-chain state transitions, pool reserve depletion velocity,
flash-loan borrows, and slippage imbalances to compute dynamic Threat Scores.
"""

import time
import math
from typing import Dict, Any, List


class RiskEngine:
    def __init__(self, reserve_drop_threshold: float = 0.15, gas_surge_threshold: float = 3.0):
        # 15% drop in reserves in short window is anomalous
        self.reserve_drop_threshold = reserve_drop_threshold
        # 3x gas surge indicates priority mempool bidding / sandwich attack
        self.gas_surge_threshold = gas_surge_threshold
        self.history: List[Dict[str, Any]] = []

    def evaluate_pool_state(self, current_pool: Dict[str, Any], previous_pool: Dict[str, Any], tx_context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Calculates threat metrics between state snapshots.
        """
        prev_tvl = previous_pool.get("tvl_usd", 1.0)
        curr_tvl = current_pool.get("tvl_usd", 1.0)
        
        # Calculate percentage reserve drop
        tvl_delta_pct = (prev_tvl - curr_tvl) / prev_tvl if prev_tvl > 0 else 0.0
        
        # Contextual metrics
        tx_context = tx_context or {}
        flash_loan_amount = tx_context.get("flash_loan_borrow_usd", 0.0)
        gas_multiplier = tx_context.get("gas_multiplier", 1.0)
        slippage_pct = tx_context.get("observed_slippage_pct", 0.1)
        collateral_outflow = tx_context.get("collateral_outflow_usd", 0.0)
        debt_repaid = tx_context.get("debt_repaid_usd", 0.0)

        # Invariant Accounting Check: (Delta Debt Repaid / Delta Collateral Outflow)
        # Separates legitimate market liquidation cascades from unbacked exploit drains
        invariant_ratio = None
        is_healthy_liquidation = False
        invariant_breached = False

        if collateral_outflow > 50000.0:  # Material collateral withdrawal/liquidation
            invariant_ratio = debt_repaid / collateral_outflow if collateral_outflow > 0 else 0.0
            if invariant_ratio >= 0.65:
                # Legitimate liquidation: debt is extinguished alongside collateral outflow
                is_healthy_liquidation = True
            elif invariant_ratio < 0.08:
                # Invariant breach: collateral leaves with zero/negligible debt extinguished
                invariant_breached = True

        # Base Risk Factors
        risk_components = {}

        # Factor 1: Liquidity Drain Velocity (Max 0.45 weight)
        if tvl_delta_pct > 0:
            if is_healthy_liquidation:
                # Dampen score for legitimate liquidations to avoid false alarms
                drain_score = 0.05
            else:
                drain_score = min(1.0, (tvl_delta_pct / self.reserve_drop_threshold)) * 0.45
        else:
            drain_score = 0.0
        risk_components["liquidity_drain_score"] = round(drain_score, 4)

        # Factor 2: Flash Loan Co-occurrence (Max 0.30 weight)
        if flash_loan_amount > 0 and curr_tvl > 0:
            loan_ratio = flash_loan_amount / curr_tvl
            flash_score = min(1.0, loan_ratio / 0.5) * 0.30
        else:
            flash_score = 0.0
        risk_components["flash_loan_risk"] = round(flash_score, 4)

        # Factor 3: Slippage / Oracle Imbalance (Max 0.15 weight)
        slippage_score = min(1.0, max(0.0, (slippage_pct - 0.5) / 5.0)) * 0.15
        risk_components["slippage_anomaly"] = round(slippage_score, 4)

        # Factor 4: Gas War / Front-running Bidding (Max 0.10 weight)
        if gas_multiplier >= self.gas_surge_threshold:
            gas_score = min(1.0, (gas_multiplier - 1.0) / 4.0) * 0.10
        else:
            gas_score = 0.0
        risk_components["mempool_frontrun_risk"] = round(gas_score, 4)

        # Factor 5: Invariant Accounting Violation (Max 0.35 weight)
        if invariant_breached:
            risk_components["accounting_invariant_breach"] = 0.35
        else:
            risk_components["accounting_invariant_breach"] = 0.0

        # Total Aggregate Threat Score [0.0 - 1.0]
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

        evaluation = {
            "timestamp": time.time(),
            "pool_name": current_pool.get("pool_name", "Unknown"),
            "current_tvl_usd": curr_tvl,
            "tvl_delta_pct": round(tvl_delta_pct * 100, 2),
            "threat_score": round(aggregate_threat_score, 4),
            "threat_score_pct": threat_score_pct,
            "threat_level": threat_level,
            "action_recommended": action_recommended,
            "risk_components": risk_components,
            "accounting_invariant": {
                "ratio": round(invariant_ratio, 4) if invariant_ratio is not None else None,
                "is_healthy_liquidation": is_healthy_liquidation,
                "invariant_breached": invariant_breached
            },
            "should_trip": aggregate_threat_score >= 0.82
        }

        self.history.append(evaluation)
        return evaluation


if __name__ == "__main__":
    print("=== Testing DeFi AI Risk Engine ===")
    engine = RiskEngine()

    # Scenario 1: Normal steady trade
    baseline = {"pool_name": "PancakeSwap_WBNB_USDT", "tvl_usd": 14500000.0}
    normal_trade = {"pool_name": "PancakeSwap_WBNB_USDT", "tvl_usd": 14495000.0}
    res1 = engine.evaluate_pool_state(normal_trade, baseline)
    print(f"[Normal Trade]  Threat Score: {res1['threat_score_pct']}% | Level: {res1['threat_level']} | Trip: {res1['should_trip']}")

    # Scenario 2: Severe market-wide liquidation wave (collateral out, debt repaid)
    # 25% drop in pool reserves, but invariant holds ($0.80 debt repaid per $1 collateral)
    liquid_pool = {"pool_name": "PancakeSwap_WBNB_USDT", "tvl_usd": 10875000.0}
    liquid_ctx = {
        "flash_loan_borrow_usd": 0.0,
        "gas_multiplier": 2.2,
        "observed_slippage_pct": 1.5,
        "collateral_outflow_usd": 3625000.0,
        "debt_repaid_usd": 2900000.0  # Ratio = 0.80 (Healthy liquidation)
    }
    res2 = engine.evaluate_pool_state(liquid_pool, baseline, liquid_ctx)
    print(f"[Market Liquidation] Threat Score: {res2['threat_score_pct']}% | Level: {res2['threat_level']} | Trip: {res2['should_trip']} (False Alarm Prevented)")

    # Scenario 3: Unbacked flash-loan exploit (invariant breached: collateral out, $0 debt repaid)
    drain_trade = {"pool_name": "PancakeSwap_WBNB_USDT", "tvl_usd": 8000000.0} # $6.5M drained
    exploit_ctx = {
        "flash_loan_borrow_usd": 10000000.0,
        "gas_multiplier": 5.2,
        "observed_slippage_pct": 18.4,
        "collateral_outflow_usd": 6500000.0,
        "debt_repaid_usd": 0.0  # Invariant breached: 0% debt repaid
    }
    res3 = engine.evaluate_pool_state(drain_trade, baseline, exploit_ctx)
    print(f"[Exploit Attack] Threat Score: {res3['threat_score_pct']}% | Level: {res3['threat_level']} | Trip: {res3['should_trip']}")
    print(f"Components: {res3['risk_components']}")
    print(f"Invariant:  {res3['accounting_invariant']}")
