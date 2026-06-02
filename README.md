# Store Intelligence System 🏪

An end-to-end retail analytics pipeline that processes CCTV footage to generate real-time metrics, visitor funnels, and anomaly alerts.

## 🚀 One-Command Deployment

The entire system (API, Pipeline, Dashboard) runs via Docker Compose:

```bash
docker compose up --build
```

*Note: Ensure you have your CCTV clips (.mp4) in the `/data/videos` volume or use the provided cameras.*

## 🏗️ Repository Structure

```text
store-intelligence/
├── pipeline/          # Computer Vision Layer (YOLOv8 + ByteTrack)
├── app/               # FastAPI Backend (Metrics, Funnel, Heatmap)
├── dashboard/         # Streamlit Dashboard (Live KPI Feed)
├── tests/             # Pytest Suite (>70% coverage)
├── docs/              # Design and Technical Choices
└── docker-compose.yml # Orchestration
```

## 🛠️ API Endpoints

-   `POST /events/ingest`: Ingest visitor events (idempotent).
-   `GET /stores/{id}/metrics`: Fetch unique visitors, conversion rate, etc.
-   `GET /stores/{id}/funnel`: Conversion funnel (Entry → Queue → Purchase).
-   `GET /stores/{id}/heatmap`: Zone activity and dwell time.
-   `GET /stores/{id}/anomalies`: Active alerts (Queue Spikes, etc.).
-   `GET /health`: Service and feed health status.

## 🧪 Testing

Run the comprehensive test suite locally:

```bash
pip install -r requirements.txt
pytest tests/ -v --cov=app --cov=pipeline
```

## 📈 Dashboard Features

-   **Real-time KPIs**: Visitor counts, conversion rates, and queue depth.
-   **Visitor Funnel**: Visual representation of the customer journey.
-   **Zone Heatmap**: Activity scores per store area.
-   **Anomaly Alerts**: Live notification of critical events like queue spikes.

## 📄 Documentation

-   [Architecture Design](docs/DESIGN.md)
-   [Technical Choices](docs/CHOICES.md)
```
