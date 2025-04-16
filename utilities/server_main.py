#!/usr/bin/env python3
import os
import sys
from utilities.config import Config
from utilities.logger import logger
from utilities.display import Display
from utilities.sensors import MultiSensor
from utilities.mqtt import MQTTManager
from utilities.wittypi import WittyPi
from time import sleep
from datetime import datetime
import threading
import time
import board

class FallbackDisplay: # object that allows script to continue if disp init fails
    def display_msg(self, *args, **kwargs):
        pass
    def display_sensor_data(self, *args, **kwargs):
        pass


def run_server():
    config = Config()
    name = config['general']['name']
    sensor_freq = config['sensors'].getint('sensor_freq', fallback=5)
    db_write_freq = config['sensors'].getint('db_write_freq', fallback=60)

    logger.info("###################### INITIALIZING ##################################")

    shared_i2c = board.I2C()  # Initialize the sensors
    sensors = MultiSensor(i2c=shared_i2c)

    try: # Initialize the display
        disp = Display(i2c=shared_i2c)
        logger.debug("Display initialized successfully.")
    except:
        logger.warning('Display init failed')
        disp = FallbackDisplay()
    disp.display_msg('Initializing')

    # SCHEDULING
    try:
        with WittyPi() as wp:
            wp.apply_scheduling(config, disp)
    except Exception as e:
        logger.warning(f"Could not apply WittyPi scheduling: {e}")

    logger.info(f"Sensor frequency: {sensor_freq}s | DB write frequency: {db_write_freq}s")
    logger.debug("Begin logging data")

    stop_event = threading.Event() # Create thread stop event

    def sensor_data():
        while not stop_event.is_set():
            time_current = datetime.now()
            sensors.add_data(time_current)
            time.sleep(sensor_freq) ## HOW OFTEN DOES SENSOR DATA GET ADDED TO QUEUE

    def update_display():
        display_interval = 1
        while not stop_event.is_set():
            readings = sensors.latest_readings
            net_status = mqtt_mgmt.get_network_status()

            def safe(val, unit=""):
                return f"{val:.1f}{unit}" if val is not None else "--"
            
            disp.display_sensor_data(
                safe(readings.get("temperature"), "°C"),
                safe(readings.get("relative_humidity"), "%"),
                safe(readings.get("pressure"), "hPa"),
                safe(readings.get("wind_speed"), "m/s"),
                net_status
            )
            time.sleep(display_interval)
    
    def cleanup(reason=""):
        disp.display_msg(reason or 'Shutting down')
        stop_event.set()
        sensor_thread.join()
        display_thread.join()

        if len(list(sensors.data_dict.values())[0]) != 0:
            sensors.insert_into_db()

        mqtt_mgmt.remote_client.loop_stop()
        mqtt_mgmt.local_client.loop_stop()
        mqtt_mgmt.remote_client.disconnect()
        mqtt_mgmt.local_client.disconnect()

        logger.info(f"Script ended: {reason}")

    sleep(5)

    mqtt_mgmt = MQTTManager()
    mqtt_mgmt.start()

    sensor_thread = threading.Thread(target = sensor_data, daemon=True)
    sensor_thread.start()

    display_thread = threading.Thread(target=update_display, daemon=True)
    display_thread.start()

    try:
        curr_time = time.monotonic()

        while True:
            readings = sensors.latest_readings
            if (time.monotonic() - curr_time) >= db_write_freq:
                sensors.insert_into_db()
                curr_time = time.monotonic()
            time.sleep(0.1)

    except KeyboardInterrupt:
        cleanup("Interrupted")
        sys.exit()

    except:
        cleanup("Error")
        logger.exception("Error recording sensor data")
        sys.exit()

if __name__ == "__main__":
    run_server()