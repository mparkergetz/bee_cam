import paho.mqtt.client as mqtt
import sqlite3
from datetime import datetime, timedelta
import time
from threading import Thread
import sys
import logging
import json
from utilities.config import Config

config = Config()
unit_name =config['general']['name']
DB_PATH = config['communication']['mqtt_db']

TIMEOUT_THRESHOLD = config.getint('communication', 'timeout_threshold')
TIME_DRIFT_THRESHOLD = config.getint('communication', 'time_drift_threshold')
STARTUP_GRACE_PERIOD = config.getint('communication', 'startup_grace_period')
startup_time = datetime.now()

DEBUG_MODE = False


## ADD THESE TO CONFIG
HUB_IP = "192.168.2.1"
TOPIC = "heartbeat"


### SEPARATE LOGGING CONFIG SO IT DOESN"T OVERWRITE ON IMPORT
log_level = logging.DEBUG if DEBUG_MODE else logging.INFO
logging.basicConfig(filename='./logs/monitor_heartbeat.log', level=log_level, format="%(asctime)s - %(levelname)s - %(message)s")
logging.info("Heartbeat monitor started")

camera_warnings = {}
startup_time = datetime.now()

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS heartbeats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            camera_name TEXT NOT NULL,
            receipt_time TEXT NOT NULL
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS camera_status (
            camera_name TEXT PRIMARY KEY,
            last_seen TEXT NOT NULL,
            sync_status TEXT NOT NULL,
            camera_on BOOLEAN NOT NULL DEFAULT 0
        )
    """)
    
    conn.commit()
    conn.close()

def log_heartbeat(camera_name, receipt_time, sync_status, camera_on):
    """Log the heartbeat receipt time and update the camera status."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO heartbeats (camera_name, receipt_time)
        VALUES (?, ?)
    """, (camera_name, receipt_time))

    cursor.execute("""
        INSERT INTO camera_status (camera_name, last_seen, sync_status, camera_on)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(camera_name) DO UPDATE SET 
            last_seen = excluded.last_seen,
            sync_status = excluded.sync_status,
            camera_on = excluded.camera_on
    """, (camera_name, receipt_time, sync_status, camera_on == 1))

    conn.commit()
    conn.close()

    if camera_name in camera_warnings and sync_status == "good":
        logging.info(f"{camera_name} has recovered.")
        camera_warnings.pop(camera_name, None)

def on_message(client, userdata, msg):
    """Handles incoming MQTT messages."""
    message = json.loads(msg.payload.decode())
    camera_name = message["name"]
    timestamp_str = message["timestamp"]
    camera_on = int(message["cam_on"])
    logging.info(f'{camera_on}, {type(camera_on)}')
    cam_time = datetime.fromisoformat(timestamp_str)
    receipt_time = datetime.now()

    drift = abs((receipt_time - cam_time).total_seconds())
    sync_status = "good" if drift <= TIME_DRIFT_THRESHOLD else "out of sync"

    if sync_status == "out of sync" and camera_warnings.get(camera_name) != "out_of_sync":
        logging.warning(f"WARNING: {camera_name} clock is out of sync by {drift} seconds")
        camera_warnings[camera_name] = "out_of_sync"

    log_heartbeat(camera_name, receipt_time.isoformat(), sync_status, camera_on)

def check_camera_status():
    while True:
        if (datetime.now() - startup_time).total_seconds() < STARTUP_GRACE_PERIOD:
            time.sleep(10)
            continue

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT camera_name, last_seen, sync_status FROM camera_status")
        cameras = cursor.fetchall()
        conn.close()

        hub_time = datetime.now()

        for camera_name, last_seen_str, sync_status in cameras:
            last_seen = datetime.fromisoformat(last_seen_str)
            gap = (hub_time - last_seen).total_seconds()

            if gap > TIMEOUT_THRESHOLD and sync_status == "good" and camera_warnings.get(camera_name) != "down":
                logging.warning(f"WARNING: {camera_name} is DOWN! Last heartbeat received at {last_seen}.")
                log_heartbeat(camera_name, last_seen, sync_status='DOWN', camera_on=0)
                camera_warnings[camera_name] = "down"

            elif gap <= TIMEOUT_THRESHOLD and camera_warnings.get(camera_name) == "down":
                logging.info(f"{camera_name} has recovered from being down.")
                camera_warnings.pop(camera_name, None)

        time.sleep(10)

def MonitorHeartbeat():
    init_db()
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_message = on_message
    client.connect(HUB_IP, 1883, 60)
    client.subscribe(TOPIC)

    Thread(target=check_camera_status, daemon=True).start()

    client.loop_forever()
