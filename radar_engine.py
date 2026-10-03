"""
DeFi AI Circuit Breaker - Radar "Modo Sombra" v1 (Shadow Monitoring Engine)
Read-only surveillance of public liquidity pools with zero on-chain execution.
Dispatches real-time breach alerts to Telegram with anti-spam cooldown and daily quotas.
Stores append-only evidence in data/radar_incidents.jsonl.
"""

import os
import json
import time
import logging
import threading
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("RadarModoSombra")

# Default Constants
DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config", "radar_pools.json")
DEFAULT_INCIDENTS_PATH = os.path.join(os.path.dirname(__file__), "data", "radar_incidents.jsonl")

COOLDOWN_SECONDS = 900       # 15 minutes per pool
MAX_DAILY_ALERTS = 20        # Maximum 20 alerts per UTC day
DRAIN_THRESHOLD_PCT = 20.0   # Drain >= 20%
PRICE_DROP_THRESHOLD_PCT = 15.0 # Price crash >= 15%


class RadarModoSombra:
    """
    Radar 'Modo Sombra' Engine:
    Passive, zero-privilege, read-only pool telemetry watcher.
    """
    def __init__(
        self,
        config_path: str = DEFAULT_CONFIG_PATH,
        incidents_path: str = DEFAULT_INCIDENTS_PATH,
        cooldown_seconds: int = COOLDOWN_SECONDS,
        max_daily_alerts: int = MAX_DAILY_ALERTS
    ):
        self.config_path = config_path
        self.incidents_path = incidents_path
        self.cooldown_seconds = cooldown_seconds
        self.max_daily_alerts = max_daily_alerts

        self._lock = threading.Lock()
        self.cooldowns: Dict[str, float] = {}       # pool_name -> last_alert_time
        self.daily_counts: Dict[str, int] = {}      # YYYY-MM-DD -> count
        self.catalog_cache: List[Dict[str, Any]] = []

        # Ensure storage directory exists
        os.makedirs(os.path.dirname(self.incidents_path), exist_ok=True)

        # Restore daily counts and cooldowns from persistent log (GLM R-3)
        self._init_state_from_log()
        self.load_catalog()

    def _init_state_from_log(self):
        """Restores daily alert quota and pool cooldowns from data/radar_incidents.jsonl across restarts (GLM R-3)."""
        if not os.path.exists(self.incidents_path):
            return
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        count = 0
        restored_cooldowns: Dict[str, float] = {}
        try:
            with open(self.incidents_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        iso = entry.get("iso_time", "")
                        pool = entry.get("pool_name")
                        ts = entry.get("timestamp", 0.0)
                        if not entry.get("is_test", False):
                            if iso.startswith(today_str):
                                count += 1
                            if pool and ts:
                                if pool not in restored_cooldowns or ts > restored_cooldowns[pool]:
                                    restored_cooldowns[pool] = ts
                    except Exception:
                        continue
            with self._lock:
                self.daily_counts[today_str] = count
                self.cooldowns.update(restored_cooldowns)
            logger.info(f"[RADAR solo lectura] Restored {count} active alerts for today ({today_str}) and {len(restored_cooldowns)} pool cooldowns from incident log.")
        except Exception as e:
            logger.warning(f"[RADAR solo lectura] Could not restore state from log: {e}")

    def load_catalog(self) -> List[Dict[str, Any]]:
        """Loads pool catalog from config/radar_pools.json without modifying code."""
        if not os.path.exists(self.config_path):
            logger.warning(f"[RADAR solo lectura] Catalog config not found at {self.config_path}")
            return []
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    with self._lock:
                        self.catalog_cache = data
                    logger.info(f"[RADAR solo lectura] Loaded {len(data)} pools from catalog configuration.")
                    return data
        except Exception as e:
            logger.error(f"[RADAR solo lectura] Failed to load catalog from {self.config_path}: {e}")
        return []

    def get_catalog_pools(self, reload: bool = False) -> List[Dict[str, Any]]:
        if reload or not self.catalog_cache:
            return self.load_catalog()
        return self.catalog_cache

    def get_pool_by_name(self, pool_name: str) -> Optional[Dict[str, Any]]:
        pools = self.get_catalog_pools()
        for p in pools:
            if p.get("pool_name") == pool_name:
                return p
        return None

    def _get_telegram_creds(self) -> tuple[Optional[str], Optional[str]]:
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        return token, chat_id

    def send_telegram_alert(self, text_message: str) -> bool:
        """
        Dispatches alert to Telegram using Bot API.
        Enforces strict zero-credential-leakage policy (reads token solely from environment).
        """
        token, chat_id = self._get_telegram_creds()
        if not token or not chat_id:
            logger.info("[RADAR solo lectura] Telegram alerts disabled (TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not configured).")
            return False

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text_message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        try:
            resp = requests.post(url, json=payload, timeout=6.0)
            if resp.status_code == 200:
                logger.info("[RADAR solo lectura] Telegram alert delivered successfully.")
                return True
            else:
                logger.warning(f"[RADAR solo lectura] Telegram Bot API error HTTP {resp.status_code}: {resp.text}")
                return False
        except Exception as e:
            logger.error(f"[RADAR solo lectura] Telegram network dispatch error: {e}")
            return False

    def evaluate_and_alert(
        self,
        current_pool: Dict[str, Any],
        baseline_pool: Optional[Dict[str, Any]] = None,
        block_number: Optional[int] = None,
        evaluation: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Evaluates pool state against mathematical breach thresholds (drain >= 20% or price drop >= 15%).
        Dispatches rate-limited alerts and writes append-only records to data/radar_incidents.jsonl.
        """
        pool_name = current_pool.get("pool_name", "Unknown_Pool")
        chain = current_pool.get("chain", "BNB Chain")
        protocol = current_pool.get("protocol", "Unknown")
        address = current_pool.get("address") or current_pool.get("pool_address", "0x0000000000000000000000000000000000000000")

        # Compute drain and price metrics
        prev_tvl = (baseline_pool or {}).get("tvl_usd", current_pool.get("tvl_usd", 1.0))
        curr_tvl = current_pool.get("tvl_usd", 1.0)
        tvl_drain_pct = round(((prev_tvl - curr_tvl) / prev_tvl * 100.0), 2) if prev_tvl > 0 else 0.0

        onchain_drain_pct = current_pool.get("onchain_liquidity_drain_pct", 0.0)
        effective_drain_pct = max(tvl_drain_pct, onchain_drain_pct)

        effective_price_drop_pct = current_pool.get("onchain_price_drop_pct", 0.0)

        # Baseline & current price
        price_before = current_pool.get("baseline_price_usd") or (baseline_pool or {}).get("live_price_usd", 0.0)
        price_after = current_pool.get("live_price_usd", 0.0)

        threat_score = (evaluation or {}).get("threat_score", 0.0)
        threat_level = (evaluation or {}).get("threat_level", "NORMAL_SECURE")

        # Breach condition check
        breach_reasons = []
        if effective_drain_pct >= DRAIN_THRESHOLD_PCT:
            breach_reasons.append(f"DRAIN_EXCEEDED_{effective_drain_pct:.2f}%")
        if effective_price_drop_pct >= PRICE_DROP_THRESHOLD_PCT:
            breach_reasons.append(f"PRICE_DROP_EXCEEDED_{effective_price_drop_pct:.2f}%")
        if threat_score >= 0.82 or threat_level == "CRITICAL_EXPLOIT":
            breach_reasons.append(f"THREAT_SCORE_EXPLOIT_{threat_score:.3f}")

        if not breach_reasons:
            return {
                "breach_detected": False,
                "status": "NORMAL_SECURE",
                "pool_name": pool_name,
                "drain_pct": effective_drain_pct,
                "price_drop_pct": effective_price_drop_pct
            }

        now = time.time()
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        iso_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        with self._lock:
            # 1. Check Anti-Spam: Cooldown per pool (15 min)
            last_alert = self.cooldowns.get(pool_name, 0.0)
            if (now - last_alert) < self.cooldown_seconds:
                remaining_s = int(self.cooldown_seconds - (now - last_alert))
                logger.info(
                    f"[RADAR solo lectura] [COOLDOWN] Invariant breach detected in {pool_name} "
                    f"but alert suppressed ({remaining_s}s remaining in 15m cooldown window)."
                )
                return {
                    "breach_detected": True,
                    "status": "SUPPRESSED_COOLDOWN",
                    "pool_name": pool_name,
                    "remaining_cooldown_seconds": remaining_s
                }

            # 2. Check Anti-Spam: Daily Quota (20 alerts)
            current_count = self.daily_counts.get(today_str, 0)
            if current_count >= self.max_daily_alerts:
                logger.warning(
                    f"[RADAR solo lectura] [QUOTA_REACHED] Alert suppressed for {pool_name}: "
                    f"Daily limit of {self.max_daily_alerts} alerts already reached for {today_str}."
                )
                return {
                    "breach_detected": True,
                    "status": "SUPPRESSED_DAILY_QUOTA",
                    "pool_name": pool_name,
                    "daily_count": current_count,
                    "max_daily_alerts": self.max_daily_alerts
                }

            # Reserve quota and update cooldown
            self.cooldowns[pool_name] = now
            self.daily_counts[today_str] = current_count + 1
            new_count = self.daily_counts[today_str]

        # 3. Format Telegram Alert
        reasons_desc = " | ".join(breach_reasons)
        block_desc = f"#{block_number}" if block_number else "Desconocido (RPC caído)"
        msg = (
            f"🛡️ <b>[RADAR solo lectura] INVARIANT BREACH DETECTED</b>\n\n"
            f"• <b>Cadena:</b> {chain}\n"
            f"• <b>Pool:</b> {pool_name} (<code>{address}</code>)\n"
            f"• <b>Protocolo:</b> {protocol}\n"
            f"• <b>Infracción:</b> {reasons_desc}\n"
            f"• <b>Drain Real Medido:</b> {effective_drain_pct:.2f}% (Umbral: ≥{DRAIN_THRESHOLD_PCT}%)\n"
            f"• <b>Caída de Precio:</b> {effective_price_drop_pct:.2f}% (Umbral: ≥{PRICE_DROP_THRESHOLD_PCT}%)\n"
            f"• <b>Precio Antes/Después:</b> ${price_before:,.2f} ➔ ${price_after:,.2f}\n"
            f"• <b>TVL Estimado (Catálogo):</b> ${prev_tvl:,.2f} ➔ ${curr_tvl:,.2f}\n"
            f"• <b>Bloque On-Chain:</b> {block_desc}\n"
            f"• <b>Timestamp:</b> {iso_str}\n"
            f"• <b>Amenaza:</b> {threat_level} (Score: {threat_score * 100:.1f}%)\n"
            f"• <b>Cuota Diaria:</b> {new_count}/{self.max_daily_alerts}\n\n"
            f"<i>[RADAR solo lectura — Cero permisos, cero transacciones on-chain]</i>"
        )

        # 4. Dispatch Telegram Alert
        sent_tg = self.send_telegram_alert(msg)

        # 5. Log to Journal with Timestamp
        logger.warning(
            f"[RADAR solo lectura] [BREACH] Invariant breach detected: Pool={pool_name}, "
            f"Chain={chain}, Drain={effective_drain_pct}%, PriceDrop={effective_price_drop_pct}%, "
            f"Block={block_desc}, TelegramSent={sent_tg}, DailyCount={new_count}/{self.max_daily_alerts}"
        )

        # 6. Append-Only Incident Evidence
        incident_entry = {
            "timestamp": now,
            "iso_time": datetime.now(timezone.utc).isoformat(),
            "radar_mode": "SOLO_LECTURA",
            "is_test": False,
            "pool_name": pool_name,
            "chain": chain,
            "protocol": protocol,
            "address": address,
            "breach_reasons": breach_reasons,
            "drain_pct": effective_drain_pct,
            "price_drop_pct": effective_price_drop_pct,
            "tvl_before_usd_catalog_estimate": prev_tvl,
            "tvl_after_usd_catalog_estimate": curr_tvl,
            "price_before_usd": price_before,
            "price_after_usd": price_after,
            "block_number": block_number,
            "threat_score": threat_score,
            "threat_level": threat_level,
            "telegram_notified": sent_tg
        }
        self._record_incident(incident_entry)

        return {
            "breach_detected": True,
            "status": "DISPATCHED",
            "pool_name": pool_name,
            "telegram_notified": sent_tg,
            "incident": incident_entry
        }

    def send_test_alert(self, pool_name: str = "PancakeSwap_WBNB_USDT", block_number: Optional[int] = None) -> Dict[str, Any]:
        """
        Executes a test alert pathway labeled [TEST] [RADAR solo lectura].
        Outputs directly to journal and dispatches to Telegram to verify end-to-end telemetry.
        """
        pool = self.get_pool_by_name(pool_name) or {
            "pool_name": pool_name,
            "chain": "BNB Chain",
            "protocol": "PancakeSwap v3",
            "address": "0x36696169C63e42cd08ce11f5deeBbCeBae652050"
        }

        now = time.time()
        iso_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        current_count = self.daily_counts.get(today_str, 0)
        block_desc = f"#{block_number}" if block_number else "Desconocido (RPC caído)"

        msg = (
            f"🛡️ <b>[RADAR solo lectura] [TEST] Verificación de Ruta de Alerta</b>\n\n"
            f"• <b>Cadena:</b> {pool.get('chain', 'BNB Chain')}\n"
            f"• <b>Pool:</b> {pool.get('pool_name', pool_name)} (<code>{pool.get('address')}</code>)\n"
            f"• <b>Sensor Status:</b> ONLINE (Monitoreo pasivo en sombra)\n"
            f"• <b>Bloque Actual:</b> {block_desc}\n"
            f"• <b>Timestamp:</b> {iso_str}\n"
            f"• <b>Anti-Spam:</b> Cooldown 15m activo | Cuota diaria: {current_count}/{self.max_daily_alerts}\n"
            f"• <b>Modo:</b> SOLO LECTURA (Cero acciones on-chain)\n\n"
            f"<i>[TEST verificado exitosamente — Centinela DeFi en sombra]</i>"
        )

        sent_tg = self.send_telegram_alert(msg)

        logger.warning(
            f"[RADAR solo lectura] [TEST] Alerta de verificación ejecutada | "
            f"Pool: {pool_name} | Bloque: {block_desc} | "
            f"Telegram: {'DISPATCHED' if sent_tg else 'SKIPPED/NO_TOKEN'}"
        )

        incident_entry = {
            "timestamp": now,
            "iso_time": datetime.now(timezone.utc).isoformat(),
            "radar_mode": "SOLO_LECTURA",
            "is_test": True,
            "pool_name": pool_name,
            "chain": pool.get("chain", "BNB Chain"),
            "protocol": pool.get("protocol", "PancakeSwap v3"),
            "address": pool.get("address", "0x36696169C63e42cd08ce11f5deeBbCeBae652050"),
            "breach_reasons": ["TEST_ALERT_VERIFICATION"],
            "block_number": block_number,
            "telegram_notified": sent_tg,
            "status": "VERIFIED_TEST"
        }
        self._record_incident(incident_entry)

        return {
            "status": "TEST_ALERT_DISPATCHED",
            "radar_mode": "SOLO_LECTURA",
            "pool_name": pool_name,
            "block_number": block_number,
            "telegram_notified": sent_tg,
            "incident": incident_entry
        }

    def _record_incident(self, entry: Dict[str, Any]):
        """Append-only recording of incident evidence to data/radar_incidents.jsonl."""
        try:
            with open(self.incidents_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"[RADAR solo lectura] Failed to append incident to {self.incidents_path}: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Returns runtime status of the Radar Modo Sombra daemon with honest telemetry claims (GLM R-1)."""
        token, chat_id = self._get_telegram_creds()
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        catalog_pools = self.get_catalog_pools()
        active_watching = [p.get("pool_name") for p in catalog_pools if p.get("pool_name") == "PancakeSwap_WBNB_USDT"]
        catalog_names = [p.get("pool_name") for p in catalog_pools]

        return {
            "radar_mode": "SOLO_LECTURA",
            "status": "ARMED_AND_WATCHING",
            "version": "v1.0-shadow",
            "pools_active_watching_count": len(active_watching),
            "pools_active_watching": active_watching,
            "pools_catalog_count": len(catalog_pools),
            "pools_catalog": catalog_names,
            "sampling_scope": "v1 actively streams live on-chain BSC eth_call (slot0/liquidity) for PancakeSwap_WBNB_USDT; remaining catalog pools staged for multi-chain adapters",
            "telegram_configured": bool(token and chat_id),
            "alerts_sent_today": self.daily_counts.get(today_str, 0),
            "max_daily_alerts": self.max_daily_alerts,
            "cooldown_seconds": self.cooldown_seconds,
            "drain_threshold_pct": DRAIN_THRESHOLD_PCT,
            "price_drop_threshold_pct": PRICE_DROP_THRESHOLD_PCT,
            "incidents_log_path": self.incidents_path
        }

    def get_recent_incidents(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Reads recent incidents from data/radar_incidents.jsonl."""
        if not os.path.exists(self.incidents_path):
            return []
        records = []
        try:
            with open(self.incidents_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            records.append(json.loads(line))
                        except Exception:
                            continue
            return records[-limit:][::-1]
        except Exception as e:
            logger.error(f"[RADAR solo lectura] Failed to read incidents: {e}")
            return []
