CryptoPulse is a real-time cryptocurrency monitoring system that detects abnormal market behavior using statistical analysis, machine learning, and graph-based mining techniques.

It identifies potential pump-and-dump patterns in crypto markets using multi-layer anomaly detection.

---

## Features

- Real-time cryptocurrency data ingestion (CoinGecko API)
- Statistical anomaly detection (Z-score analysis)
- Machine learning detection (Isolation Forest)
- Graph-based market relationship analysis (NetworkX)
- Alert generation system for suspicious activity
- Web dashboard for live and historical data visualization
- REST API for data access and analysis

---

## Quick Start

```bash
pip install -r requirements.txt
python app.py

Open in browser:

http://localhost:5000
Project Structure
crypto_pump_detector/
│
├── app.py
├── requirements.txt
│
├── modules/
│   ├── data_fetcher.py
│   ├── anomaly_detector.py
│   ├── graph_miner.py
│   └── alert_system.py
│
├── templates/
├── static/
└── data/

API Endpoints
Endpoint	Description
/api/live	Live market data
/api/historical/<coin>	Historical data
/api/anomalies	Anomaly detection scan
/api/graph	Graph analysis results
/api/alerts	Alert history
Core Methods
Z-Score: Detects statistical anomalies in price and volume
Isolation Forest: Machine learning-based anomaly detection
NetworkX Graph Analysis: Finds correlated and suspicious coin clusters
Data Flow

CoinGecko API → Data Fetcher → Storage → Anomaly Detection → Graph Analysis → Alerts → Dashboard

#Author

Rehan Ahmad
BS Artificial Intelligence Student
GitHub: https://github.com/yourusername

Email: your.email@example.com
