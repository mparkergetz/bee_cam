#!/usr/bin/env python3
import os
import sys
import logging
from utilities.config import Config
from utilities.display import Display
from utilities.sensors import MultiSensor
from .send_heartbeat import SendCameraHeartbeat, SendCameraShutdown
import board

from picamera2 import Picamera2
from time import sleep
from datetime import datetime
import threading
import time

def run_camera():
    config = Config()
    name = config['general']['name'] 

    size = (config['imaging'].getint('w'), config['imaging'].getint('h'))
    lens_position = config['imaging'].getfloat('lens_position')
    img_count = 0

    # set main and sub output dirs
    MODULE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    main_dir = os.path.join(MODULE_ROOT, "data")
    os.makedirs(main_dir, exist_ok=True)
    date_folder = str(datetime.now().strftime("%Y-%m-%d"))
    curr_date = os.path.join(main_dir, date_folder)
    os.makedirs(curr_date , exist_ok=True)

    path_image_dat = os.path.join(curr_date,'images') # image data will save to a sub directory 'images'
    os.makedirs(path_image_dat, exist_ok=True)
    
    shared_i2c = board.I2C()
    sensors = MultiSensor(curr_date, i2c=shared_i2c) # Initialize the sensors

    disp = Display()
    disp.display_msg('Initializing')

    # Configure logging
    log_dir = os.path.join(MODULE_ROOT, "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "camera_main.log")
    logging.basicConfig(filename=log_file, level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    logging.info("###################### NEW RUN ##################################")

    MAX_RETRIES = 3

    for attempt in range(MAX_RETRIES):
        try:
            camera = Picamera2()
            cam_config = camera.create_still_configuration({'size': size})
            camera.configure(cam_config)
            camera.exposure_mode = 'sports'
            camera.set_controls({"LensPosition": lens_position})
            camera.start()
            sleep(5)
            break
        except Exception as e:
            logging.error(f"Camera init attempt {attempt+1} failed: {e}")
            sleep(2)
    else:
        disp.display_msg('Cam init failed', img_count)
        sys.exit()

    os.chdir(curr_date)
    logging.info("Imaging...")

    def sensor_data():
        while not stop_event.is_set():
            sensors.add_data(datetime.now())
            if stop_event.wait(2):
                break

    def capture_image(time_current_split):
        event.wait()
        camera.capture_file('images/'+name + '_' + time_current_split + '.jpg')
        logging.debug("Image acquired: %s", time_current_split)

    def cleanup():
        stop_event.set()
        if sensor_thread.is_alive():
            sensor_thread.join()
        if heartbeat_thread.is_alive():
            heartbeat_thread.join()
        if len(list(sensors.data_dict.values())[0]) != 0:
            sensors.append_to_csv()
        sensors.sensors_deinit()
        logging.info("Sensors deinit, Exiting.")
        SendCameraShutdown()

### SET UP THREADING
    stop_event = threading.Event()

    sensor_thread = threading.Thread(target = sensor_data, daemon=True)
    sensor_thread.start()

    heartbeat_thread = threading.Thread(target=SendCameraHeartbeat, args=(stop_event,), daemon=True)
    heartbeat_thread.start()

    event = threading.Event()

    MAX_RETRIES = 3
    retry_count = 0
    curr_time = time.time()

    while True:

        try:
            disp.display_msg('Imaging!', img_count)

            event.set()
            time_current = datetime.now()
            time_current_split = str(time_current.strftime("%Y%m%d_%H%M%S"))
            
            capture_thread = threading.Thread(target=capture_image, args=(time_current_split,))
            capture_thread.start()

            capture_thread.join(timeout=3) 
            if capture_thread.is_alive(): # If thread is still alive after 3 seconds, it's probably hung
                raise TimeoutError("Camera operation took too long!")
            event.clear()
            
            img_count += 1
            retry_count = 0
        
            # if wanting a delay in saving sensor data:
            if (time.time()-curr_time) >= 30:
                sensors.append_to_csv()
                curr_time = time.time()
            sleep(.7)

        except KeyboardInterrupt:
            stop_event.set()  # stop sensor thread
            sensor_thread.join() 

            if len(list(sensors.data_dict.values())[0]) != 0: # if list is not empty then add data
                sensors.append_to_csv()
            
            disp.display_msg('Interrupted', img_count)
            logging.info("KeyboardInterrupt")
            cleanup()
            sys.exit()

        except TimeoutError:
            retry_count += 1
            disp.display_msg('Cam Timeout!', img_count)
            logging.error("Camera operation timeout!")
            if retry_count >= MAX_RETRIES:
                disp.display_msg('Max retries reached!', img_count)
                logging.error("Max retries reached. Exiting...")
                sys.exit()
            else:
                sleep(2) # Wait for a bit before attempting a retry
                continue

        except Exception as e:
            disp.display_msg('Error', img_count)
            logging.exception("Error capturing image: %s", str(e))
            cleanup()
            sys.exit()

if __name__ == "__main__":
    run_camera()