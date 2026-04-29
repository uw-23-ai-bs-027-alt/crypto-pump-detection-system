"""
alert_system.py
Generates, stores, and retrieves pump-and-dump alerts.
"""

import sqlite3
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "crypto.db")


# ── Generate alerts from anomaly results ──────────────────────────────────────
def generate_alerts(analysis_results: list[dict]) -> list[dict]:
    """
    Takes the output of anomaly_detector.run_full_analysis and
    creates human-readable alert records, saving them to the DB.
    Returns list of new alert dicts.
    """
    new_alerts = []
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    for result in analysis_results:
        if result.get("status") != "ok":
            continue
        coin_id = result["coin_id"]
        symbol  = result["symbol"]

        for event in result.get("anomalies", []):
            ts         = event["timestamp"]
            event_type = event["event_type"]
            severity   = event["severity"]
            price      = event["price"]
            volume     = event["volume"]
            vol_pct    = event["vol_change_pct"]
            price_pct  = event["price_change_pct"]

            if event_type == "PUMP":
                message = (
                    f"🚀 Pump detected in {symbol} at {_fmt_ts(ts)} — "
                    f"volume spike {vol_pct:.1f}σ above mean "
                    f"| Price: ${price:,.4f}"
                )
            elif event_type == "DUMP":
                message = (
                    f"📉 Dump detected in {symbol} at {_fmt_ts(ts)} — "
                    f"price dropped {price_pct:.1f}σ below mean "
                    f"| Volume: {volume:,.0f}"
                )
            else:
                message = (
                    f"⚠️  Anomaly in {symbol} at {_fmt_ts(ts)} — "
                    f"price Z-score {event['price_zscore']:.2f}, "
                    f"volume Z-score {event['volume_zscore']:.2f}"
                )

            # Deduplicate: skip if same coin + timestamp already stored
            c.execute("""
                SELECT id FROM alerts
                WHERE coin_id=? AND timestamp=? AND alert_type=?
                LIMIT 1
            """, (coin_id, ts, event_type))
            if c.fetchone():
                continue

            c.execute("""
                INSERT INTO alerts
                    (coin_id, symbol, alert_type, message, price, volume, severity, timestamp)
                VALUES (?,?,?,?,?,?,?,?)
            """, (coin_id, symbol, event_type, message,
                  price, volume, severity, ts))
            new_alerts.append({
                "coin_id":    coin_id,
                "symbol":     symbol,
                "alert_type": event_type,
                "message":    message,
                "price":      price,
                "volume":     volume,
                "severity":   severity,
                "timestamp":  ts,
            })

    conn.commit()
    conn.close()
    logger.info("Generated %d new alerts.", len(new_alerts))
    return new_alerts


# ── Retrieve stored alerts ─────────────────────────────────────────────────────
def get_alerts(limit: int = 100, severity: str = None) -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    if severity:
        c.execute("""
            SELECT * FROM alerts WHERE severity=?
            ORDER BY id DESC LIMIT ?
        """, (severity, limit))
    else:
        c.execute("""
            SELECT * FROM alerts
            ORDER BY id DESC LIMIT ?
        """, (limit,))

    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_alert_stats() -> dict:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM alerts")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM alerts WHERE alert_type='PUMP'")
    pumps = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM alerts WHERE alert_type='DUMP'")
    dumps = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM alerts WHERE severity='high'")
    high  = c.fetchone()[0]
    c.execute("SELECT symbol, COUNT(*) as cnt FROM alerts GROUP BY symbol ORDER BY cnt DESC LIMIT 1")
    row = c.fetchone()
    most_alerted = row[0] if row else "N/A"
    conn.close()
    return {
        "total": total, "pumps": pumps, "dumps": dumps,
        "high_severity": high, "most_alerted_coin": most_alerted
    }


# ── Utility ────────────────────────────────────────────────────────────────────
def _fmt_ts(ts: str) -> str:
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%H:%M %d-%b")
    except Exception:
        return ts
