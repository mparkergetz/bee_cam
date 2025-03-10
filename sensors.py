from datetime import datetime,timedelta
import os
import sys
import time

import socket
import fcntl
import struct

import board
from csv import DictWriter

from smbus2 import SMBus
import adafruit_sht31d # temp humidity
import adafruit_bmp3xx # pressure
import adafruit_mcp3421.mcp3421 as ADC # anemometer adc
from adafruit_mcp3421.analog_in import AnalogIn

from PIL import Image, ImageDraw, ImageFont
import adafruit_ssd1306 # display

from display import Display
from config import Config
config = Config()
name = config['general']['name']  

class Sensor:
    data_dict = {"name": [], "time": []}
    def __init__(self, device=None, i2c=None):
         self.i2c = i2c if i2c is not None else board.I2C()
         self.sensor_device = device
         self.failed = False

    def get_data(self,sensor_type):
        """
        Depending on the child class sensor device get_data will be
        used in order to grab the current sensor reading from the sensor.
        """
        if self.failed:
            return None
        try:
            data = getattr(self.sensor_device, sensor_type)
            return data
        except Exception as e:
            logging.error(f"Error retrieving {sensor_type} data: {e}")
            self.failed = True
            return None

    def add_data(self,sensor_type):
        """
        Add data into the dictionary under the key of the sensor type
        Also returns the current data that was recieved in case that wants to be examined
        """
        data = self.get_data(sensor_type)
        if data is not None:
            self.data_dict.setdefault(sensor_type, []).append(data)
        return data

    def display(self):
        """
        Display the sensor dictionary
        """
        print("Sensor Data")
        d = self.data_dict
        print(d)

    def sensor_deinit(self):
        self.i2c.deinit() 

class TempRHSensor(Sensor):
    def __init__(self, i2c=None):
        try:
            super().__init__(adafruit_sht31d.SHT31D(i2c if i2c else board.I2C()), i2c)
            self.sensor_types = ['temperature', 'relative_humidity']
        except Exception as e:
            logging.error(f"Temperature/Humidity Sensor Initialization Failed: {e}")
            self.failed = True  

    def temp_rh_data(self):
        if self.failed:
            return None, None
        return self.add_data(self.sensor_types[0]), self.add_data(self.sensor_types[1])

class PresSensor(Sensor):
    def __init__(self, i2c=None):
        try:
            super().__init__(adafruit_bmp3xx.BMP3XX_I2C(i2c if i2c else board.I2C()), i2c)
            self.sensor_types = ['pressure']
        except Exception as e:
            logging.error(f"Pressure Sensor Initialization Failed: {e}")
            self.failed = True

    def pressure_data(self):
        if self.failed:
            return None
        return self.add_data(self.sensor_types[0])


def map_range(value, in_min, in_max, out_min, out_max):
    return out_min + (value - in_min) * (out_max - out_min) / (in_max - in_min)

def adc_to_wind_speed(val):
    """Convert MCP3421 18-bit ADC value to wind speed in m/s with offset correction."""
    voltage_val = (val / 131072) * 2.048 
    corrected_voltage = max(voltage_val - 0.0053, 0.4) 
    return (corrected_voltage - 0.4) * (32.4 / (2.0 - 0.4))  

class WindSensor(Sensor):
    def __init__(self, i2c=None):
        super().__init__(i2c=i2c)
        self.adc = ADC.MCP3421(self.i2c, gain=1, resolution=18, continuous_mode=True)
        self.adc_channel = AnalogIn(self.adc)

    def get_data(self, sensor_type="wind_speed"):
        adc_val = self.adc_channel.value
        return adc_to_wind_speed(adc_val)

    def add_data(self, sensor_type="wind_speed"):
        data = self.get_data(sensor_type)
        self.data_dict.setdefault(sensor_type, []).append(data)
        return data

