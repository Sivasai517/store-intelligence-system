#!/bin/bash
# run.sh - Pipeline runner script for the Store Intelligence System
#
# Processes all CCTV video files and generates events.
#
# Usage:
#   ./pipeline/run.sh [VIDEO_DIR] [STORE_ID] [API_URL]
#
# Defaults:
#   VIDEO_DIR = /data/videos
#   STORE_ID  = ST1008
#   API_URL   = http://api:8000

set -euo pipefail

VIDEO_DIR="${1:-/data/videos}"
STORE_ID="${2:-ST1008}"
API_URL="${3:-http://api:8000}"
FRAME_SKIP="${FRAME_SKIP:-5}"
CONFIDENCE="${CONFIDENCE:-0.35}"

echo "============================================"
echo "  Store Intelligence - Pipeline Runner"
echo "============================================"
echo "Video directory : ${VIDEO_DIR}"
echo "Store ID        : ${STORE_ID}"
echo "API URL         : ${API_URL}"
echo "Frame skip      : ${FRAME_SKIP}"
echo "Confidence      : ${CONFIDENCE}"
echo "============================================"
echo ""

# Wait for API to be ready
echo "Waiting for API to be ready..."
MAX_RETRIES=30
RETRY_COUNT=0
until curl -sf "${API_URL}/health" > /dev/null 2>&1; do
    RETRY_COUNT=$((RETRY_COUNT + 1))
    if [ "${RETRY_COUNT}" -ge "${MAX_RETRIES}" ]; then
        echo "ERROR: API not available after ${MAX_RETRIES} retries."
        exit 1
    fi
    echo "  API not ready, retrying in 2s... (${RETRY_COUNT}/${MAX_RETRIES})"
    sleep 2
done
echo "API is ready!"
echo ""

# Process each video file
CAM_INDEX=1
for VIDEO_FILE in "${VIDEO_DIR}"/*.mp4; do
    if [ ! -f "${VIDEO_FILE}" ]; then
        echo "No .mp4 files found in ${VIDEO_DIR}"
        exit 0
    fi

    CAMERA_ID="CAM${CAM_INDEX}"
    FILENAME=$(basename "${VIDEO_FILE}")

    echo "--------------------------------------------"
    echo "Processing: ${FILENAME}"
    echo "  Camera ID: ${CAMERA_ID}"
    echo "  Store ID : ${STORE_ID}"
    echo "--------------------------------------------"

    python -m pipeline.emit \
        --video "${VIDEO_FILE}" \
        --store_id "${STORE_ID}" \
        --camera_id "${CAMERA_ID}" \
        --api_url "${API_URL}" \
        --frame_skip "${FRAME_SKIP}" \
        --confidence "${CONFIDENCE}"

    echo "Finished: ${FILENAME}"
    echo ""

    CAM_INDEX=$((CAM_INDEX + 1))
done

echo "============================================"
echo "  Pipeline complete! All videos processed."
echo "============================================"
