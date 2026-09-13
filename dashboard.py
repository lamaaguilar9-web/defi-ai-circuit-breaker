"""
DeFi AI Circuit Breaker - Multi-Chain Real-Time Guardian Web Dashboard
FastAPI + Tailwind visual command center monitoring BNB Chain, Ethereum,
Arbitrum One, and Solana with interactive multi-chain exploit simulations.
"""

import time
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

from telemetry_sensor import TelemetrySensor
from risk_engine import RiskEngine
from circuit_breaker import CircuitBreaker
from simulate_exploit import simulate_multi_chain_attack

app = FastAPI(title="DeFi AI Multi-Chain Circuit Breaker")

sensor = TelemetrySensor()
engine = RiskEngine()
breaker = CircuitBreaker(sensitivity_threshold=0.82)

current_pool_name = "PancakeSwap_WBNB_USDT"
current_pool_state = sensor.sample_monitored_pool(current_pool_name)
baseline_pool = dict(current_pool_state)
current_eval = engine.evaluate_pool_state(current_pool_state, baseline_pool)
last_incident = None

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DeFi AI Circuit Breaker — Multi-Chain Guardian</title>
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
                        ethblue: '#627eea',
                        arbyellow: '#28a0f0',
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
    <header class="max-w-7xl mx-auto flex flex-col md:flex-row justify-between items-start md:items-center pb-6 border-b border-slate-800 gap-4">
        <div>
            <div class="flex items-center gap-3">
                <span class="text-3xl">🛡️</span>
                <h1 class="text-2xl md:text-3xl font-black tracking-tight text-white">DeFi AI <span class="text-emerald-400">Circuit Breaker</span></h1>
                <span class="text-xs uppercase px-2.5 py-0.5 rounded-full font-bold bg-bnbgold/20 text-bnbgold border border-bnbgold/40">BNB Chain Flagship • Cross-Chain Sentinel</span>
            </div>
            <p class="text-xs md:text-sm text-slate-400 mt-1">Autonomous Sub-45ms Invariant Protection • Native BNB Chain Ecosystem (PancakeSwap & Venus) with Cross-Chain Defense</p>
        </div>

        <div class="flex items-center gap-4">
            <div id="status-pill" class="flex items-center gap-2 px-4 py-2 rounded-xl bg-emerald-950/60 border border-emerald-500/40 text-emerald-300 font-mono text-sm shadow-lg shadow-emerald-950/50">
                <span class="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-live"></span>
                <span id="system-status-text">ARMED & MONITORING</span>
            </div>
        </div>
    </header>

    <main class="max-w-7xl mx-auto mt-8 space-y-6">

        <!-- 4-Chain Telemetry Grid -->
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <!-- BNB Card -->
            <div class="bg-cardbg border border-bnbgold/40 rounded-2xl p-5 shadow-xl shadow-bnbgold/5">
                <div class="flex items-center justify-between text-xs font-bold text-slate-400 uppercase">
                    <span class="flex items-center gap-1.5"><span class="text-bnbgold font-bold">●</span> BNB Chain <span class="text-[10px] bg-bnbgold/20 text-bnbgold px-1.5 py-0.5 rounded font-bold border border-bnbgold/40">FLAGSHIP</span></span>
                    <span id="bnb-status" class="text-emerald-400 font-mono">RPC Active</span>
                </div>
                <div class="mt-3">
                    <div class="text-xs text-slate-400">Block Height</div>
                    <div id="bnb-block" class="text-xl font-mono font-bold text-white mt-0.5">Fetching...</div>
                </div>
                <div class="mt-2 text-xs text-slate-400 flex justify-between">
                    <span>Gas: <span id="bnb-gas" class="text-slate-300 font-mono">--%</span></span>
                    <span>Lat: <span id="bnb-lat" class="text-slate-300 font-mono">--ms</span></span>
                </div>
            </div>

            <!-- Ethereum Card -->
            <div class="bg-cardbg border border-slate-800/80 rounded-2xl p-5 shadow-xl">
                <div class="flex items-center justify-between text-xs font-bold text-slate-400 uppercase">
                    <span class="flex items-center gap-1.5"><span class="text-ethblue font-bold">●</span> Ethereum <span class="text-[10px] bg-slate-800 text-slate-400 px-1.5 py-0.5 rounded">INGRESS FEED</span></span>
                    <span id="eth-status" class="text-emerald-400 font-mono">RPC Active</span>
                </div>
                <div class="mt-3">
                    <div class="text-xs text-slate-400">Block Height</div>
                    <div id="eth-block" class="text-xl font-mono font-bold text-white mt-0.5">Fetching...</div>
                </div>
                <div class="mt-2 text-xs text-slate-400 flex justify-between">
                    <span>Base Fee: <span id="eth-gas" class="text-slate-300 font-mono">-- Gwei</span></span>
                    <span>Lat: <span id="eth-lat" class="text-slate-300 font-mono">--ms</span></span>
                </div>
            </div>

            <!-- Arbitrum Card -->
            <div class="bg-cardbg border border-slate-800/80 rounded-2xl p-5 shadow-xl">
                <div class="flex items-center justify-between text-xs font-bold text-slate-400 uppercase">
                    <span class="flex items-center gap-1.5"><span class="text-arbyellow font-bold">●</span> Arbitrum One <span class="text-[10px] bg-slate-800 text-slate-400 px-1.5 py-0.5 rounded">L2 INGRESS</span></span>
                    <span id="arb-status" class="text-emerald-400 font-mono">Sequencer OK</span>
                </div>
                <div class="mt-3">
                    <div class="text-xs text-slate-400">Nitro Block Height</div>
                    <div id="arb-block" class="text-xl font-mono font-bold text-white mt-0.5">Fetching...</div>
                </div>
                <div class="mt-2 text-xs text-slate-400 flex justify-between">
                    <span>Delay: <span id="arb-gas" class="text-slate-300 font-mono">120ms</span></span>
                    <span>Lat: <span id="arb-lat" class="text-slate-300 font-mono">--ms</span></span>
                </div>
            </div>

            <!-- Solana Card -->
            <div class="bg-cardbg border border-slate-800/80 rounded-2xl p-5 shadow-xl">
                <div class="flex items-center justify-between text-xs font-bold text-slate-400 uppercase">
                    <span class="flex items-center gap-1.5"><span class="text-solpurple font-bold">●</span> Solana <span class="text-[10px] bg-slate-800 text-slate-400 px-1.5 py-0.5 rounded">CROSS-CHAIN</span></span>
                    <span class="text-emerald-400 font-mono">RPC Active</span>
                </div>
                <div class="mt-3">
                    <div class="text-xs text-slate-400">Slot Height</div>
                    <div id="sol-slot" class="text-xl font-mono font-bold text-white mt-0.5">Fetching...</div>
                </div>
                <div class="mt-2 text-xs text-slate-400 flex justify-between">
                    <span>Sentinel Link:</span>
                    <span class="text-emerald-400 font-mono">Port :8000</span>
                </div>
            </div>
        </div>

        <!-- Main Workspace: Pool Selector & Threat Analysis -->
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">

            <!-- Left: Pool Selector & Real-Time Reserves (2 cols) -->
            <div class="lg:col-span-2 bg-cardbg border border-slate-800/80 rounded-2xl p-6 shadow-xl space-y-6">
                <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 border-b border-slate-800 pb-4">
                    <div>
                        <div class="text-xs uppercase font-bold text-slate-400">Target Ecosystem & Protocol</div>
                        <h2 id="current-pool-title" class="text-xl font-black text-white mt-0.5">PancakeSwap_WBNB_USDT (BNB Chain)</h2>
                    </div>
                    <div class="flex items-center gap-2">
                        <label for="pool-select" class="text-xs text-slate-400 font-bold">Switch Pool:</label>
                        <select id="pool-select" onchange="changePool(this.value)" class="bg-slate-900 border border-slate-700 text-slate-200 text-xs rounded-xl px-3 py-2 font-mono focus:outline-none focus:border-emerald-500">
                            <option value="PancakeSwap_WBNB_USDT">[BNB Chain] PancakeSwap v3 (WBNB/USDT)</option>
                            <option value="Venus_Protocol_vBNB">[BNB Chain] Venus Protocol (vBNB Lending)</option>
                            <option value="Uniswap_v3_WETH_USDC">[Ethereum] Uniswap v3 (WETH/USDC)</option>
                            <option value="Aave_v3_WETH_Pool">[Ethereum] Aave v3 (WETH Collateral Pool)</option>
                            <option value="Camelot_WETH_ARB">[Arbitrum One] Camelot DEX (WETH/ARB)</option>
                            <option value="GMX_GLP_Liquidity_Vault">[Arbitrum One] GMX v2 (Multi-Asset Vault)</option>
                        </select>
                    </div>
                </div>

                <!-- Reserve Stats -->
                <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    <div class="bg-slate-900/80 border border-slate-800 p-4 rounded-xl">
                        <div class="text-xs text-slate-400 font-bold">Protected TVL</div>
                        <div id="tvl-usd" class="text-xl font-mono font-bold text-emerald-400 mt-1">$14,500,000.00</div>
                        <div class="text-[10px] text-slate-500 mt-1">Live Invariant Baseline</div>
                    </div>
                    <div class="bg-slate-900/80 border border-slate-800 p-4 rounded-xl">
                        <div class="text-xs text-slate-400 font-bold">Accounting Invariant Law</div>
                        <div id="invariant-type" class="text-sm font-mono font-bold text-white mt-1">AMM_CONSTANT_PRODUCT</div>
                        <div id="invariant-formula" class="text-[10px] text-slate-400 mt-1 font-mono">Δx · Δy ≥ k · (1-fee)²</div>
                    </div>
                    <div class="bg-slate-900/80 border border-slate-800 p-4 rounded-xl">
                        <div class="text-xs text-slate-400 font-bold">Mitigation Latency SLA</div>
                        <div class="text-xl font-mono font-bold text-white mt-1">&lt; 45 ms</div>
                        <div class="text-[10px] text-emerald-400 mt-1">Deterministic Micro-Engine</div>
                    </div>
                </div>

                <!-- Multi-Chain Exploit Simulation Trigger Deck -->
                <div class="border-t border-slate-800 pt-5">
                    <div class="text-xs uppercase font-bold text-slate-400 mb-3">Live Exploit Simulation Deck (Single-Click Reproducibility)</div>
                    <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
                        <button onclick="triggerSimulation('bnb_flashloan')" class="flex flex-col items-center justify-center p-3 rounded-xl bg-amber-950/40 border border-amber-600/40 hover:bg-amber-900/50 hover:border-amber-500 transition-all text-amber-300 font-bold text-xs shadow-lg">
                            <span class="text-base mb-1">⚡ BNB Flash-Loan</span>
                            <span class="text-[10px] text-slate-400 font-mono">$6.7M Drain Attempt</span>
                        </button>
                        <button onclick="triggerSimulation('eth_aave_drain')" class="flex flex-col items-center justify-center p-3 rounded-xl bg-blue-950/40 border border-blue-600/40 hover:bg-blue-900/50 hover:border-blue-500 transition-all text-blue-300 font-bold text-xs shadow-lg">
                            <span class="text-base mb-1">🏛️ ETH Aave Drain</span>
                            <span class="text-[10px] text-slate-400 font-mono">$33M Unbacked Outflow</span>
                        </button>
                        <button onclick="triggerSimulation('arbitrum_sequencer_sandwich')" class="flex flex-col items-center justify-center p-3 rounded-xl bg-sky-950/40 border border-sky-600/40 hover:bg-sky-900/50 hover:border-sky-500 transition-all text-sky-300 font-bold text-xs shadow-lg">
                            <span class="text-base mb-1">🥪 ARB Sandwich Attack</span>
                            <span class="text-[10px] text-slate-400 font-mono">Sequencer Delay Tick Warp</span>
                        </button>
                    </div>
                    <div class="mt-3 flex justify-end">
                        <button onclick="resetSystem()" class="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-bold border border-slate-700 transition-all flex items-center gap-1.5">
                            🔄 Reset All Circuits (Admin Recovery)
                        </button>
                    </div>
                </div>
            </div>

            <!-- Right: Threat Gauge & Real-Time Incident Telemetry (1 col) -->
            <div class="bg-cardbg border border-slate-800/80 rounded-2xl p-6 shadow-xl space-y-6 flex flex-col justify-between">
                <div>
                    <div class="text-xs uppercase font-bold text-slate-400 mb-2">Dynamic Threat Gauge</div>
                    <div class="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 text-center">
                        <div id="threat-pct" class="text-5xl font-mono font-black text-emerald-400 transition-all">0.0%</div>
                        <div id="threat-level" class="text-xs font-mono font-bold text-emerald-300 mt-2 uppercase tracking-wider">NORMAL_SECURE</div>
                    </div>
                </div>

                <!-- Incident Telemetry Card -->
                <div id="incident-box" class="bg-slate-900/90 border border-slate-800 rounded-xl p-4 text-xs font-mono space-y-2">
                    <div class="text-slate-400 font-bold text-[10px] uppercase border-b border-slate-800 pb-1">Emergency Dispatch Telemetry</div>
                    <div class="flex justify-between">
                        <span class="text-slate-400">Action:</span>
                        <span id="inc-action" class="text-slate-300 font-bold">STANDBY</span>
                    </div>
                    <div class="flex justify-between">
                        <span class="text-slate-400">Latency:</span>
                        <span id="inc-latency" class="text-slate-300">-- ms</span>
                    </div>
                    <div>
                        <span class="text-slate-400">Pause Tx Hash:</span>
                        <div id="inc-tx" class="text-slate-500 truncate mt-0.5">--</div>
                    </div>
                </div>

                <div class="text-[10px] text-slate-500 text-center font-mono">
                    Deterministic Invariant Rule: ΔAssets ≥ ΔLiabilities + Margin
                </div>
            </div>
        </div>

    </main>

    <script>
        async function updateTelemetry() {
            try {
                const res = await fetch('/api/telemetry');
                const data = await res.json();
                
                if (data.bnb && data.bnb.block_number) {
                    document.getElementById('bnb-block').innerText = '#' + data.bnb.block_number.toLocaleString();
                    document.getElementById('bnb-gas').innerText = data.bnb.gas_utilization_pct + '%';
                    document.getElementById('bnb-lat').innerText = data.bnb.rpc_latency_ms + 'ms';
                }
                if (data.ethereum && data.ethereum.block_number) {
                    document.getElementById('eth-block').innerText = '#' + data.ethereum.block_number.toLocaleString();
                    document.getElementById('eth-gas').innerText = data.ethereum.base_fee_gwei + ' Gwei';
                    document.getElementById('eth-lat').innerText = data.ethereum.rpc_latency_ms + 'ms';
                }
                if (data.arbitrum && data.arbitrum.block_number) {
                    document.getElementById('arb-block').innerText = '#' + data.arbitrum.block_number.toLocaleString();
                    document.getElementById('arb-lat').innerText = data.arbitrum.rpc_latency_ms + 'ms';
                }
                if (data.solana && data.solana.slot) {
                    document.getElementById('sol-slot').innerText = '#' + data.solana.slot.toLocaleString();
                }
            } catch (e) {
                console.error("Telemetry fetch error:", e);
            }
        }

        async function changePool(poolName) {
            const res = await fetch('/api/pool/' + poolName);
            const data = await res.json();
            document.getElementById('current-pool-title').innerText = data.pool_name + ' (' + data.chain + ')';
            document.getElementById('tvl-usd').innerText = '$' + Number(data.tvl_usd).toLocaleString('en-US', {minimumFractionDigits: 2});
            document.getElementById('invariant-type').innerText = data.protocol_type;
            if (data.protocol_type.includes('LENDING')) {
                document.getElementById('invariant-formula').innerText = 'ΔCollateral ≤ (ΔDebt / Threshold) + ε';
            } else {
                document.getElementById('invariant-formula').innerText = 'Δx · Δy ≥ k · (1 - fee)²';
            }
        }

        async function triggerSimulation(scenario) {
            const res = await fetch('/api/simulate/' + scenario, { method: 'POST' });
            const data = await res.json();

            // Update UI with attack results
            document.getElementById('threat-pct').innerText = data.threat_score_pct + '%';
            document.getElementById('threat-level').innerText = data.threat_level;
            
            // Red alert styling
            document.getElementById('threat-pct').className = 'text-5xl font-mono font-black text-rose-500 transition-all animate-live';
            document.getElementById('threat-level').className = 'text-xs font-mono font-bold text-rose-400 mt-2 uppercase tracking-wider';
            
            const pill = document.getElementById('status-pill');
            pill.className = 'flex items-center gap-2 px-4 py-2 rounded-xl bg-rose-950/80 border border-rose-500 text-rose-300 font-mono text-sm shadow-lg shadow-rose-950/80';
            document.getElementById('system-status-text').innerText = 'CIRCUIT BREAKER TRIPPED';

            document.getElementById('inc-action').innerText = data.action_executed || 'PAUSE_DISPATCHED';
            document.getElementById('inc-action').className = 'text-rose-400 font-bold';
            document.getElementById('inc-latency').innerText = data.mitigation_latency_ms + ' ms';
            document.getElementById('inc-tx').innerText = data.contract_pause_tx_hash;
            document.getElementById('inc-tx').className = 'text-emerald-400 font-mono truncate mt-0.5';
        }

        async function resetSystem() {
            await fetch('/api/reset', { method: 'POST' });
            document.getElementById('threat-pct').innerText = '0.0%';
            document.getElementById('threat-pct').className = 'text-5xl font-mono font-black text-emerald-400 transition-all';
            document.getElementById('threat-level').innerText = 'NORMAL_SECURE';
            document.getElementById('threat-level').className = 'text-xs font-mono font-bold text-emerald-300 mt-2 uppercase tracking-wider';

            const pill = document.getElementById('status-pill');
            pill.className = 'flex items-center gap-2 px-4 py-2 rounded-xl bg-emerald-950/60 border border-emerald-500/40 text-emerald-300 font-mono text-sm shadow-lg shadow-emerald-950/50';
            document.getElementById('system-status-text').innerText = 'ARMED & MONITORING';

            document.getElementById('inc-action').innerText = 'STANDBY';
            document.getElementById('inc-action').className = 'text-slate-300 font-bold';
            document.getElementById('inc-latency').innerText = '-- ms';
            document.getElementById('inc-tx').innerText = '--';
            document.getElementById('inc-tx').className = 'text-slate-500 truncate mt-0.5';
        }

        // Auto-refresh telemetry every 6 seconds
        updateTelemetry();
        setInterval(updateTelemetry, 6000);
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(content=HTML_TEMPLATE)

@app.get("/api/telemetry")
def get_telemetry():
    return sensor.get_all_chains_telemetry()

@app.get("/api/pools")
def get_pools():
    return sensor.list_available_pools()

@app.get("/api/pool/{pool_name}")
def get_pool(pool_name: str):
    return sensor.sample_monitored_pool(pool_name)

@app.post("/api/simulate/{scenario}")
def simulate_attack(scenario: str):
    global last_incident
    res = simulate_multi_chain_attack(scenario)
    last_incident = res
    return res

@app.post("/api/reset")
def reset_breaker():
    global breaker, last_incident
    breaker.reset_circuit()
    last_incident = None
    return {"status": "success", "message": "All multi-chain circuits reset to ARMED_MONITORING"}

@app.get("/api/status")
def get_status():
    return {
        "breaker": breaker.get_status(),
        "latest_incident": last_incident
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5055)
