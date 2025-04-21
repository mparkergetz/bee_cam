#!/usr/bin/env python3
import os
import json
import time
from datetime import datetime
import psutil
import paho.mqtt.client as mqtt
from utilities.config import Config
from utilities.logger import logger as base_logger

logger = base_logger.getChild("camera_monitor")

def find_camera_pid():
    for proc in psutil.process_iter(['pid', 'cmdline']):
        try:
            if proc.info['cmdline'] and 'camera_main.py' in ' '.join(proc.info['cmdline']):
                return proc.info['pid']
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None

def main():
    config = Config()
    unit_name = config['general']['name']
    monitor_freq = config.getint('communication', 'monitor_freq', fallback=60)
    broker = config['communication'].get('network_ip', '192.168.2.1')

    client = mqtt.Client(client_id=f"{self.unit_name}_monitor", callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    try:
        client.connect(broker, 1883, 60)
        client.loop_start()
        logger.info("Camera_monitor connected", broker)
    except Exception as e:
        logger.error("Could not connect to MQTT broker: %s", e)
        return

    topic = "alerts"
    alert_sent = False
    cached_pid = None

    while True:
        camera_running = False

        if cached_pid:
            try:
                proc = psutil.Process(cached_pid)
                if 'camera_main.py' in ' '.join(proc.cmdline()):
                    camera_running = True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                cached_pid = None

        if not camera_running:
            cached_pid = find_camera_pid()
            camera_running = cached_pid is not None

        if not camera_running and not alert_sent:
            timestamp = datetime.now().isoformat()
            message = json.dumps({
                "name": unit_name,
                "timestamp": timestamp,
                "error": "camera_main.py is NOT running!"
            })
            try:
                client.publish(topic, message)
                logger.warning("ALERT SENT: %s", message)
                alert_sent = True
            except Exception as e:
                logger.error("Failed to publish alert: %s", e)

        elif camera_running and alert_sent:
            logger.info("camera_main.py is back online.")
            alert_sent = False

        time.sleep(monitor_freq)