class MultiSensor(Sensor):
    """
    Class that holds the various different sensors for acquiring data
    """
    def __init__(self, path_sensors, i2c=None):
        """
        Initialize the different sensor classes
        """
        super().__init__(i2c=i2c)
        self.unit_name = name
        self._temp_rh = TempRHSensor(i2c=i2c)
        self._pres = PresSensor(i2c=i2c)
        self._ws = WindSensor(i2c=i2c)

        with WittyPi() as witty:
            self._shutdown_dt = witty.get_shutdown_datetime() 

        start_time= datetime.now().strftime('%Y%m%d_%H%M%S')
        self.filename = f'{path_sensors}.csv'# all data is written to this CSV...

        self.latest_readings = {
            "temperature": None, "relative_humidity": None,
            "pressure": None, "wind_speed": None
        }

    # def get_shutdown_datetime(self):
    #     return self._shutdown_dt

    def add_data(self,date_time):
        """
        Collect sensor data, store it in the dictionary, and update latest readings.
        """
        # check that time is in proper range based on wittyPi set shutdown time
        if self._shutdown_dt >= date_time:
            time_current_split = str(date_time.strftime("%Y%m%d_%H%M%S"))
            self.data_dict['time'].append(time_current_split)
            self.data_dict["name"].append(self.unit_name)

            ## Add Temperature and Humidity
            self.latest_readings["temperature"], self.latest_readings["relative_humidity"] = self._temp_rh.temp_rh_data()
            self.latest_readings["pressure"] = self._pres.pressure_data()
            self.latest_readings["wind_speed"] = self._ws.add_data()
        else:
            raise ShutdownTime

    def append_to_csv(self):
        """
        Write collected sensor data to CSV file.
        """
        if not os.path.exists(self.filename):  # create the csv with headers..
            with open(self.filename, 'w') as data_file:
                    csv_writer = DictWriter(data_file, fieldnames =self.data_dict.keys())
                    csv_writer.writeheader()

        with open(self.filename, 'a') as data_file:
            try: # Try to pass the dictionary into the csv 
                csv_writer = DictWriter(data_file, fieldnames =self.data_dict.keys())
                rows = []
                print(self.data_dict)
                len_list = len(next(iter(self.data_dict.values())))
                for t in range(len_list):
                    rows.append({k: self.data_dict[k][t] for k in self.data_dict.keys()})
                csv_writer.writerows(rows)
            
                for k in self.data_dict: # reset data_dict keys
                    self.data_dict[k] = []

                print("~*csv updated*~")

            except Exception as e:
                print(f"An error occurred while appending to the CSV file: {e}")

    def sensors_deinit(self):
        print("Deinitializing I2C Bus")
        self._temp_rh.sensor_deinit()
        self._pres.sensor_deinit()
        self._ws.sensor_deinit()
        # self._disp.sensor_deinit()
        print("Finished Denitializing I2C Bus...Reading for Reboot")

if __name__ == "__main__":
    print("Starting Sensor Monitoring...")

    shared_i2c = board.I2C()
    sensors = MultiSensor(path_sensors="/home/pi/data/", i2c=shared_i2c)
    display = Display(i2c=shared_i2c)

    start_time = time.time()  # Initialize start_time before entering the loop

    try:
        while True:
            time.sleep(2)  # Sample interval
            time_current = datetime.now()

            # Get sensor readings
            sensors.add_data(time_current)
            temp = sensors._temp_rh.get_data('temperature')
            humidity = sensors._temp_rh.get_data('relative_humidity')
            pressure = sensors._pres.get_data('pressure')
            wind_speed = sensors._ws.get_data()

            # Display readings on OLED screen
            display.display_sensor_data(temp, humidity, pressure, wind_speed)

            # Save to CSV every 10 seconds
            if (time.time() - start_time) >= 10:
                sensors.append_to_csv()
                start_time = time.time()  # Reset timer

    except KeyboardInterrupt:
        print("Exiting Program...")
        display.clear_display()
        sensors.sensors_deinit()

