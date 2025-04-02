#!/usr/bin/env python3

import paho.mqtt.client as mqtt
import ssl
import json
import re

# === CONFIGURATION ===
BROKER = "r00f7910.ala.us-east-1.emqxsl.com"
PORT = 8883
USERNAME = "user1"
PASSWORD = "user1pasS"
CA_CERT = "mycert.crt"  # Must be in the same directory or provide full path

TOPICS = [
    "+/weather",
    "+/status/camera/#"
]

# === CALLBACKS ===
def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print("Connected to broker.")
        for topic in TOPICS:
            client.subscribe(topic)
            print(f"Subscribed to: {topic}")
    else:
        print(f"Failed to connect, return code {rc}")

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())

        # Extract unit name from topic (e.g. "beehub/weather" → "beehub")
        topic_parts = msg.topic.split("/")
        unit_name = topic_parts[0]

        print(f"\nUnit: {unit_name}")
        print(f"Topic: {msg.topic}")
        for key, val in payload.items():
            print(f"   {key}: {val}")
    except Exception as e:
        print(f"Failed to parse message on {msg.topic}: {e}")

# === MAIN ===
def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(USERNAME, PASSWORD)
    client.tls_set(ca_certs=CA_CERT, certfile=None, keyfile=None,
                   cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLS)

    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(BROKER, PORT)
    client.loop_forever()

if __name__ == "__main__":
    main()
