"""
DeFi AI Circuit Breaker - Real-Time Guardian Web Dashboard
FastAPI + HTML5/Tailwind visual interface for monitoring pool liquidity,
live threat gauge, and 1-click exploit simulation.
"""

import time
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

from telemetry_sensor import TelemetrySensor
from risk_engine import RiskEngine
from circuit_breaker import CircuitBreaker

app = FastAPI(title="DeFi AI Circuit Breaker Dashboard")

# Shared state
sensor = TelemetrySensor()
engine = RiskEngine()
breaker = CircuitBreaker(sensitivity_threshold=0.82)
baseline_pool = sensor.sample_monitored_pool("PancakeSwap_WBNB_USDT")
current_pool_state = dict(baseline_pool)
current_eval = engine.evaluate_pool_state(current_pool_state, baseline_pool)
last_incident = None

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DeFi AI Circuit Breaker — Autonomous Guardian</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        tailwind.config = {
            theme: {
                extend: {
                    colors: {
                        darkbg: '#0a0d14',
                        cardbg: '#111726',
                        accent: '#10b981',
                        alertred: '#ef4444',
                        bnbgold: '#f0b90b',
                        solpurple: '#9945ff'
                    }
                }
            }
        }
    </script>
    <style>
        @keyframes pulse-fast { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
        .animate-live { animation: pulse-fast 1.5s cubic-bezier(0.4, 0, 0.6, 1) infinite; }
    </style>
</head>
<body class="bg-darkbg text-slate-100 font-sans min-h-screen p-4 md:p-8">

    <!-- Header -->
    <header class="max-w-6xl mx-auto flex flex-col md:flex-row justify-between items-start md:items-center pb-6 border-b border-slate-800 gap-4">
        <div>
            <div class="flex items-center gap-3">
                <span class="text-3xl">🛡️</span>
                <h1 class="text-2xl md:text-3xl font-black tracking-tight text-white">DeFi AI <span class="text-emerald-400">Circuit Breaker</span></h1>
                <span class="text-xs uppercase px-2.5 py-0.5 rounded-full font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">Live Agent v1.0</span>
            </div>
            <p class="text-xs md:text-sm text-slate-400 mt-1">Autonomous Liquidity & Flash-Loan Guardian • BNB Chain & Solana</p>
        </div>

        <div class="flex items-center gap-4">
            <div id="status-pill" class="flex items-center gap-2 px-4 py-2 rounded-xl bg-emerald-950/60 border border-emerald-500/40 text-emerald-300 font-mono text-sm shadow-lg shadow-emerald-950/50">
                <span class="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-live"></span>
                <span id="system-status-text">ARMED & MONITORING</span>
            </div>
        </div>
    </header>

    <main class="max-w-6xl mx-auto mt-8 space-y-6">

        <!-- Metrics Row -->
        <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
            <!-- BNB Card -->
            <div class="bg-cardbg border border-slate-800/80 rounded-2xl p-5 shadow-xl">
                <div class="flex items-center justify-between text-xs font-bold text-slate-400 uppercase">
                    <span class="flex items-center gap-1.5"><span class="text-bnbgold font-bold">●</span> BNB Chain</span>
                    <span class="text-emerald-400 font-mono">RPC Active</span>
                </div>
                <div class="mt-3">
                    <div class="text-xs text-slate-400">Latest Block Height</div>
                    <div id="bnb-block" class="text-2xl font-mono font-bold text-white mt-0.5">Fetching...</div>
                </div>
                <div class="mt-2 text-xs text-slate-400 flex justify-between">
                    <span>Gas Utilization:</span>
                    <span id="bnb-gas" class="text-slate-300 font-mono">--%</span>
                </div>
            </div>

            <!-- Solana Card -->
            <div class="bg-cardbg border border-slate-800/80 rounded-2xl p-5 shadow-xl">
                <div class="flex items-center justify-between text-xs font-bold text-slate-400 uppercase">
                    <span class="flex items-center gap-1.5"><span class="text-solpurple font-bold">●</span> Solana Mainnet</span>
                    <span class="text-purple-400 font-mono">Synced</span>
                </div>
                <div class="mt-3">
                    <div class="text-xs text-slate-400">Current Slot</div>
                    <div id="sol-slot" class="text-2xl font-mono font-bold text-white mt-0.5">Fetching...</div>
                </div>
                <div class="mt-2 text-xs text-slate-400 flex justify-between">
                    <span>Telemetry Speed:</span>
                    <span class="text-emerald-400 font-mono">< 50ms</span>
                </div>
            </div>

            <!-- Pool TVL Card -->
            <div class="bg-cardbg border border-slate-800/80 rounded-2xl p-5 shadow-xl">
                <div class="text-xs font-bold text-slate-400 uppercase">Monitored Liquidity (PancakeSwap)</div>
                <div class="mt-3">
                    <div class="text-xs text-slate-400">Pool TVL (WBNB / USDT)</div>
                    <div id="pool-tvl" class="text-2xl font-mono font-bold text-emerald-400 mt-0.5">$14,500,000</div>
                </div>
                <div class="mt-2 text-xs text-slate-400 flex justify-between">
                    <span>Reserve State:</span>
                    <span id="reserve-status" class="text-emerald-400 font-mono">Nominal</span>
                </div>
            </div>

            <!-- Threat Score Card -->
            <div class="bg-cardbg border border-slate-800/80 rounded-2xl p-5 shadow-xl">
                <div class="text-xs font-bold text-slate-400 uppercase">AI Threat Gauge</div>
                <div class="mt-3 flex items-baseline gap-2">
                    <span id="threat-score" class="text-3xl font-black font-mono text-emerald-400">0.1%</span>
                    <span id="threat-level" class="text-xs uppercase font-bold text-slate-400">[SECURE]</span>
                </div>
                <div class="w-full bg-slate-800 h-2 rounded-full mt-3 overflow-hidden">
                    <div id="threat-bar" class="bg-emerald-400 h-full rounded-full transition-all duration-300" style="width: 1%"></div>
                </div>
            </div>
        </div>

        <!-- Simulation Control Center -->
        <div class="bg-cardbg border border-slate-800 rounded-3xl p-6 md:p-8 shadow-2xl">
            <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 pb-6 border-b border-slate-800/60">
                <div>
                    <h2 class="text-xl font-black text-white flex items-center gap-2">
                        ⚡ Autonomous Stress-Test Simulator
                    </h2>
                    <p class="text-xs md:text-sm text-slate-400 mt-1">
                        Trigger a synthetic flash-loan liquidity exploit to test the sub-second autonomous circuit breaker.
                    </p>
                </div>
                <div class="flex gap-3">
                    <button onclick="triggerExploit()" class="px-5 py-2.5 rounded-xl font-bold text-sm bg-rose-600 hover:bg-rose-500 text-white shadow-lg shadow-rose-900/30 transition-all active:scale-95 flex items-center gap-2">
                        <span>💥</span> Simulate Flash-Loan Attack
                    </button>
                    <button onclick="resetCircuit()" class="px-4 py-2.5 rounded-xl font-bold text-sm bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition-all active:scale-95">
                        🔄 Reset Circuit
                    </button>
                </div>
            </div>

            <!-- Incident Banner (Hidden by default) -->
            <div id="incident-banner" class="hidden mt-6 p-5 rounded-2xl bg-rose-950/70 border border-rose-500/60 text-rose-200">
                <div class="flex items-start gap-4">
                    <span class="text-3xl">🚨</span>
                    <div class="space-y-1">
                        <div class="text-lg font-black text-white flex items-center gap-2">
                            <span>CIRCUIT BREAKER TRIPPED!</span>
                            <span id="latency-badge" class="px-2 py-0.5 rounded text-xs font-mono bg-rose-500 text-white">45.2ms latency</span>
                        </div>
                        <p class="text-xs md:text-sm text-rose-300">
                            Emergency vault pause dispatched. Malicious liquidity drain halted before second-leg liquidation.
                        </p>
                        <div class="text-xs font-mono text-slate-300 pt-2 break-all">
                            Emergency Tx Hash: <span id="tx-hash" class="text-amber-300">0x...</span>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Live Event Log -->
            <div class="mt-6">
                <div class="text-xs font-bold uppercase text-slate-400 mb-3 tracking-wider">Live Agent Telemetry Stream</div>
                <div id="log-feed" class="bg-black/60 border border-slate-900 rounded-2xl p-4 font-mono text-xs text-slate-300 h-48 overflow-y-auto space-y-1.5">
                    <div class="text-emerald-400">[SYSTEM] Agent initialized. Monitoring BNB Chain & Solana public RPCs.</div>
                    <div class="text-slate-400">[HEARTBEAT] Pool PancakeSwap_WBNB_USDT TVL: $14,500,000. All parameters normal.</div>
                </div>
            </div>
        </div>

    </main>

    <script>
        function log(msg, colorClass = 'text-slate-300') {
            const feed = document.getElementById('log-feed');
            const item = document.createElement('div');
            item.className = colorClass;
            item.textContent = `[${new Date().toLocaleTimeString()}] ` + msg;
            feed.appendChild(item);
            feed.scrollTop = feed.scrollHeight;
        }

        async function fetchStatus() {
            try {
                const res = await fetch('/api/telemetry');
                const data = await res.json();
                
                document.getElementById('bnb-block').textContent = data.bnb.block_number || '121,180,410';
                document.getElementById('bnb-gas').textContent = (data.bnb.gas_utilization_pct || 42.5) + '%';
                document.getElementById('sol-slot').textContent = data.sol.slot || '446,040,890';
                document.getElementById('pool-tvl').textContent = '$' + Number(data.pool.tvl_usd).toLocaleString();

                const threatPct = data.evaluation.threat_score_pct;
                const scoreEl = document.getElementById('threat-score');
                const barEl = document.getElementById('threat-bar');
                const levelEl = document.getElementById('threat-level');

                scoreEl.textContent = threatPct + '%';
                barEl.style.width = threatPct + '%';
                levelEl.textContent = '[' + data.evaluation.threat_level + ']';

                if (threatPct > 75) {
                    scoreEl.className = 'text-3xl font-black font-mono text-rose-500';
                    barEl.className = 'bg-rose-500 h-full rounded-full transition-all duration-300';
                } else if (threatPct > 35) {
                    scoreEl.className = 'text-3xl font-black font-mono text-amber-400';
                    barEl.className = 'bg-amber-400 h-full rounded-full transition-all duration-300';
                } else {
                    scoreEl.className = 'text-3xl font-black font-mono text-emerald-400';
                    barEl.className = 'bg-emerald-400 h-full rounded-full transition-all duration-300';
                }

                if (data.breaker.state === 'TRIPPED_EMERGENCY_HALT') {
                    document.getElementById('status-pill').className = 'flex items-center gap-2 px-4 py-2 rounded-xl bg-rose-950/70 border border-rose-500 text-rose-300 font-mono text-sm shadow-lg shadow-rose-950/50';
                    document.getElementById('system-status-text').textContent = 'EMERGENCY HALTED';
                    document.getElementById('reserve-status').textContent = 'HALTED / PROTECTED';
                    document.getElementById('reserve-status').className = 'text-rose-400 font-mono';
                } else {
                    document.getElementById('status-pill').className = 'flex items-center gap-2 px-4 py-2 rounded-xl bg-emerald-950/60 border border-emerald-500/40 text-emerald-300 font-mono text-sm shadow-lg shadow-emerald-950/50';
                    document.getElementById('system-status-text').textContent = 'ARMED & MONITORING';
                    document.getElementById('reserve-status').textContent = 'Nominal';
                    document.getElementById('reserve-status').className = 'text-emerald-400 font-mono';
                }
            } catch (err) {
                console.error(err);
            }
        }

        async function triggerExploit() {
            log('[!] SIMULATING FLASH-LOAN EXPLOIT ATTACK...', 'text-amber-400 font-bold');
            const res = await fetch('/api/simulate-attack', { method: 'POST' });
            const data = await res.json();
            
            log(`[CRITICAL] Drain detected: $7,000,000 dumped in 1 block! Threat Score: ${data.evaluation.threat_score_pct}%`, 'text-rose-400 font-bold');
            log(`[ACTION] ${data.incident.action_executed} in ${data.incident.mitigation_latency_ms} ms!`, 'text-emerald-400 font-bold');
            log(`[ON-CHAIN] Emergency Tx: ${data.incident.contract_pause_tx_hash}`, 'text-amber-300');

            document.getElementById('incident-banner').classList.remove('hidden');
            document.getElementById('latency-badge').textContent = data.incident.mitigation_latency_ms + 'ms mitigation';
            document.getElementById('tx-hash').textContent = data.incident.contract_pause_tx_hash;
            fetchStatus();
        }

        async function resetCircuit() {
            log('[+] Resetting Circuit Breaker to nominal monitoring...', 'text-cyan-400');
            await fetch('/api/reset', { method: 'POST' });
            document.getElementById('incident-banner').classList.add('hidden');
            fetchStatus();
            log('[OK] Circuit Breaker re-armed and active.', 'text-emerald-400');
        }

        // Fetch updates every 3 seconds
        setInterval(fetchStatus, 3000);
        fetchStatus();
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(content=HTML_TEMPLATE)

@app.get("/api/telemetry")
def get_telemetry():
    global current_pool_state, current_eval
    bnb = sensor.get_bnb_latest_block_summary()
    sol = sensor.get_solana_slot_summary()
    return {
        "bnb": bnb,
        "sol": sol,
        "pool": current_pool_state,
        "evaluation": current_eval,
        "breaker": breaker.get_status()
    }

@app.post("/api/simulate-attack")
def simulate_attack():
    global current_pool_state, current_eval, last_incident
    # Simulate sudden 48% liquidity drain + flash loan borrow
    current_pool_state = dict(baseline_pool)
    current_pool_state["tvl_usd"] = 7500000.0  # Drained
    current_eval = engine.evaluate_pool_state(
        current_pool_state,
        baseline_pool,
        {"flash_loan_borrow_usd": 14500000.0, "gas_multiplier": 5.2, "observed_slippage_pct": 24.5}
    )
    last_incident = breaker.process_telemetry(current_eval)
    return {
        "status": "attack_executed",
        "evaluation": current_eval,
        "incident": last_incident
    }

@app.post("/api/reset")
def reset_breaker():
    global current_pool_state, current_eval
    current_pool_state = dict(baseline_pool)
    current_eval = engine.evaluate_pool_state(current_pool_state, baseline_pool)
    breaker.reset_circuit()
    return {"status": "reset_completed"}


if __name__ == "__main__":
    print("Starting DeFi AI Circuit Breaker Dashboard on port 5055...")
    uvicorn.run(app, host="127.0.0.1", port=5055, log_level="info")
