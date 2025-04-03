import os
import json
import time
import sqlite3
import threading
from utilities.logger import logger as base_logger
logger = base_logger.getChild("MQTT")

from datetime import datetime
import paho.mqtt.client as mqtt

from utilities.config import Config

class MQTTManager:
    def __init__(self):
        self.config = Config()
        self.unit_name = self.config['general']['name']

        self.package_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        self.weather_db_path = os.path.join(self.package_root, self.config['communication']['weather_db'])
        self.heartbeat_db_path = os.path.join(self.package_root, self.config['communication']['mqtt_db'])

        self.TIMEOUT_THRESHOLD = self.config.getint('communication', 'timeout_threshold')
        self.TIME_DRIFT_THRESHOLD = self.config.getint('communication', 'time_drift_threshold')
        self.STARTUP_GRACE_PERIOD = self.config.getint('communication', 'startup_grace_period')
        self.startup_time = datetime.now()

        self.remote_broker = "r00f7910.ala.us-east-1.emqxsl.com"
        self.remote_port = 8883
        self.mqtt_user = "user1"
        self.mqtt_pass = "user1pasS"
        self.heartbeat_topic = "heartbeat"
        self.hub_IP = "192.168.2.1"

        self.last_seen_cache = {}
        self.camera_warnings = {}

        # Remote client (EMQX)
        self.remote_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.remote_client.username_pw_set(self.mqtt_user, self.mqtt_pass)
        cert_path = os.path.join(os.path.dirname(__file__), "mycert.crt")
        self.remote_client.tls_set(ca_certs=cert_path)
        self.remote_client.on_connect = self._on_remote_connect

        # Local client (LAN heartbeat)
        self.local_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.local_client.on_connect = self._on_local_connect
        self.local_client.on_message = self._on_heartbeat

        # DB connections
        self.weather_conn = sqlite3.connect(self.weather_db_path, check_same_thread=False)
        self.weather_cursor = self.weather_conn.cursor()

        self.hb_conn = sqlite3.connect(self.heartbeat_db_path, check_same_thread=False)
        self.hb_cursor = self.hb_conn.cursor()
        self._init_heartbeat_db()

        # Logging
        # log_path = os.path.join(self.package_root, "logs", "mqtt_manager.log")
        # os.makedirs(os.path.dirname(log_path), exist_ok=True)
        # logging.basicConfig(filename=log_path, level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    def _init_heartbeat_db(self):
        self.hb_cursor.execute("""
            CREATE TABLE IF NOT EXISTS heartbeats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                camera_name TEXT NOT NULL,
                receipt_time TEXT NOT NULL
            )
        """)
        self.hb_cursor.execute("""
            CREATE TABLE IF NOT EXISTS camera_status (
                camera_name TEXT PRIMARY KEY,
                last_seen TEXT NOT NULL,
                sync_status TEXT NOT NULL,
                camera_on BOOLEAN NOT NULL DEFAULT 0
            )
        """)
        self.hb_conn.commit()

    def _on_local_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            logger.info("Connected to local MQTT broker (heartbeat)")
            client.subscribe(self.heartbeat_topic)
            logger.info(f"Subscribed to topic: {self.heartbeat_topic}")
        else:
            logger.error(f"Local MQTT connection failed with code {rc}")

    def _on_remote_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            logger.info("Connected to remote MQTT broker (EMQX)")
        else:
            logger.error(f"Remote MQTT connection failed with code {rc}")

    def _on_heartbeat(self, client, userdata, msg):
        try:
            logger.debug(f"[HEARTBEAT RECEIVED] Raw payload: {msg.payload}")
            data = json.loads(msg.payload.decode())
            camera_name = data["name"]
            timestamp = datetime.fromisoformat(data["timestamp"])
            camera_on = int(data["cam_on"])
            now = datetime.now()

            drift = abs((now - timestamp).total_seconds())
            sync_status = "good" if drift <= self.TIME_DRIFT_THRESHOLD else "out of sync"

            if sync_status == "out of sync" and self.camera_warnings.get(camera_name) != "out_of_sync":
                logger.warning(f"Camera {camera_name} clock out of sync by {drift:.2f}s")
                self.camera_warnings[camera_name] = "out_of_sync"

            self.hb_cursor.execute("""
                INSERT INTO heartbeats (camera_name, receipt_time) VALUES (?, ?)
            """, (camera_name, now.isoformat()))
            self.hb_cursor.execute("""
                INSERT INTO camera_status (camera_name, last_seen, sync_status, camera_on)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(camera_name) DO UPDATE SET 
                    last_seen = excluded.last_seen,
                    sync_status = excluded.sync_status,
                    camera_on = excluded.camera_on
            """, (camera_name, now.isoformat(), sync_status, camera_on))
            self.hb_conn.commit()

            if camera_name in self.camera_warnings and sync_status == "good":
                logger.info(f"Camera {camera_name} has recovered from sync issue.")
                self.camera_warnings.pop(camera_name, None)

        except Exception as e:
            logger.error(f"Error handling heartbeat: {e}")

    def _monitor_camera_status(self):
        while True:
            if (datetime.now() - self.startup_time).total_seconds() < self.STARTUP_GRACE_PERIOD:
                time.sleep(5)
                continue

            try:
                self.hb_cursor.execute("SELECT camera_name, last_seen, sync_status FROM camera_status")
                rows = self.hb_cursor.fetchall()
                now = datetime.now()

                for camera_name, last_seen_str, sync_status in rows:
                    last_seen = datetime.fromisoformat(last_seen_str)
                    gap = (now - last_seen).total_seconds()

                    if gap > self.TIMEOUT_THRESHOLD and sync_status == "good" and self.camera_warnings.get(camera_name) != "down":
                        logger.warning(f"{camera_name} is DOWN. Last seen: {last_seen}")
                        self.camera_warnings[camera_name] = "down"
                        self.hb_cursor.execute("""
                            UPDATE camera_status SET sync_status = ?, camera_on = 0 WHERE camera_name = ?
                        """, ("DOWN", camera_name))
                        self.hb_conn.commit()

                    elif gap <= self.TIMEOUT_THRESHOLD and self.camera_warnings.get(camera_name) == "down":
                        logger.info(f"{camera_name} has recovered from DOWN.")
                        self.camera_warnings.pop(camera_name, None)

            except Exception as e:
                logger.error(f"Error checking camera status: {e}")
            time.sleep(10)

    def _send_weather_data(self):
        while True:
            try:
                self.weather_cursor.execute("""
                    SELECT time, temperature, relative_humidity, pressure, wind_speed
                    FROM weather_data ORDER BY id DESC LIMIT 1
                """)
                row = self.weather_cursor.fetchone()
                if row:
                    ts, temp, humid, pres, wind = row
                    topic = f"{self.unit_name}/weather"
                    payload = json.dumps({
                        "time": ts,
                        "temp": temp,
                        "humid": humid,
                        "pres": pres,
                        "wind": wind
                    })
                    self.remote_client.publish(topic, payload, qos=1)
            except Exception as e:
                logger.warning(f"Failed to publish weather data: {e}")
            time.sleep(60)

    def _send_camera_status(self):
        local_conn = sqlite3.connect(self.heartbeat_db_path, check_same_thread=False)
        local_cursor = local_conn.cursor()

        while True:
            try:
                local_cursor.execute("SELECT camera_name, last_seen, sync_status, camera_on FROM camera_status")
                rows = local_cursor.fetchall()

                for camera_name, last_seen_raw, sync_status, camera_on in rows:
                    try:
                        last_seen_dt = datetime.fromisoformat(last_seen_raw)
                        last_seen = last_seen_dt.replace(microsecond=0).isoformat()
                    except Exception:
                        last_seen = last_seen_raw 

                    current = (last_seen, sync_status, camera_on)
                    cached = self.last_seen_cache.get(camera_name)

                    if cached != current:
                        topic = f"{self.unit_name}/status/{camera_name}"
                        payload = json.dumps({
                            "camera": camera_name,
                            "last_seen": last_seen,
                            "sync_status": sync_status,
                            "camera_on": bool(camera_on)
                        })
                        result = self.remote_client.publish(topic, payload, qos=1)
                        if result.rc == mqtt.MQTT_ERR_SUCCESS:
                            logger.debug(f"Published camera status for {camera_name}")
                        else:
                            logger.warning(f"Failed to publish camera status for {camera_name}: {result.rc}")
                        self.last_seen_cache[camera_name] = current

            except Exception as e:
                logger.warning(f"Failed to send camera status: {e}")

            time.sleep(60)

    def start(self):
        try:
            # Remote client setup
            self.remote_client.connect_async(self.remote_broker, self.remote_port)
            self.remote_client.loop_start()
            time.sleep(2)

            # Local client setup
            self.local_client.connect_async(self.hub_IP, 1883)
            self.local_client.loop_start()

            logger.info("MQTTManager started both local and remote clients.")

            threading.Thread(target=self._monitor_camera_status, daemon=True).start()
            threading.Thread(target=self._send_weather_data, daemon=True).start()
            threading.Thread(target=self._send_camera_status, daemon=True).start()
        except Exception as e:
            logger.error(f"Failed to start MQTTManager: {e}")

if __name__ == "__main__":
    print("[MQTTManager] Starting test")
    mqtt_mgmt = MQTTManager()
    mqtt_mgmt.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[MQTTManager] Interrupted")