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

        # Base Risk Factors
        risk_components = {}

        # Factor 1: Liquidity Drain Velocity (Max 0.45 weight)
        if tvl_delta_pct > 0:
            drain_score = min(1.0, (tvl_delta_pct / self.reserve_drop_threshold)) * 0.45
        else:
            drain_score = 0.0
        risk_components["liquidity_drain_score"] = round(drain_score, 4)

        # Factor 2: Flash Loan Co-occurrence (Max 0.30 weight)
        # If flash loan size is >20% of pool TVL
        if flash_loan_amount > 0 and curr_tvl > 0:
            loan_ratio = flash_loan_amount / curr_tvl
            flash_score = min(1.0, loan_ratio / 0.5) * 0.30
        else:
            flash_score = 0.0
        risk_components["flash_loan_risk"] = round(flash_score, 4)

        # Factor 3: Slippage / Oracle Imbalance (Max 0.15 weight)
        # Slippage > 5% in a single tx is highly anomalous
        slippage_score = min(1.0, max(0.0, (slippage_pct - 0.5) / 5.0)) * 0.15
        risk_components["slippage_anomaly"] = round(slippage_score, 4)

        # Factor 4: Gas War / Front-running Bidding (Max 0.10 weight)
        if gas_multiplier >= self.gas_surge_threshold:
            gas_score = min(1.0, (gas_multiplier - 1.0) / 4.0) * 0.10
        else:
            gas_score = 0.0
        risk_components["mempool_frontrun_risk"] = round(gas_score, 4)

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

    # Scenario 2: Flash loan + 45% sudden pool drain
    drain_trade = {"pool_name": "PancakeSwap_WBNB_USDT", "tvl_usd": 8000000.0} # $6.5M drained
    exploit_ctx = {
        "flash_loan_borrow_usd": 10000000.0,
        "gas_multiplier": 5.2,
        "observed_slippage_pct": 18.4
    }
    res2 = engine.evaluate_pool_state(drain_trade, baseline, exploit_ctx)
    print(f"[Exploit Attack] Threat Score: {res2['threat_score_pct']}% | Level: {res2['threat_level']} | Trip: {res2['should_trip']}")
    print(f"Components: {res2['risk_components']}")
