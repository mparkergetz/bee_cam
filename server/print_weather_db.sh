#!/bin/bash

DB_PATH="/home/pi/bee_cam/data/weather.db"
NUM_ROWS=5

if [ ! -f "$DB_PATH" ]; then
    echo "Database not found at $DB_PATH"
    exit 1
fi

echo "Showing last $NUM_ROWS rows from weather_data:"
sqlite3 "$DB_PATH" <<EOF
.headers on
.mode column
SELECT * FROM weather_data ORDER BY id DESC LIMIT $NUM_ROWS;
EOF
