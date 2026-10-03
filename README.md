<p align="center">
  <img src="assets/logo.svg" alt="DeFi AI Circuit Breaker" width="200"/>
</p>

# 🛡️ DeFi AI Circuit Breaker — BNB Chain Autonomous Guardian

> **Sub-45ms Autonomous On-Chain Exploit Prevention & Emergency Liquidity Halt for BNB Chain (BEP-20).**  
> Dedicated real-time invariant defense for PancakeSwap v3 and Venus Protocol against flash-loan attacks and oracle drains.

[![Telemetry Architecture](https://img.shields.io/badge/Telemetry-Loopback%20127.0.0.1%20Confined-emerald?style=for-the-badge&logo=fastapi)](https://github.com/lamaaguilar9-web/defi-ai-circuit-breaker)
[![Network](https://img.shields.io/badge/Chain-BNB%20Chain%20(BEP--20)-F0B90B?style=for-the-badge&logo=binance)](https://bscscan.com)
[![Watch Demo Video](https://img.shields.io/badge/▶_Watch_Demo_Video-Loom-625df5?style=for-the-badge&logo=loom&logoColor=white)](https://www.loom.com/share/1c2473fc60f2406e91377c5344005d9d)

🛡️ **Telemetry Dashboard:** Confinado a `127.0.0.1:5055` (Acceso seguro exclusivo vía túnel SSH)  
🎥 **Official Video Walkthrough:** [https://www.loom.com/share/1c2473fc60f2406e91377c5344005d9d](https://www.loom.com/share/1c2473fc60f2406e91377c5344005d9d)

---

> [!IMPORTANT]
> **Architecture & Scope Notice:** The canonical Solidity smart contracts are located in the `bnb-invariant-shield` repository (`BNBInvariantShield.sol`). This repository implements the Python autonomous telemetry, risk evaluation, and emergency dispatch agent layer.

---

## 🚀 Overview

In decentralized finance, flash loans and oracle manipulation attacks drain tens of millions of dollars in a single transaction block. Traditional security solutions rely on multi-signature councils or governance time-locks that take hours or days to respond — far too late to preserve user capital.

**DeFi AI Circuit Breaker** introduces the Wall Street "Circuit Breaker" mechanism natively to **BNB Chain (BEP-20)**. It is an autonomous on-chain Guardian Agent that continuously ingests block-level telemetry directly from public BSC JSON-RPC endpoints (`bsc-dataseed.binance.org`).

When an anomalous flash-loan borrowing pattern or abnormal liquidity drain is detected, the Guardian triggers an emergency smart contract pause and mitigation dispatch with an architectural SLA target of **under 45 milliseconds**, halting the attack before secondary arbitrage and liquidation transactions can finalize.

---

## ⚡ Key Highlights & Innovation

- **Sub-45ms Response SLA Target**: Engineered with an architectural SLA target of `< 45ms` (internal Python compute cycle: `< 0.05ms`).
- **BNB Chain Invariant Engine**: Supports Constant Product AMMs ($\Delta x \cdot \Delta y \ge k$ PancakeSwap v3) and Lending Conservation ($\Delta \text{Debt}/\Delta \text{Collateral} \ge 0.65$ Venus Protocol), distinguishing healthy liquidations from unbacked drains.
- **Dedicated Real-Time BSC Telemetry**: Direct block-by-block monitoring of BNB Chain Mainnet block numbers, gas utilization, and live PancakeSwap v3 on-chain `slot0()` calls.
- **Granular vs Global Mitigation**: Dispatches fine-grained asset halts or global emergency pauses (`BNB CHAIN_GLOBAL_EMERGENCY_PAUSE`) with verifiable audit incident logs (zero fabricated hashes).
- **Zero Operating Cost**: Built entirely on top of free public BSC JSON-RPC nodes (`bsc-dataseed.binance.org`). No paid API subscriptions required.
- **Interactive Stress-Test Terminal**: Built-in visual dashboard (FastAPI + Tailwind) allowing protocols and auditors to replay simulated flash-loan exploits and verify mitigation response in real time.

---

## 📊 System Architecture

```
[ Free Public RPC Layer ]
   └── BNB Chain JSON-RPC (bsc-dataseed.binance.org) --> eth_blockNumber, eth_getBlockByNumber, eth_call

           │ (Real-time telemetry streaming)
           ▼
[ telemetry_sensor.py ]
   Extracts live on-chain slot0/liquidity deltas, block heights, and pool baselines.

           │
           ▼
[ risk_engine.py ]
   Calculates Threat Score [0.0 - 1.0]:
   ├── Factor 1: Liquidity Drain Velocity (Max 40% - Weight 0.40)
   ├── Factor 2: Flash Loan Borrow Co-occurrence (Max 25% - Weight 0.25)
   ├── Factor 3: Slippage / Oracle Distortion (Max 15% - Weight 0.15)
   ├── Factor 4: Mempool Priority Gas Surge (Max 10% - Weight 0.10)
   └── Factor 5: Balance-Sheet Invariant Violation (Max 35% - Weight 0.35)

           │ (Threat Score >= 0.82 & Invariant Breached)
           ▼
[ circuit_breaker.py ]
   Autonomous Mitigation Dispatcher:
   ├── Granular Asset Pause vs Global Halt
   ├── Honest PAUSE_DRY_RUN Mode (Zero fabricated hashes)
   ├── Enforces non-custodial invariant defense
   └── Dispatches Incident Audit Logs
```

---

## 🛠️ Quick Start & Local Execution

### 1. Prerequisites
- Python 3.10+
- Dependencies: `requests`, `fastapi`, `uvicorn` (install via `pip install -r requirements.txt`)

### 2. Verify On-Chain Sensor (Live RPC Connection)
```bash
python telemetry_sensor.py
```

### 3. Run the Autonomous Exploit Simulation
```bash
python simulate_exploit.py
```
*Observe the Guardian Agent detecting a 48% pool drain and halting the protocol in < 50ms.*

### 4. Launch the Visual Guardian Dashboard
```bash
python dashboard.py
```
Open your browser at `http://127.0.0.1:5055` to view live telemetry and trigger synthetic flash-loan exploits with 1 click.

---

## 📜 Incident Telemetry Format

When the Circuit Breaker trips, an immutable incident report is generated:

```json
{
  "event": "CIRCUIT_BREAKER_TRIPPED",
  "timestamp": 1726019760.24,
  "pool_name": "PancakeSwap_WBNB_USDT",
  "threat_score": 1.0,
  "threat_level": "CRITICAL_EXPLOIT",
  "mitigation_latency_ms": 0.012,
  "action_executed": "BNB CHAIN_GLOBAL_EMERGENCY_PAUSE",
  "execution_status": "PAUSE_DRY_RUN",
  "contract_pause_tx_hash": null,
  "protected_tvl_usd": 7800000.0
}
```

---

## 🛰️ Radar "Modo Sombra" v1 (Passive Surveillance Engine)

Passive, zero-privilege watcher monitoring public liquidity pools:

- **Strict Read-Only Mode (`SOLO_LECTURA`)**: Zero on-chain actions, zero private key requirements, zero external permissions.
- **Honest Sampling Scope (v1)**: Active real-time surveillance evaluates **PancakeSwap v3 WBNB/USDT** (`0x3669...`) on BSC Mainnet via live on-chain `eth_call` (`slot0`/`liquidity`). The remaining 3 pools (`Uniswap_v3_WETH_USDC`, `Camelot_v3_WETH_USDC`, `Venus_Protocol_vBNB`) are catalog-staged in `config/radar_pools.json` awaiting multi-chain RPC telemetry adapters.
- **Deterministic Telegram Alerts**: Dispatched when `drain >= 20%` or `price_drop >= 15%`, detailing chain, pool address, measured drain%, price drop, estimated catalog TVL baseline, on-chain block height, and timestamp.
- **Persistent Anti-Spam**: 15-minute cooldown per pool (`COOLDOWN_SECONDS = 900`) and a strict 20 alert daily quota (`MAX_DAILY_ALERTS = 20`), both restored automatically from the incident ledger upon service restarts.
- **Append-Only Evidence Ledger**: All detections logged to `data/radar_incidents.jsonl` (git-ignored) providing timestamped proof-of-detection for institutional prospects.
- **REST Endpoints & Verification**:
  - `GET /api/radar/status`: Reports `pools_active_watching` (1) vs `pools_catalog` (4), runtime status, and quota counters.
  - `GET /api/radar/incidents`: Historical breach audit feed.
  - `POST /api/radar/test-alert`: Protected test alert pathway labeled `[TEST] [RADAR solo lectura]` with full journal and Telegram verification.

---

## 🏆 Active Hackathons & Capital Grants
- **BNB Chain Builder Grant ($25,000 USD)** — Formally Submitted & in review with BNB Chain BD Team.
- **CoinMarketCap "Build with CMC" Hackathon ($10,000 USD + $8.4k Pro Grants)** — DoraHacks Track: *AI Agents and Automation*.
- **Solana Guardian Agent** — DoraHacks BUIDL #48631.
- **Binance Agentic AI Challenge** — DoraHacks Submission ID 2381.

---
*Developed by Luis Aguilar & SentinelLab AI.*

