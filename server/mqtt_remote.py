import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import time
import json
import threading
import sqlite3
import paho.mqtt.client as mqtt
from utilities.config import Config

class MQTTRemote:
    def __init__(self):
        self.config = Config()
        self.unit_name = self.config['general']['name']

        self.package_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        mqtt_db = self.config['communication']['mqtt_db']
        weather_db = self.config['communication']['weather_db']
        self.weather_db_path = os.path.join(self.package_root, weather_db)
        self.heartbeat_db = os.path.join(self.package_root, mqtt_db)
        
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.cert_path = os.path.join(script_dir, "mycert.crt")
        self.remote_broker = "r00f7910.ala.us-east-1.emqxsl.com"
        self.remote_port = 8883
        self.mqtt_user = "user1"
        self.mqtt_pass = "user1pasS"

        self.relay_interval = 1

        self.mqtt_conn = sqlite3.connect(self.heartbeat_db, check_same_thread=False)
        self.mqtt_cursor = self.mqtt_conn.cursor()
        self._setup_db()

        self.weather_conn = sqlite3.connect(self.weather_db_path, check_same_thread=False)
        #self.weather_conn.execute("PRAGMA journal_mode=WAL")
        self.weather_cursor = self.weather_conn.cursor()

        self.remote_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.remote_client.username_pw_set(self.mqtt_user, self.mqtt_pass)
        self.remote_client.tls_set(ca_certs=self.cert_path)

    def _setup_db(self):
        self.mqtt_cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT,
            payload TEXT,
            qos INTEGER,
            sent INTEGER DEFAULT 0
        )
        """)
        self.mqtt_conn.commit()

    def store_message(self, topic, payload, qos):
        self.mqtt_cursor.execute("INSERT INTO messages (topic, payload, qos, sent) VALUES (?, ?, ?, 0)",
                         (topic, payload, qos))
        self.mqtt_conn.commit()

    def mark_sent(self, msg_id):
        self.mqtt_cursor.execute("UPDATE messages SET sent = 1 WHERE id = ?", (msg_id,))
        self.mqtt_conn.commit()

    def test_connection(self):
        topic = f"{self.unit_name}/status/test"
        payload = json.dumps({"status": "online", "timestamp": int(time.time())})
        result = self.remote_client.publish(topic, payload, qos=1)
        return result.rc == mqtt.MQTT_ERR_SUCCESS

    def resend_unsent(self):
        while True:
            try:
                self.mqtt_cursor.execute("SELECT id, topic, payload, qos FROM messages WHERE sent = 0")
                rows = self.mqtt_cursor.fetchall()
                for msg_id, topic, payload, qos in rows:
                    result = self.remote_client.publish(topic, payload, qos=qos)
                    if result.rc == mqtt.MQTT_ERR_SUCCESS:
                        self.mark_sent(msg_id)
            except Exception:
                pass
            time.sleep(self.relay_interval)

    def send_weather_data(self):
        while True:
            try:
                ## SENDS ALL UNSENT WEATHER UPDATES
                # self.weather_cursor.execute("SELECT id, time, temperature, relative_humidity, pressure, wind_speed FROM weather_data WHERE sent = 0")
                # rows = self.weather_cursor.fetchall()
                # for row in rows:

                ## JUST SENDS LATEST WEATHER STATUS
                self.weather_cursor.execute("""
                    SELECT id, time, temperature, relative_humidity, pressure, wind_speed
                    FROM weather_data
                    ORDER BY id DESC
                    LIMIT 1
                """)
                row = self.weather_cursor.fetchone()
                if row:
                    id_, ts, temp, hum, pres, wind = row
                    topic = f"{self.unit_name}/weather"
                    payload = json.dumps({
                        "time": ts,
                        "temp": temp,
                        "humid": hum,
                        "pres": pres,
                        "wind": wind
                    })
                    self.store_message(topic, payload, qos=1)
            except Exception:
                pass
            time.sleep(60)

    def send_camera_status(self):
        hb_conn = sqlite3.connect(self.heartbeat_db)
        hb_cursor = hb_conn.cursor()
        last_seen_cache = {}

        while True:
            try:

                hb_cursor.execute("SELECT camera_name, last_seen, sync_status, camera_on FROM camera_status")
                rows = hb_cursor.fetchall()
                for row in rows:
                    camera_name, last_seen, sync_status, camera_on = row
                    last_payload = last_seen_cache.get(camera_name)
                    current_payload = (last_seen, sync_status, camera_on)

                    if current_payload != last_payload:
                        topic = f"{self.unit_name}/status/camera/{camera_name}"
                        payload = json.dumps({
                            "camera": camera_name,
                            "last_seen": last_seen,
                            "sync_status": sync_status,
                            "camera_on": bool(camera_on)
                        })
                        self.store_message(topic, payload, qos=1)
                        last_seen_cache[camera_name] = current_payload
            except Exception:
                pass
            time.sleep(600)

    def start(self):
        self.remote_client.connect_async(self.remote_broker, self.remote_port)
        self.remote_client.loop_start()

        time.sleep(2)

        if not self.test_connection():
            print("MQTT connection test failed.")
            return

        threading.Thread(target=self.resend_unsent, daemon=True).start()
        threading.Thread(target=self.send_weather_data, daemon=True).start()
        threading.Thread(target=self.send_camera_status, daemon=True).start()

        while True:
            time.sleep(1)


if __name__ == "__main__":
    relay = MQTTRemote()
    relay.start()
