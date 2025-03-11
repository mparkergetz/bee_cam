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
DB_PATH = config['communication']['db_location']

TIMEOUT_THRESHOLD = config.getint('communication', 'timeout_threshold')
TIME_DRIFT_THRESHOLD = config.getint('communication', 'time_drift_threshold')
STARTUP_GRACE_PERIOD = config.getint('communication', 'startup_grace_period')
startup_time = datetime.now()

DEBUG_MODE = False

HUB_IP = "192.168.2.1"
TOPIC = "heartbeat"

log_level = logging.DEBUG if DEBUG_MODE else logging.INFO
logging.basicConfig(filename='./logs/monitor_heartbeat.log', level=log_level, format="%(asctime)s - %(levelname)s - %(message)s")
logging.info("Heartbeat monitor started")

sensor_warnings = {}
startup_time = datetime.now()

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS heartbeats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sensor_name TEXT NOT NULL,
            receipt_time TEXT NOT NULL
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sensor_status (
            sensor_name TEXT PRIMARY KEY,
            last_seen TEXT NOT NULL,
            sync_status TEXT NOT NULL,
            camera_on BOOLEAN NOT NULL DEFAULT 0
        )
    """)
    
    conn.commit()
    conn.close()

def log_heartbeat(sensor_name, receipt_time, sync_status, camera_on):
    """Log the heartbeat receipt time and update the sensor status."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO heartbeats (sensor_name, receipt_time)
        VALUES (?, ?)
    """, (sensor_name, receipt_time))

    cursor.execute("""
        INSERT INTO sensor_status (sensor_name, last_seen, sync_status, camera_on)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(sensor_name) DO UPDATE SET 
            last_seen = excluded.last_seen,
            sync_status = excluded.sync_status,
            camera_on = excluded.camera_on
    """, (sensor_name, receipt_time, sync_status, camera_on == 1))

    conn.commit()
    conn.close()

    if sensor_name in sensor_warnings and sync_status == "good":
        logging.info(f"{sensor_name} has recovered.")
        sensor_warnings.pop(sensor_name, None)

def on_message(client, userdata, msg):
    """Handles incoming MQTT messages."""
    message = json.loads(msg.payload.decode())
    sensor_name = message["name"]
    timestamp_str = message["timestamp"]
    camera_on = int(message["cam_on"])
    logging.info(f'{camera_on}, {type(camera_on)}')
    sensor_time = datetime.fromisoformat(timestamp_str)
    receipt_time = datetime.now()

    drift = abs((receipt_time - sensor_time).total_seconds())
    sync_status = "good" if drift <= TIME_DRIFT_THRESHOLD else "out of sync"

    if sync_status == "out of sync" and sensor_warnings.get(sensor_name) != "out_of_sync":
        logging.warning(f"WARNING: {sensor_name} clock is out of sync by {drift} seconds")
        sensor_warnings[sensor_name] = "out_of_sync"

    log_heartbeat(sensor_name, receipt_time.isoformat(), sync_status, camera_on)

def check_sensor_status():
    while True:
        if (datetime.now() - startup_time).total_seconds() < STARTUP_GRACE_PERIOD:
            time.sleep(10)
            continue

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT sensor_name, last_seen, sync_status FROM sensor_status")
        sensors = cursor.fetchall()
        conn.close()

        hub_time = datetime.now()

        for sensor_name, last_seen_str, sync_status in sensors:
            last_seen = datetime.fromisoformat(last_seen_str)
            gap = (hub_time - last_seen).total_seconds()

            if gap > TIMEOUT_THRESHOLD and sync_status == "good" and sensor_warnings.get(sensor_name) != "down":
                logging.warning(f"WARNING: {sensor_name} is DOWN! Last heartbeat received at {last_seen}.")
                sensor_warnings[sensor_name] = "down"

            elif gap <= TIMEOUT_THRESHOLD and sensor_warnings.get(sensor_name) == "down":
                logging.info(f"{sensor_name} has recovered from being down.")
                sensor_warnings.pop(sensor_name, None)

        time.sleep(10)

def MonitorHeartbeat():
    init_db()
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_message = on_message
    client.connect(HUB_IP, 1883, 60)
    client.subscribe(TOPIC)

    Thread(target=check_sensor_status, daemon=True).start()

    client.loop_forever()
