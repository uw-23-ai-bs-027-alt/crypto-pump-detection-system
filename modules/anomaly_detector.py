import sqlite3
import logging
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "crypto.db")

# ── Tuneable Parameters ────────────────────────────────────────────────────────
ZSCORE_PRICE_THRESH  = 2.5   # std-devs above mean → suspicious price spike
ZSCORE_VOLUME_THRESH = 2.0   # std-devs above mean → suspicious volume spike
MIN_ROWS_REQUIRED    = 10    # need at least this many points to analyse
ISO_CONTAMINATION    = 0.05  # expected fraction of anomalies (5 %)


# ── Load data for a single coin ────────────────────────────────────────────────
def _load_coin_df(coin_id: str, limit: int = 120) -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("""
        SELECT price, volume_24h, price_change_pct, timestamp
        FROM crypto_prices
        WHERE coin_id = ?
        ORDER BY id DESC LIMIT ?
    """, conn, params=(coin_id, limit))
    conn.close()
    return df.iloc[::-1].reset_index(drop=True)  # chronological order


# ── 1. Statistical Thresholding ────────────────────────────────────────────────
def zscore_anomalies(df: pd.DataFrame) -> pd.DataFrame:
    """
    Flag rows where price OR volume deviates > threshold standard deviations
    from the rolling mean.  Returns DataFrame with added columns:
      price_zscore, volume_zscore, stat_anomaly (bool)
    """
    df = df.copy()
    for col, thresh, out in [
        ("price",      ZSCORE_PRICE_THRESH,  "price_zscore"),
        ("volume_24h", ZSCORE_VOLUME_THRESH, "volume_zscore"),
    ]:
        mu  = df[col].mean()
        sig = df[col].std() + 1e-9
        df[out] = (df[col] - mu) / sig

    df["stat_anomaly"] = (
        (df["price_zscore"]  > ZSCORE_PRICE_THRESH) |
        (df["volume_zscore"] > ZSCORE_VOLUME_THRESH)
    )
    return df


# ── 2. Isolation Forest ────────────────────────────────────────────────────────
def isolation_forest_anomalies(df: pd.DataFrame) -> pd.DataFrame:
    """
    Use Isolation Forest on [price, volume_24h, price_change_pct].
    Adds column `iso_anomaly` (bool) and `iso_score` (lower = more anomalous).
    """
    df = df.copy()
    features = ["price", "volume_24h", "price_change_pct"]
    X = df[features].fillna(0).values

    clf = IsolationForest(
        n_estimators=100,
        contamination=ISO_CONTAMINATION,
        random_state=42
    )
    clf.fit(X)
    df["iso_score"]   = clf.decision_function(X)   # negative = more anomalous
    df["iso_anomaly"] = clf.predict(X) == -1        # True = anomaly
    return df


# ── Combined Analysis ──────────────────────────────────────────────────────────
def analyse_coin(coin_id: str, symbol: str) -> dict:
    """
    Run both detectors on a coin.
    Returns a dict with summary stats and a list of anomaly events.
    """
    df = _load_coin_df(coin_id)
    if len(df) < MIN_ROWS_REQUIRED:
        return {"coin_id": coin_id, "symbol": symbol, "status": "insufficient_data", "anomalies": []}

    df = zscore_anomalies(df)
    df = isolation_forest_anomalies(df)

    # Combined flag: flagged by EITHER method
    df["is_anomaly"] = df["stat_anomaly"] | df["iso_anomaly"]

    anomaly_rows = df[df["is_anomaly"]].copy()

    events = []
    for _, row in anomaly_rows.iterrows():
        vol_change_pct = (row["volume_zscore"] * 100) if not pd.isna(row.get("volume_zscore")) else 0
        price_change_pct = (row["price_zscore"] * 100) if not pd.isna(row.get("price_zscore")) else 0

        # Determine pump vs dump
        if row["price_change_pct"] > 0 and row["volume_zscore"] > ZSCORE_VOLUME_THRESH:
            event_type = "PUMP"
        elif row["price_change_pct"] < -2:
            event_type = "DUMP"
        else:
            event_type = "ANOMALY"

        severity = "high" if (abs(row["price_zscore"]) > 4 or abs(row["volume_zscore"]) > 4) else "medium"

        events.append({
            "timestamp":        row["timestamp"],
            "price":            round(float(row["price"]), 4),
            "volume":           round(float(row["volume_24h"]), 2),
            "price_zscore":     round(float(row["price_zscore"]), 2),
            "volume_zscore":    round(float(row["volume_zscore"]), 2),
            "iso_score":        round(float(row["iso_score"]), 4),
            "stat_anomaly":     bool(row["stat_anomaly"]),
            "iso_anomaly":      bool(row["iso_anomaly"]),
            "event_type":       event_type,
            "severity":         severity,
            "vol_change_pct":   round(abs(vol_change_pct), 1),
            "price_change_pct": round(abs(price_change_pct), 1),
        })

    return {
        "coin_id":       coin_id,
        "symbol":        symbol,
        "status":        "ok",
        "total_rows":    len(df),
        "anomaly_count": len(events),
        "mean_price":    round(float(df["price"].mean()), 4),
        "std_price":     round(float(df["price"].std()), 4),
        "mean_volume":   round(float(df["volume_24h"].mean()), 2),
        "std_volume":    round(float(df["volume_24h"].std()), 2),
        "anomalies":     events,
        # Full series for charting
        "series": {
            "timestamps": df["timestamp"].tolist(),
            "prices":     [round(float(v), 4) for v in df["price"]],
            "volumes":    [round(float(v), 2) for v in df["volume_24h"]],
            "anomaly_flags": df["is_anomaly"].tolist(),
        }
    }


# ── Analyse ALL tracked coins ──────────────────────────────────────────────────
def run_full_analysis(coins: list[tuple]) -> list[dict]:
    """
    coins: list of (coin_id, symbol) tuples
    Returns list of analysis dicts, sorted by anomaly_count desc.
    """
    results = []
    for coin_id, symbol in coins:
        try:
            res = analyse_coin(coin_id, symbol)
            results.append(res)
        except Exception as e:
            logger.error("Analysis failed for %s: %s", coin_id, e)
    results.sort(key=lambda x: x.get("anomaly_count", 0), reverse=True)
    return results


# ── Quick summary for dashboard ────────────────────────────────────────────────
def get_anomaly_summary(coins: list[tuple]) -> dict:
    """Lightweight summary: total alerts, most suspicious coin, etc."""
    all_results = run_full_analysis(coins)
    total_anomalies = sum(r.get("anomaly_count", 0) for r in all_results)
    most_suspicious = all_results[0] if all_results else {}

    return {
        "total_coins_analysed": len(all_results),
        "total_anomalies":      total_anomalies,
        "most_suspicious_coin": most_suspicious.get("symbol", "N/A"),
        "most_suspicious_count": most_suspicious.get("anomaly_count", 0),
        "details":              all_results,
    }
