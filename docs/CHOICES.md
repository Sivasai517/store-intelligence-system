# Store Intelligence System - Technical Choices

## 1. Why YOLOv8?
**Alternatives considered:** YOLOv5, Faster R-CNN, SSD.
-   **AI Suggestion**: YOLOv8 provides the best trade-off between inference speed and mAP (Mean Average Precision).
-   **Final Reasoning**: YOLOv8n (Nano) is extremely lightweight, capable of running >60 FPS on average CPUs, making it ideal for processing multiple CCTV feeds simultaneously without dedicated GPUs.

## 2. Why ByteTrack?
**Alternatives considered:** SORT, DeepSORT.
-   **AI Suggestion**: ByteTrack is the current state-of-the-art for multi-object tracking without needing deep feature extractors for every frame.
-   **Final Reasoning**: Unlike DeepSORT, ByteTrack doesn't require a separate Re-ID model, reducing computational overhead. It excels at keeping track IDs during occlusions (e.g., when a person walks behind a shelf).

## 3. Why SQLite?
**Alternatives considered:** PostgreSQL, MongoDB.
-   **AI Suggestion**: SQLite is sufficient for single-store analytics and simplifies deployment.
-   **Final Reasoning**: For the Purplle Challenge scope, a zero-config database is preferred. SQLite with WAL (Write-Ahead Logging) handles the event ingestion rates for 5-10 cameras comfortably while maintaining 100% portability.

## 4. Why FastAPI?
**Alternatives considered:** Flask, Django.
-   **AI Suggestion**: FastAPI's asynchronous nature is perfect for I/O bound tasks like event logging.
-   **Final Reasoning**: FastAPI provides automatic Swagger documentation and high performance. The built-in Pydantic validation ensures the event schema is strictly enforced at the edge.

## 5. Why Streamlit?
**Alternatives considered:** React, Dash.
-   **Final Reasoning**: Streamlit allows for the creation of high-fidelity, interactive dashboards with Python logic, enabling rapid iteration on retail metrics without complex frontend boilerplate.
