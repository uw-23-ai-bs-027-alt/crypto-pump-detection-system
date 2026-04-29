# 🔍 CryptoPulse — Pump & Dump Detection System

A real-time cryptocurrency surveillance dashboard using Python (Flask) + data mining (Isolation Forest + Statistical Thresholding) + graph mining (NetworkX).

---

## ⚡ Quick Start (3 Commands)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the app
python app.py

# 3. Open browser
# http://localhost:5000
```

---

## 📁 Project Structure

```
crypto_pump_detector/
│
├── app.py                      ← Flask app (routes, background thread)
├── requirements.txt
├── README.md
│
├── modules/
│   ├── data_fetcher.py         ← CoinGecko API + SQLite storage
│   ├── anomaly_detector.py     ← Isolation Forest + Z-score detection  ← CORE DATA MINING
│   ├── graph_miner.py          ← NetworkX correlation + cluster analysis
│   └── alert_system.py        ← Alert generation and retrieval
│
├── templates/
│   ├── base.html               ← Sidebar layout
│   ├── index.html              ← Dashboard homepage
│   ├── live.html               ← Live price feed
│   ├── analytics.html          ← Deep analysis + graph mining
│   └── alerts.html             ← Alert centre
│
├── static/
│   └── css/
│       └── style.css           ← Dark cyberpunk UI
│
└── data/                       ← Auto-created
    ├── crypto.db               ← SQLite database
    └── crypto_data.csv         ← CSV backup
```

---

## 🧠 Data Mining Core

### 1. Statistical Thresholding (Z-Score)
```python
# Flag if price or volume deviates > threshold std-devs from the mean
z_score = (value - mean) / std_dev
if z_score > threshold:    # 2.5σ for price, 2.0σ for volume
    flag as anomaly
```

### 2. Isolation Forest (sklearn)
```python
clf = IsolationForest(n_estimators=100, contamination=0.05)
clf.fit(X)  # Features: [price, volume_24h, price_change_pct]
predictions = clf.predict(X)  # -1 = anomaly, 1 = normal
```

### 3. Combined Decision
An event is flagged as a **pump-and-dump** if:
- Statistical anomaly (Z-score) **OR** Isolation Forest flags it
- Pump: high volume Z-score + positive price change
- Dump: negative price change after a pump

---

## 📊 Graph Mining (NetworkX)

- **Correlation Graph**: coins with Pearson correlation ≥ 0.7 are connected by edges
- **Community Detection**: greedy modularity maximisation finds clusters of co-moving coins
- **Hub Detection**: degree + betweenness centrality identifies market-moving coins
- **Suspicious Clusters**: clusters with avg correlation ≥ 0.85 flagged as potentially coordinated
- **Volume Propagation**: directed graph showing which coin's volume spike precedes another's

---

## 🌐 Pages

| URL | Description |
|-----|-------------|
| `/` | Dashboard — overview, live prices, recent alerts |
| `/live` | Live feed with per-coin price/volume charts |
| `/analytics` | Deep anomaly analysis + graph mining |
| `/alerts` | Full alert log with timeline chart |

## 🔌 JSON API

| Endpoint | Description |
|----------|-------------|
| `GET /api/live` | Latest snapshot for all 10 coins |
| `GET /api/historical/<coin>?limit=N` | Historical data points |
| `GET /api/anomalies` | Run full anomaly scan (all coins) |
| `GET /api/anomalies/<coin>` | Single coin analysis with chart series |
| `GET /api/graph` | Graph mining results |
| `GET /api/alerts?severity=high` | Stored alerts |
| `GET /api/summary` | Dashboard summary |

---

## ⚙️ Configuration

Edit `modules/data_fetcher.py`:
```python
COINS = ["bitcoin", "ethereum", ...]   # which coins to track
```

Edit `modules/anomaly_detector.py`:
```python
ZSCORE_PRICE_THRESH  = 2.5   # raise to reduce sensitivity
ZSCORE_VOLUME_THRESH = 2.0
ISO_CONTAMINATION    = 0.05  # expected % of anomalies
```

---

## 📦 Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| Flask | 3.0.0 | Web framework |
| requests | 2.31.0 | CoinGecko API calls |
| pandas | 2.1.4 | Data manipulation |
| numpy | 1.26.2 | Numerical operations |
| scikit-learn | 1.3.2 | Isolation Forest |
| networkx | 3.2.1 | Graph mining |
| python-dateutil | 2.8.2 | Timestamp parsing |

All lightweight — runs fine on Core i5, no GPU required.

---

## 🎨 UI Features

- **Dark cyberpunk aesthetic** with cyan/green/red accent colors
- **Scanline overlay** for retro terminal feel
- **Live ticker bar** with auto-scrolling prices
- **Auto-refresh** every 30 seconds
- **Red anomaly markers** on price charts
- **Volume spike bars** highlighted in red
- **Alert badges** with severity levels (high/medium)

---

## 🔄 Data Flow

```
CoinGecko API
     ↓ (every 45s, background thread)
data_fetcher.py → SQLite DB + CSV
     ↓
anomaly_detector.py
  ├── Z-Score Analysis
  └── Isolation Forest
     ↓
alert_system.py → alerts table
     ↓
Flask routes → JSON API → Browser dashboard
```

---

## 🚀 Demo Mode

On first startup, 1,200 synthetic data points are automatically seeded (120 points × 10 coins) so the app is immediately usable without waiting for real API data to accumulate. A synthetic pump is injected at timestep 80–85 for each coin to demonstrate detection.

Real CoinGecko data starts flowing immediately in the background — no API key required.
