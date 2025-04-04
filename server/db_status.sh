#!/bin/bash

DB_PATH="../logs/heartbeats.db"

echo "===== Last 10 Heartbeats ====="
sqlite3 "$DB_PATH" <<EOF
.headers on
.mode column
SELECT * FROM heartbeats ORDER BY receipt_time DESC LIMIT 10;
EOF

echo ""
echo "===== Latest Cam Status ====="
sqlite3 "$DB_PATH" <<EOF
.headers on
.mode column
SELECT * FROM camera_status;
EOF
