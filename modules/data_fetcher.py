"""
data_fetcher.py
Fetches real-time cryptocurrency data from CoinGecko API.
Stores data in SQLite database and CSV backup.
"""

import requests
import sqlite3
import csv
import os
import time
import logging
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
COINGECKO_URL = "https://api.coingecko.com/api/v3/coins/markets"
COINS = ["bitcoin", "ethereum", "binancecoin", "solana", "ripple",
         "dogecoin", "cardano", "avalanche-2", "chainlink", "polkadot"]
CURRENCY = "usd"
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "crypto.db")
CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "crypto_data.csv")

# ── Database Setup ─────────────────────────────────────────────────────────────
def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS crypto_prices (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            coin_id     TEXT    NOT NULL,
            symbol      TEXT    NOT NULL,
            name        TEXT    NOT NULL,
            price       REAL    NOT NULL,
            volume_24h  REAL    NOT NULL,
            price_change_pct REAL,
            market_cap  REAL,
            timestamp   TEXT    NOT NULL
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            coin_id     TEXT    NOT NULL,
            symbol      TEXT    NOT NULL,
            alert_type  TEXT    NOT NULL,
            message     TEXT    NOT NULL,
            price       REAL,
            volume      REAL,
            severity    TEXT    DEFAULT 'medium',
            timestamp   TEXT    NOT NULL
        )
    """)
    conn.commit()
    conn.close()
    logger.info("Database initialized at %s", DB_PATH)


# ── Fetch from CoinGecko ───────────────────────────────────────────────────────
def fetch_market_data():
    """Fetch current prices & volumes for tracked coins."""
    params = {
        "vs_currency": CURRENCY,
        "ids": ",".join(COINS),
        "order": "market_cap_desc",
        "per_page": len(COINS),
        "page": 1,
        "sparkline": False,
        "price_change_percentage": "1h,24h"
    }
    try:
        resp = requests.get(COINGECKO_URL, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        logger.error("API fetch failed: %s", e)
        return []


# ── Store Data ─────────────────────────────────────────────────────────────────
def store_data(records: list[dict]):
    """Persist fetched records to SQLite and CSV."""
    if not records:
        return

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    rows = []

    for r in records:
        row = (
            r.get("id", ""),
            r.get("symbol", "").upper(),
            r.get("name", ""),
            float(r.get("current_price") or 0),
            float(r.get("total_volume") or 0),
            float(r.get("price_change_percentage_24h") or 0),
            float(r.get("market_cap") or 0),
            now,
        )
        rows.append(row)

    c.executemany("""
        INSERT INTO crypto_prices
            (coin_id, symbol, name, price, volume_24h, price_change_pct, market_cap, timestamp)
        VALUES (?,?,?,?,?,?,?,?)
    """, rows)
    conn.commit()
    conn.close()

    # CSV backup
    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    write_header = not os.path.exists(CSV_PATH)
    with open(CSV_PATH, "a", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(["coin_id","symbol","name","price",
                             "volume_24h","price_change_pct","market_cap","timestamp"])
        writer.writerows(rows)

    logger.info("Stored %d records at %s", len(rows), now)


# ── Query Helpers ──────────────────────────────────────────────────────────────
def get_latest_prices() -> list[dict]:
    """Return the most recent row for each coin."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT * FROM crypto_prices
        WHERE id IN (
            SELECT MAX(id) FROM crypto_prices GROUP BY coin_id
        )
        ORDER BY market_cap DESC
    """)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_historical(coin_id: str, limit: int = 100) -> list[dict]:
    """Return last `limit` data points for a coin."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT * FROM crypto_prices
        WHERE coin_id = ?
        ORDER BY id DESC LIMIT ?
    """, (coin_id, limit))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return list(reversed(rows))


def get_all_historical(limit_per_coin: int = 60) -> dict:
    """Return historical data for all coins, keyed by coin_id."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    result = {}
    for coin in COINS:
        c.execute("""
            SELECT price, volume_24h, timestamp FROM crypto_prices
            WHERE coin_id = ?
            ORDER BY id DESC LIMIT ?
        """, (coin, limit_per_coin))
        rows = list(reversed([dict(r) for r in c.fetchall()]))
        if rows:
            result[coin] = rows
    conn.close()
    return result


# ── Seed Dummy Data (for demo / cold start) ────────────────────────────────────
def seed_demo_data():
    """Insert synthetic data so the app works without waiting for 30+ fetches."""
    import random
    import math
    from datetime import timedelta

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM crypto_prices")
    count = c.fetchone()[0]
    conn.close()

    if count >= 200:
        logger.info("Demo data already present, skipping seed.")
        return

    logger.info("Seeding demo data …")
    base_prices = {
        "bitcoin": 67000, "ethereum": 3500, "binancecoin": 580,
        "solana": 170,  "ripple": 0.62,  "dogecoin": 0.16,
        "cardano": 0.48, "avalanche-2": 38, "chainlink": 17, "polkadot": 8.5
    }
    symbols = {
        "bitcoin":"BTC","ethereum":"ETH","binancecoin":"BNB",
        "solana":"SOL","ripple":"XRP","dogecoin":"DOGE",
        "cardano":"ADA","avalanche-2":"AVAX","chainlink":"LINK","polkadot":"DOT"
    }
    names = {k: k.capitalize() for k in base_prices}
    names["avalanche-2"] = "Avalanche"
    names["binancecoin"] = "BNB"
    names["chainlink"] = "Chainlink"
    names["polkadot"] = "Polkadot"

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    base_time = datetime.now(timezone.utc) - timedelta(hours=24)

    all_rows = []
    for coin, base_p in base_prices.items():
        price = base_p
        vol   = base_p * random.uniform(800, 2000)
        for i in range(120):   # 120 data points (one every 12 min over 24h)
            ts = (base_time + timedelta(minutes=i * 12)).isoformat()
            # gentle random walk
            price *= (1 + random.uniform(-0.012, 0.013))
            vol   *= (1 + random.uniform(-0.05,  0.06))
            # inject a synthetic pump at step 80-85
            if 80 <= i <= 85:
                price *= random.uniform(1.04, 1.12)
                vol   *= random.uniform(2.5, 5.0)
            pct = random.uniform(-3, 3)
            mc  = price * random.uniform(1e7, 1e9)
            all_rows.append((coin, symbols[coin], names[coin],
                             round(price,4), round(vol,2), round(pct,2), round(mc,2), ts))

    c.executemany("""
        INSERT INTO crypto_prices
            (coin_id,symbol,name,price,volume_24h,price_change_pct,market_cap,timestamp)
        VALUES (?,?,?,?,?,?,?,?)
    """, all_rows)
    conn.commit()
    conn.close()
    logger.info("Seeded %d synthetic rows.", len(all_rows))


# ── Background Polling Loop ────────────────────────────────────────────────────
def run_fetcher_loop(interval: int = 45):
    """Continuously fetch & store real data (runs in a background thread)."""
    init_db()
    seed_demo_data()
    while True:
        data = fetch_market_data()
        if data:
            store_data(data)
        else:
            logger.warning("Empty API response, skipping store.")
        time.sleep(interval)
