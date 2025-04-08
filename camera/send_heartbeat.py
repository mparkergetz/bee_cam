import paho.mqtt.client as mqtt
from time import sleep
from datetime import datetime
import os
import json
from utilities.config import Config
from utilities.logger import logger as base_logger
logger = base_logger.getChild("Heartbeat")

config = Config()
network_ip = config['communication']['network_ip']
UNIT_NAME = config['general']['name'] 
HEARTBEAT_TOPIC = "heartbeat"

mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

def connect_mqtt():
    try:
        mqtt_client.connect(network_ip, 1883, 60)
    except Exception as e:
        logger.error(f"MQTT Connection Failed: {e}")

def SendCameraHeartbeat(stop_event):
    while not stop_event.is_set():
        timestamp = datetime.now().isoformat()
        message = json.dumps({
            "name": UNIT_NAME,
            "timestamp": timestamp,
            "cam_on": 1
        })

        try:
            connect_mqtt()
            mqtt_client.publish(HEARTBEAT_TOPIC, message)
            logger.debug(f"Heartbeat sent: {message}")
        except Exception as e:
            logger.error(f"Failed to send heartbeat: {e}")

        if stop_event.wait(10):  
            break

def SendCameraShutdown():
    try:
        connect_mqtt()
        mqtt_client.publish(TOPIC, json.dumps({
            "name": UNIT_NAME,
            "timestamp": datetime.now().isoformat(),
            "cam_on": 0 
        }))

        mqtt_client.disconnect()
        logger.info(f"Camera_main stopping: {UNIT_NAME}")
    except Exception as e:
        logger.error(f"Failed to send final offline heartbeat: {e}")

def is_camera_running():
    return any("camera_main.py" in line for line in os.popen("ps aux"))

def MonitorCameraMain():
    TOPIC = "heartbeat_alert"

    while True:
        if not is_camera_running():
            timestamp = datetime.now().isoformat()
            message = json.dumps({
                "name": UNIT_NAME,
                "timestamp": timestamp,
                "error": "camera_main.py is NOT running!"
            })

            try:
                connect_mqtt()
                client.publish(TOPIC, message)
                logger.warning(f"ALERT SENT: {message}")
            except Exception as e:
                logger.error(f"Failed to send alert: {e}")
            time.sleep(60) 

if __name__ == "__main__":
    MonitorCameraMain()