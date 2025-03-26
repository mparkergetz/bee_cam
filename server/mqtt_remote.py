import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import paho.mqtt.client as mqtt
import sqlite3
import time
import json
import threading
from utilities.config import Config


config = Config()
unit_name =config['general']['name']

package_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
db_relative_path = config['communication']['weather_db']
DB_PATH = os.path.join(package_root, db_relative_path)

REMOTE_BROKER = "r00f7910.ala.us-east-1.emqxsl.com"
REMOTE_PORT = 8883
MQTT_USER = "user1"
MQTT_PASS = "user1pasS"
CERT_PATH = "/home/pi/bee_cam/server/mycert.crt"

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cur = conn.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT,
    payload TEXT,
    qos INTEGER,
    sent INTEGER DEFAULT 0
)
""")
conn.commit()

def store_message(topic, payload, qos):
    cur.execute("INSERT INTO messages (topic, payload, qos, sent) VALUES (?, ?, ?, 0)", 
                (topic, payload, qos))
    conn.commit()

def mark_sent(msg_id):
    cur.execute("UPDATE messages SET sent = 1 WHERE id = ?", (msg_id,))
    conn.commit()

def resend_unsent():
    while True:
        try:
            cur.execute("SELECT id, topic, payload, qos FROM messages WHERE sent = 0")
            rows = cur.fetchall()
            for row in rows:
                msg_id, topic, payload, qos = row
                result = remote_client.publish(topic, payload, qos=qos)
                if result.rc == mqtt.MQTT_ERR_SUCCESS:
                    mark_sent(msg_id)
        except Exception as e:
            pass  # Keep trying
        time.sleep(RELAY_INTERVAL)

def test_connection():
    test_topic = f"{unit_name}/status/test"
    test_payload = json.dumps({"status": "online", "timestamp": int(time.time())})
    result = remote_client.publish(test_topic, test_payload, qos=1)
    return result.rc == mqtt.MQTT_ERR_SUCCESS

if __name__ == "__main__":
    remote_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    remote_client.username_pw_set(MQTT_USER, MQTT_PASS)
    remote_client.tls_set(ca_certs=CERT_PATH)
    remote_client.connect_async(REMOTE_BROKER, REMOTE_PORT)
    remote_client.loop_start()

    while True:
        test_connection()
        time.sleep(1)

