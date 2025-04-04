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

    # SCHEDULING
    try:
        with WittyPi() as wp:
            if get_config.getboolean('scheduling', 'sun_sched'):
                logger.debug('setting to sun sched')
                try:
                    start_today, stop_today, start_tomorrow = wp.get_sun_times(sun_times_csv)
                    logger.debug(f'sun times: {start_today}, {stop_today}, {start_tomorrow}')
                    wp.shutdown_startup(start_today=start_today, stop_today=stop_today, start_tomorrow=start_tomorrow)
                    logger.debug('WittyPi shutdown_startup complete')
                except Exception:
                    logger.warning("Defaulting to config start/stop times")
            else:
                try:
                    start_str = config.get('settings', 'default_start')
                    stop_str = config.get('settings', 'default_stop')

                    start_time = datetime.strptime(start_str, '%H:%M:%S').time()
                    stop_time = datetime.strptime(stop_str, '%H:%M:%S').time()

                    start_dt = datetime.combine(datetime.today(), start_time)
                    stop_dt = datetime.combine(datetime.today(), stop_time)

                    wp.shutdown_startup(start_today=start_dt, stop_today=stop_dt, start_tomorrow=start_dt)
                except Exception:
                    logger.warning("Setting default times failed")
    except Exception as e:
        logger.warning(f"Could not set WittyPi schedule: {e}")

    # Initialize the sensors
    shared_i2c = board.I2C()
    sensors = MultiSensor(i2c=shared_i2c)

    # Initialize the display
    disp = Display(i2c=shared_i2c)
    disp.display_msg('Initializing')

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
            if None not in readings.values():
                disp.display_sensor_data(
                    readings["temperature"],
                    readings["relative_humidity"],
                    readings["pressure"],
                    readings["wind_speed"]
                )
            time.sleep(display_interval)

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