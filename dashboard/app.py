"""
app.py - Streamlit dashboard for the Store Intelligence System.

Displays:
- Visitor Count (KPI card)
- Conversion Rate (KPI card)
- Queue Depth (KPI card)
- Abandonment Rate (KPI card)
- Visitor Funnel (bar chart)
- Zone Heatmap (bar chart with color scale)
- Active Anomalies (alert cards)
- Live Event Feed (table)

Auto-refreshes every 10 seconds.
"""

import time
from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_URL = "http://api:8000"  # Docker service name; use localhost for local dev
REFRESH_INTERVAL = 10  # seconds
DEFAULT_STORE_ID = "ST1008"

# ---------------------------------------------------------------------------
# Page Configuration
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Store Intelligence Dashboard",
    page_icon="🏪",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Custom CSS for premium styling
# ---------------------------------------------------------------------------

st.markdown("""
<style>
    /* Main background */
    .stApp {
        background: linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%);
    }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background: rgba(15, 12, 41, 0.95);
        border-right: 1px solid rgba(255, 255, 255, 0.1);
    }

    /* KPI Cards */
    .kpi-card {
        background: rgba(255, 255, 255, 0.08);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.15);
        border-radius: 16px;
        padding: 24px;
        text-align: center;
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .kpi-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
    }
    .kpi-value {
        font-size: 2.8rem;
        font-weight: 700;
        background: linear-gradient(135deg, #00d2ff, #7b2ff7);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin: 8px 0;
    }
    .kpi-label {
        font-size: 0.95rem;
        color: rgba(255, 255, 255, 0.6);
        text-transform: uppercase;
        letter-spacing: 1.5px;
    }

    /* Anomaly cards */
    .anomaly-critical {
        background: rgba(255, 59, 48, 0.15);
        border: 1px solid rgba(255, 59, 48, 0.4);
        border-radius: 12px;
        padding: 16px;
        margin: 8px 0;
    }
    .anomaly-warn {
        background: rgba(255, 204, 0, 0.15);
        border: 1px solid rgba(255, 204, 0, 0.4);
        border-radius: 12px;
        padding: 16px;
        margin: 8px 0;
    }
    .anomaly-info {
        background: rgba(0, 122, 255, 0.15);
        border: 1px solid rgba(0, 122, 255, 0.4);
        border-radius: 12px;
        padding: 16px;
        margin: 8px 0;
    }

    /* Section headers */
    .section-header {
        font-size: 1.3rem;
        font-weight: 600;
        color: rgba(255, 255, 255, 0.9);
        margin: 24px 0 16px 0;
        padding-bottom: 8px;
        border-bottom: 2px solid rgba(123, 47, 247, 0.5);
    }

    /* Hide default streamlit elements */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# API Helper Functions
# ---------------------------------------------------------------------------

def fetch_api(endpoint: str) -> dict | None:
    """Fetch data from the FastAPI backend."""
    try:
        response = requests.get(f"{API_URL}{endpoint}", timeout=5)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.warning(f"API error: {e}")
        return None


def fetch_health() -> dict | None:
    return fetch_api("/health")


def fetch_metrics(store_id: str) -> dict | None:
    return fetch_api(f"/stores/{store_id}/metrics")


def fetch_funnel(store_id: str) -> dict | None:
    return fetch_api(f"/stores/{store_id}/funnel")


def fetch_heatmap(store_id: str) -> dict | None:
    return fetch_api(f"/stores/{store_id}/heatmap")


def fetch_anomalies(store_id: str) -> dict | None:
    return fetch_api(f"/stores/{store_id}/anomalies")


# ---------------------------------------------------------------------------
# Dashboard Layout
# ---------------------------------------------------------------------------

def render_dashboard():
    """Main dashboard rendering function."""

    # Sidebar
    with st.sidebar:
        st.markdown("# 🏪 Store Intelligence")
        st.markdown("---")
        store_id = st.text_input("Store ID", value=DEFAULT_STORE_ID)
        auto_refresh = st.checkbox("Auto-refresh", value=True)
        refresh_rate = st.slider("Refresh interval (s)", 5, 60, REFRESH_INTERVAL)
        st.markdown("---")

        # Health status
        health = fetch_health()
        if health:
            status_emoji = "🟢" if health["status"] == "healthy" else "🔴"
            st.markdown(f"**Status:** {status_emoji} {health['status'].upper()}")
            st.markdown(f"**Events:** {health.get('total_events', 0):,}")
            if health.get("last_event_timestamp"):
                st.markdown(f"**Last event:** {health['last_event_timestamp'][:19]}")
            if health.get("stale_feed_warning"):
                st.warning("⚠️ Stale feed detected!")
        else:
            st.error("❌ API unreachable")

        st.markdown("---")
        st.caption(f"Last updated: {datetime.now().strftime('%H:%M:%S')}")

    # Main content
    st.markdown(
        '<h1 style="text-align: center; color: white; margin-bottom: 8px;">'
        '🏪 Store Intelligence Dashboard</h1>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p style="text-align: center; color: rgba(255,255,255,0.5); margin-bottom: 32px;">'
        f'Real-time analytics for Store {store_id}</p>',
        unsafe_allow_html=True,
    )

    # --- KPI Cards ---
    metrics = fetch_metrics(store_id)
    if metrics:
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.markdown(f"""
            <div class="kpi-card">
                <div class="kpi-label">Unique Visitors</div>
                <div class="kpi-value">{metrics['unique_visitors']}</div>
            </div>
            """, unsafe_allow_html=True)

        with col2:
            conv_pct = f"{metrics['conversion_rate'] * 100:.1f}%"
            st.markdown(f"""
            <div class="kpi-card">
                <div class="kpi-label">Conversion Rate</div>
                <div class="kpi-value">{conv_pct}</div>
            </div>
            """, unsafe_allow_html=True)

        with col3:
            st.markdown(f"""
            <div class="kpi-card">
                <div class="kpi-label">Queue Depth</div>
                <div class="kpi-value">{metrics['queue_depth']}</div>
            </div>
            """, unsafe_allow_html=True)

        with col4:
            abandon_pct = f"{metrics['abandonment_rate'] * 100:.1f}%"
            st.markdown(f"""
            <div class="kpi-card">
                <div class="kpi-label">Abandonment Rate</div>
                <div class="kpi-value">{abandon_pct}</div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("📊 Waiting for metrics data...")

    st.markdown("<br>", unsafe_allow_html=True)

    # --- Funnel + Heatmap ---
    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown('<div class="section-header">📊 Visitor Funnel</div>',
                     unsafe_allow_html=True)
        funnel_data = fetch_funnel(store_id)
        if funnel_data and funnel_data.get("stages"):
            df_funnel = pd.DataFrame(funnel_data["stages"])
            fig = go.Figure(go.Funnel(
                y=df_funnel["stage"],
                x=df_funnel["count"],
                textinfo="value+percent initial",
                marker=dict(
                    color=["#7b2ff7", "#00d2ff", "#ffd700", "#00e676"],
                ),
            ))
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="white", size=14),
                margin=dict(l=20, r=20, t=20, b=20),
                height=350,
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No funnel data available yet.")

    with col_right:
        st.markdown('<div class="section-header">🗺️ Zone Heatmap</div>',
                     unsafe_allow_html=True)
        heatmap_data = fetch_heatmap(store_id)
        if heatmap_data and heatmap_data.get("zones"):
            df_heatmap = pd.DataFrame(heatmap_data["zones"])
            fig = px.bar(
                df_heatmap,
                x="zone_id",
                y="normalized_score",
                color="normalized_score",
                color_continuous_scale=["#302b63", "#7b2ff7", "#00d2ff", "#ffd700"],
                labels={"zone_id": "Zone", "normalized_score": "Activity Score"},
            )
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="white"),
                margin=dict(l=20, r=20, t=20, b=20),
                height=350,
                xaxis=dict(gridcolor="rgba(255,255,255,0.1)"),
                yaxis=dict(gridcolor="rgba(255,255,255,0.1)"),
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No heatmap data available yet.")

    # --- Anomalies ---
    st.markdown('<div class="section-header">⚠️ Active Anomalies</div>',
                 unsafe_allow_html=True)
    anomaly_data = fetch_anomalies(store_id)
    if anomaly_data and anomaly_data.get("anomalies"):
        for anomaly in anomaly_data["anomalies"]:
            severity = anomaly["severity"].lower()
            css_class = f"anomaly-{severity}"
            severity_emoji = {"critical": "🔴", "warn": "🟡", "info": "🔵"}.get(
                severity, "⚪"
            )
            st.markdown(f"""
            <div class="{css_class}">
                <strong>{severity_emoji} {anomaly['anomaly_type']}</strong>
                — {anomaly['severity']}<br>
                <span style="color: rgba(255,255,255,0.8);">{anomaly['description']}</span><br>
                <em style="color: rgba(255,255,255,0.5);">💡 {anomaly['suggested_action']}</em>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.success("✅ No anomalies detected.")

    # --- Live Event Feed ---
    st.markdown('<div class="section-header">📡 Live Event Feed</div>',
                 unsafe_allow_html=True)
    if metrics and metrics.get("unique_visitors", 0) > 0:
        # Show avg dwell time as a simple table
        if metrics.get("avg_dwell_time"):
            st.markdown("**Average Dwell Time by Zone:**")
            dwell_df = pd.DataFrame([
                {"Zone": k, "Avg Dwell (ms)": v}
                for k, v in metrics["avg_dwell_time"].items()
            ])
            st.dataframe(dwell_df, use_container_width=True, hide_index=True)
    else:
        st.info("🔄 Waiting for events... The pipeline will populate data automatically.")

    # Auto-refresh
    if auto_refresh:
        time.sleep(refresh_rate)
        st.rerun()


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    render_dashboard()
else:
    render_dashboard()
