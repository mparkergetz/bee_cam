#!/bin/bash

# === CONFIGURATION ===
BROKER="r00f7910.ala.us-east-1.emqxsl.com"
PORT=8883
USERNAME="user1"
PASSWORD="user1pasS"
CERT_PATH="./mycert.crt"

TOPICS=(
  "+/weather"
  "+/status/#"
)

# === CHECK DEPENDENCIES ===
for cmd in mosquitto_sub jq; do
    if ! command -v "$cmd" &> /dev/null; then
        echo "❌ $cmd not found. Please install it (e.g. sudo apt install $cmd)."
        exit 1
    fi
done

echo "Connecting to MQTT broker at $BROKER:$PORT"
echo "Subscribing to topics: ${TOPICS[*]}"
echo "----------------------------------------"

# === SUBSCRIBE AND PARSE ===
mosquitto_sub \
    -h "$BROKER" \
    -p "$PORT" \
    --cafile "$CERT_PATH" \
    -u "$USERNAME" \
    -P "$PASSWORD" \
    -v \
    -t "+/weather" \
    -t "+/status/#" | while read -r topic payload; do

    unit=$(echo "$topic" | cut -d'/' -f1)
    subtopic=$(echo "$topic" | cut -d'/' -f2)

    echo
    echo "Unit:        $unit"
    echo "Topic:       $subtopic"

    if [[ "$subtopic" == "weather" ]]; then
        echo "$payload" | jq -r '
            "Time:        \(.time)",
            "Temperature: \(.temp) °C",
            "Humidity:    \(.humid) %",
            "Pressure:    \(.pres) hPa",
            "Wind Speed:  \(.wind) m/s"
        '
    elif [[ "$subtopic" == "status" ]]; then
        echo "$payload" | jq -r '
            "Camera:      \(.camera)",
            "Last Seen:   \(.last_seen)",
            "Sync Status: \(.sync_status)",
            "Camera On:   \(.camera_on)"
        '
    else
        echo "$payload"
    fi

    echo "----------------------------------------"
done
