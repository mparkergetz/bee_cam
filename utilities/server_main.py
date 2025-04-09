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

def run_server():
    get_config = Config()
    config = get_config.dict()
    name = config['general']['name']
    #sensor_int = get_config.getint('communication', 'sensor_int')
    MODULE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sun_times_csv = os.path.join(MODULE_ROOT, 'setup', 'sun_times.csv')

    logger.info("###################### INITIALIZING ##################################")

    # Initialize the sensors
    shared_i2c = board.I2C()
    sensors = MultiSensor(i2c=shared_i2c)

    # Initialize the display
    disp = Display(i2c=shared_i2c)
    disp.display_msg('Initializing')

    # SCHEDULING
    try:
        with WittyPi() as wp:
            wp.apply_scheduling(get_config, sun_times_csv, disp)
    except Exception as e:
        logger.warning(f"Could not apply WittyPi scheduling: {e}")

    logger.debug("Begin logging data")

    # Create thread stop event
    stop_event = threading.Event()

    def sensor_data():
        while not stop_event.is_set():
            time_current = datetime.now()
            sensors.add_data(time_current)
            time.sleep(5) ## HOW OFTEN DOES SENSOR DATA GET ADDED TO QUEUE

    def update_display():
        display_interval = 1
        while not stop_event.is_set():
            readings = sensors.latest_readings
            net_status = mqtt_mgmt.get_network_status()
            if None not in readings.values():
                disp.display_sensor_data(
                    readings["temperature"],
                    readings["relative_humidity"],
                    readings["pressure"],
                    readings["wind_speed"],
                    net_status
                )
            time.sleep(display_interval)

    sleep(5)

    mqtt_mgmt = MQTTManager()
    mqtt_mgmt.start()

    sensor_thread = threading.Thread(target = sensor_data)
    sensor_thread.start()

    display_thread = threading.Thread(target=update_display)
    display_thread.start()

    try:
        curr_time = time.monotonic()

        while True:
            readings = sensors.latest_readings
            if (time.monotonic() - curr_time) >= 10:
                sensors.insert_into_db()
                curr_time = time.monotonic()
            time.sleep(0.1)

    except KeyboardInterrupt:
        disp.display_msg('Interrupted')
        stop_event.set()
        sensor_thread.join()
        display_thread.join()
        if len(list(sensors.data_dict.values())[0]) != 0: 
            sensors.insert_into_db()

        mqtt_mgmt.client.loop_stop()
        mqtt_mgmt.client.disconnect()

        logger.info("KeyboardInterrupt")
        sys.exit()

    except:
        disp.display_msg('Error')
        stop_event.set()
        display_thread.join()
        
        logger.exception("Error recording sensor data")
        sys.exit()

if __name__ == "__main__":
    run_server()