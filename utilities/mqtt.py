import os
import psutil
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
        self.is_remote_connected = False
        self.is_local_connected = False

        self.package_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        self.sensor_db_path = os.path.join(self.package_root, self.config['communication']['sensor_db'])
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
        self.camera_sync_status = {}

        # Remote client (EMQX)
        self.remote_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.remote_client.username_pw_set(self.mqtt_user, self.mqtt_pass)
        cert_path = os.path.join(os.path.dirname(__file__), "mycert.crt")
        self.remote_client.tls_set(ca_certs=cert_path)
        self.remote_client.on_connect = self._on_remote_connect

        # Local client (LAN heartbeat)
        self.local_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.local_client.on_connect = self._on_local_connect
        self.local_client.on_message = self._on_local_message

        # DB connections
        self.sensor_conn = sqlite3.connect(self.sensor_db_path, check_same_thread=False)
        self.sensor_cursor = self.sensor_conn.cursor()

        self.hb_conn = sqlite3.connect(self.heartbeat_db_path, check_same_thread=False)
        self.hb_cursor = self.hb_conn.cursor()
        self._init_heartbeat_db()

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
        self.is_local_connected = rc == 0
        if rc == 0:
            logger.info(f"Connected to local MQTT broker ({self.heartbeat_topic})")
            client.subscribe(self.heartbeat_topic)
            client.subscribe("alerts")
            logger.debug(f"Subscribed to topic: {self.heartbeat_topic}")
        else:
            logger.error(f"Local MQTT connection failed with code {rc}")

    def _on_remote_connect(self, client, userdata, flags, rc, properties=None):
        self.is_remote_connected = rc == 0
        if rc == 0:
            logger.info("Connected to remote MQTT broker (EMQX)")
        else:
            logger.error(f"Remote MQTT connection failed with code {rc}")

    def get_network_status(self):
        try:
            self.hb_cursor.execute("SELECT camera_name FROM camera_status WHERE camera_on = 1")
            active_cameras = [
            ''.join(filter(str.isdigit, row[0])) for row in self.hb_cursor.fetchall()
            ]
        except Exception as e:
            logger.warning(f"Failed to fetch active camera list: {e}")
            active_cameras = []

        return {
            "cell": self.is_remote_connected,
            "local": active_cameras
        }

    def _on_local_message(self, client, userdata, msg):
        try:
            logger.debug(f"[LOCAL MQTT RECEIVED] {msg.topic}: {msg.payload}")
            data = json.loads(msg.payload.decode())

            if msg.topic == "heartbeat":
                self._handle_heartbeat(data)
            elif msg.topic == "alerts":
                self._handle_camera_alert(data)
        except Exception as e:
            logger.error(f"Failed to process local MQTT message: {e}")
    
    def _handle_camera_alert(self, data):
        try:
            name = data.get("name", "unknown")
            timestamp = data.get("timestamp", "")
            error = data.get("error", "")

            payload = f"[ALERT from {name}] @ {timestamp}: {error}"
            logger.warning(payload)
            self.remote_client.publish("alerts", payload, qos=1)
        except Exception as e:
            logger.error(f"Failed to forward camera alert: {e}")


    def _handle_heartbeat(self, data):
        try:
            cursor = self.hb_conn.cursor()

            camera_name = data["name"]
            timestamp = datetime.fromisoformat(data["timestamp"])
            camera_on = int(data["cam_on"])
            now = datetime.now()

            drift = abs((now - timestamp).total_seconds())
            sync_status = "good" if drift <= self.TIME_DRIFT_THRESHOLD else "out of sync"

            if sync_status == "out of sync" and self.camera_sync_status.get(camera_name) != "out_of_sync":
                payload = f"{camera_name} clock OUT OF SYNC by {drift:.2f}s"
                logger.warning(payload)
                self.camera_sync_status[camera_name] = "out_of_sync"
                self.remote_client.publish('alerts', payload, qos=1)

            cursor.execute("""
                INSERT INTO heartbeats (camera_name, receipt_time) VALUES (?, ?)
            """, (camera_name, now.isoformat()))
            cursor.execute("""
                INSERT INTO camera_status (camera_name, last_seen, sync_status, camera_on)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(camera_name) DO UPDATE SET 
                    last_seen = excluded.last_seen,
                    sync_status = excluded.sync_status,
                    camera_on = excluded.camera_on
            """, (camera_name, now.isoformat(), sync_status, camera_on))
            self.hb_conn.commit()

            if camera_name in self.camera_sync_status and sync_status == "good":
                payload = f"{camera_name} is IN SYNC."
                logger.info(payload)
                self.camera_sync_status.pop(camera_name, None)
                self.remote_client.publish('alerts', payload, qos=1)

        except Exception as e:
            logger.error(f"Error handling heartbeat: {e}")

    def _monitor_camera_status(self):
        cursor = self.hb_conn.cursor()

        while True:
            if (datetime.now() - self.startup_time).total_seconds() < self.STARTUP_GRACE_PERIOD:
                time.sleep(5)
                continue

            try:
                cursor.execute("SELECT camera_name, last_seen, sync_status FROM camera_status")
                rows = cursor.fetchall()
                now = datetime.now()

                for camera_name, last_seen_str, sync_status in rows:
                    last_seen = datetime.fromisoformat(last_seen_str)
                    gap = (now - last_seen).total_seconds()

                    if gap > self.TIMEOUT_THRESHOLD and sync_status == "good" and self.camera_warnings.get(camera_name) != "down":
                        payload = f"{camera_name} is DOWN. Last seen: {last_seen}"
                        logger.warning(payload)
                        self.camera_warnings[camera_name] = "down"
                        cursor.execute("""
                            UPDATE camera_status SET sync_status = ?, camera_on = 0 WHERE camera_name = ?
                        """, ("DOWN", camera_name))
                        self.hb_conn.commit()
                        self.remote_client.publish('alerts', payload, qos=1)

                    elif gap <= self.TIMEOUT_THRESHOLD and self.camera_warnings.get(camera_name) == "down":
                        payload = f"{camera_name} is UP."
                        logger.info(payload)
                        self.camera_warnings.pop(camera_name, None)
                        cursor.execute("""
                            UPDATE camera_status SET sync_status = ?, camera_on = 1 WHERE camera_name = ?
                        """, ("good", camera_name))
                        self.hb_conn.commit()
                        self.remote_client.publish('alerts', payload, qos=1)

            except Exception as e:
                logger.error(f"Error checking camera status: {e}")
            time.sleep(10)

    def _send_sensor_data(self):
        while True:
            try:
                self.sensor_cursor.execute("""
                    SELECT time, temperature, relative_humidity, pressure, wind_speed, internal_temp
                    FROM sensor_data ORDER BY id DESC LIMIT 1
                """)
                row = self.sensor_cursor.fetchone()
                if row:
                    ts, temp, humid, pres, wind, internal_temp = row
                    topic = f"{self.unit_name}/sensors"
                    payload = json.dumps({
                        "time": ts,
                        "temp": temp,
                        "humid": humid,
                        "pres": pres,
                        "wind": wind,
                        "int_temp": internal_temp
                    })
                    self.remote_client.publish(topic, payload, qos=1)
            except Exception as e:
                logger.warning(f"Failed to publish sensor data: {e}")
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

    def send_camera_heartbeat(self, stop_event):
        while not stop_event.is_set():
            timestamp = datetime.now().isoformat()
            message = json.dumps({
                "name": self.unit_name,
                "timestamp": timestamp,
                "cam_on": 1
            })

            try:
                self.local_client.publish(self.heartbeat_topic, message)
                logger.info(f"Heartbeat sent: {message}")
            except Exception as e:
                logger.error(f"Failed to send heartbeat: {e}")

            if stop_event.wait(10):
                break

    def send_camera_shutdown(self):
        try:
            self.local_client.publish(self.heartbeat_topic, json.dumps({
                "name": self.unit_name,
                "timestamp": datetime.now().isoformat(),
                "cam_on": 0
            }))
            self.local_client.disconnect()
            logger.info(f"Camera_main stopping: {self.unit_name}")
        except Exception as e:
            logger.error(f"Failed to send final offline heartbeat: {e}")


    def is_camera_running(self):
        for proc in psutil.process_iter(['pid', 'cmdline']):
            try:
                if proc.info['cmdline'] and 'camera_main.py' in ' '.join(proc.info['cmdline']):
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return False

    def monitor_camera_main(self):
        topic = "heartbeat_alert"
        while True:
            if not self.is_camera_running():
                timestamp = datetime.now().isoformat()
                message = json.dumps({
                    "name": self.unit_name,
                    "timestamp": timestamp,
                    "error": "camera_main.py is NOT running!"
                })
                try:
                    self.remote_client.publish(topic, message)
                    logger.warning(f"ALERT SENT: {message}")
                except Exception as e:
                    logger.error(f"Failed to send alert: {e}")
            time.sleep(60)          

    def start(self):
        try:
            # Remote client setup
            self.remote_client.connect_async(self.remote_broker, self.remote_port)
            self.remote_client.loop_start()
            time.sleep(2)

            # Local client setup
            self.local_client.connect_async(self.hub_IP, 1883)
            logger.info("Trying to connect to local MQTT broker...")
            self.local_client.loop_start()

            logger.debug("MQTTManager started both local and remote clients.")

            threading.Thread(target=self._monitor_camera_status, daemon=True).start()
            threading.Thread(target=self._send_sensor_data, daemon=True).start()
            threading.Thread(target=self._send_camera_status, daemon=True).start()
        except Exception as e:
            logger.error(f"Failed to start MQTTManager: {e}")

    def connect_local(self):
        try:
            self.local_client.connect_async(self.hub_IP, 1883)
            self.local_client.loop_start()
            logger.info("Local MQTT client connected (from connect_local)")
        except Exception as e:
            logger.error(f"Error connecting local MQTT: {e}")

if __name__ == "__main__":
    MonitorCameraMain()