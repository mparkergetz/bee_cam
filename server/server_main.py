#!/usr/bin/env python3
import os
import sys
import logging
from utilities.config import Config
from utilities.display import Display
from utilities.sensors import MultiSensor
from .mqtt_local import MonitorHeartbeat
from .mqtt_remote import MQTTRemote
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
    #output_dir = os.path.abspath(config['general']['output_dir'])

    # curr_date = os.path.join(output_dir, name, str(datetime.now().strftime("%Y%m%d")))
    # name_dir = os.path.join(output_dir, name)
    # os.makedirs(name_dir, exist_ok=True)

    # Initialize the sensors
    shared_i2c = board.I2C()
    sensors = MultiSensor(i2c=shared_i2c)

    # Initialize the display
    disp = Display(i2c=shared_i2c)
    disp.display_msg('Initializing')

    # Configure logging
    log_dir = os.path.join(MODULE_ROOT, "logs")
    #print(log_dir)
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "server_main.log")
    logging.basicConfig(filename=log_file, level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    logging.info("###################### NEW RUN ##################################")
    logging.info("Begin logging data")

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
            if None not in readings.values():
                disp.display_sensor_data(
                    readings["temperature"],
                    readings["relative_humidity"],
                    readings["pressure"],
                    readings["wind_speed"]
                )
            time.sleep(display_interval)

    heartbeat_thread = threading.Thread(target=MonitorHeartbeat, daemon=True)
    heartbeat_thread.start()

    sensor_thread = threading.Thread(target = sensor_data)
    sensor_thread.start()

    display_thread = threading.Thread(target=update_display)
    display_thread.start()

    try:
        curr_time = time.monotonic()

        while True:
            readings = sensors.latest_readings

            disp.display_sensor_data(
                readings["temperature"],
                readings["relative_humidity"],
                readings["pressure"],
                readings["wind_speed"]
            )

            if (time.monotonic() - curr_time) >= 10:
                #print(psutil.cpu_percent(interval=1), "% CPU Usage")
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
        
        
        logging.info("KeyboardInterrupt")
        sys.exit()

    except:
        disp.display_msg('Error')
        stop_event.set()
        display_thread.join()
        
        logging.exception("Error recording sensor data")
        sys.exit()

if __name__ == "__main__":
    run_server()