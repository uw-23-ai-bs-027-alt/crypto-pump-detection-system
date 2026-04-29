import sqlite3
import logging
import os
from collections import defaultdict
import pandas as pd
import numpy as np
import networkx as nx

logger = logging.getLogger(__name__)

# Optional import: pandas may not be installed in some environments (linter/dev setups).
try:
    import pandas as pd
except Exception:  # pragma: no cover - fallback when pandas not available
    pd = None
    logger.warning("pandas is not available; install pandas to enable full functionality")

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "crypto.db")

CORRELATION_THRESHOLD = 0.7   # edges only for |correlation| >= this
MIN_DATA_POINTS       = 20    # minimum overlapping data points


# ── Load price matrix ──────────────────────────────────────────────────────────
def _load_price_matrix(limit: int = 100)-> pd.DataFrame:
    """
    Returns a DataFrame with timestamps as index and coins as columns (price values).
    """
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("""
        SELECT coin_id, price, timestamp
        FROM crypto_prices
        ORDER BY id DESC LIMIT ?
    """, conn, params=(limit * 15,))   # 15 coins × limit rows
    conn.close()

    if df.empty:
        return pd.DataFrame()

    # Pivot: rows = timestamp buckets, columns = coins
    df["ts_bucket"] = pd.to_datetime(df["timestamp"]).dt.floor("5min")
    pivot = df.groupby(["ts_bucket", "coin_id"])["price"].last().unstack("coin_id")
    return pivot.dropna(how="all")


# ── Build correlation graph ────────────────────────────────────────────────────
def build_correlation_graph(limit: int = 100) -> nx.Graph:
    """
    Builds an undirected weighted graph where:
      - Nodes  = coins
      - Edges  = Pearson correlation >= CORRELATION_THRESHOLD
      - Weight = correlation value
    """
    pivot = _load_price_matrix(limit)
    if pivot.empty or pivot.shape[1] < 2:
        logger.warning("Not enough data for correlation graph.")
        return nx.Graph()

    corr = pivot.corr(method="pearson")
    G = nx.Graph()

    for coin in corr.columns:
        G.add_node(coin)

    for i, c1 in enumerate(corr.columns):
        for j, c2 in enumerate(corr.columns):
            if i >= j:
                continue
            val = corr.loc[c1, c2]
            if pd.isna(val):
                continue
            if abs(val) >= CORRELATION_THRESHOLD:
                G.add_edge(c1, c2, weight=round(float(val), 3))

    return G


# ── Community detection ────────────────────────────────────────────────────────
def detect_communities(G: nx.Graph) -> list[list[str]]:
    """
    Use greedy modularity maximisation to detect clusters.
    Falls back to connected components for small graphs.
    """
    if G.number_of_nodes() == 0:
        return []
    try:
        from networkx.algorithms.community import greedy_modularity_communities
        communities = list(greedy_modularity_communities(G))
        return [sorted(list(c)) for c in communities]
    except Exception:
        return [sorted(list(c)) for c in nx.connected_components(G)]


# ── Hub detection ─────────────────────────────────────────────────────────────
def find_hub_coins(G: nx.Graph) -> list[dict]:
    """
    Coins with high degree centrality = potential market-movers / hubs.
    """
    if G.number_of_nodes() == 0:
        return []
    centrality = nx.degree_centrality(G)
    betweenness = nx.betweenness_centrality(G, weight="weight")
    hubs = []
    for node in G.nodes():
        hubs.append({
            "coin": node,
            "degree": G.degree(node),
            "degree_centrality":      round(centrality.get(node, 0), 3),
            "betweenness_centrality": round(betweenness.get(node, 0), 3),
        })
    return sorted(hubs, key=lambda x: x["betweenness_centrality"], reverse=True)


