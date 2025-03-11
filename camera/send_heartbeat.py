import paho.mqtt.client as mqtt
import time
from datetime import datetime
import logging
import os
import json

HUB_IP = "192.168.2.1"
TOPIC = "heartbeat"
SENSOR_NAME = "cam01"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

def is_camera_running():
    return any("control.py" in line for line in os.popen("ps aux"))

while True:
    timestamp = datetime.now().isoformat()
    camera_status = 1 if is_camera_running() else 0
    message = json.dumps({"name": SENSOR_NAME,"timestamp": timestamp,"cam_on": camera_status})

    try:
        client.connect(HUB_IP, 1883, 60)
        client.publish(TOPIC, message)
        client.disconnect()
        #print(f"Heartbeat sent: {message}")
        logging.info(f"Heartbeat sent: {message}")
    except Exception as e:
        #print("Failed to send heartbeat:", e)
        logging.error(f"Failed to send heartbeat: {e}")

    time.sleep(10)