# ── Suspicious cluster detection ──────────────────────────────────────────────
def find_suspicious_clusters(G: nx.Graph, communities: list) -> list[dict]:
    """
    A cluster is flagged as suspicious when:
      - It contains >= 2 coins
      - The average edge weight (correlation) is very high (>= 0.85)
    This could indicate coordinated trading.
    """
    suspicious = []
    for community in communities:
        if len(community) < 2:
            continue
        subgraph = G.subgraph(community)
        weights  = [d["weight"] for _, _, d in subgraph.edges(data=True) if "weight" in d]
        if not weights:
            continue
        avg_corr = np.mean(weights)
        if avg_corr >= 0.85:
            suspicious.append({
                "coins":            community,
                "size":             len(community),
                "avg_correlation":  round(float(avg_corr), 3),
                "edge_count":       subgraph.number_of_edges(),
                "suspicious_reason": f"High co-movement ({avg_corr:.2f} avg correlation) — possible coordinated pump"
            })
    return suspicious


# ── Volume anomaly graph ───────────────────────────────────────────────────────
def volume_spike_graph(coins: list[tuple]) -> dict:
    """
    Build a simple directed graph: if coin A had a volume spike followed
    within 5 minutes by coin B having a price spike, draw A→B.
    This hints at potential wash-trading or coordinated pumps.
    Returns graph summary (not rendered — just insights).
    """
    conn = sqlite3.connect(DB_PATH)
    spike_times = defaultdict(list)

    for coin_id, symbol in coins:
        df = pd.read_sql_query("""
            SELECT volume_24h, price, timestamp FROM crypto_prices
            WHERE coin_id = ?
            ORDER BY id DESC LIMIT 60
        """, conn, params=(coin_id,))
        if df.empty or len(df) < 5:
            continue
        mean_vol = df["volume_24h"].mean()
        std_vol  = df["volume_24h"].std()
        threshold = mean_vol + 2 * std_vol
        spikes = df[df["volume_24h"] > threshold]
        for ts in spikes["timestamp"]:
            spike_times[symbol].append(ts)

    conn.close()

    DG = nx.DiGraph()
    symbols = list(spike_times.keys())
    for i, s1 in enumerate(symbols):
        for j, s2 in enumerate(symbols):
            if s1 == s2:
                continue
            count = 0
            for t1 in spike_times[s1]:
                for t2 in spike_times[s2]:
                    try:
                        dt = (pd.Timestamp(t2) - pd.Timestamp(t1)).total_seconds()
                        if 0 < dt < 600:   # s2 spike within 10 min after s1
                            count += 1
                    except Exception:
                        pass
            if count > 0:
                DG.add_edge(s1, s2, weight=count)

    # Insights
    in_degree  = dict(DG.in_degree())
    out_degree = dict(DG.out_degree())
    influencers = sorted(out_degree.items(), key=lambda x: x[1], reverse=True)[:3]
    followers   = sorted(in_degree.items(),  key=lambda x: x[1], reverse=True)[:3]

    return {
        "nodes":       list(DG.nodes()),
        "edges":       list(DG.edges(data=True)),
        "influencers": influencers,
        "followers":   followers,
        "edge_count":  DG.number_of_edges(),
    }


# ── Master graph analysis ──────────────────────────────────────────────────────
def run_graph_analysis(coins: list[tuple]) -> dict:
    G            = build_correlation_graph()
    communities  = detect_communities(G)
    hubs         = find_hub_coins(G)
    suspicious   = find_suspicious_clusters(G, communities)
    vol_graph    = volume_spike_graph(coins)

    edges_list = [
        {"source": u, "target": v, "weight": d.get("weight", 0)}
        for u, v, d in G.edges(data=True)
    ]

    return {
        "node_count":           G.number_of_nodes(),
        "edge_count":           G.number_of_edges(),
        "communities":          communities,
        "community_count":      len(communities),
        "hub_coins":            hubs[:5],
        "suspicious_clusters":  suspicious,
        "volume_propagation":   vol_graph,
        "graph_edges":          edges_list,
        "graph_nodes":          list(G.nodes()),
    }
