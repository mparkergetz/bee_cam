from datetime import datetime,timedelta
import os
import sys
import time
import sqlite3

import socket
import fcntl
import struct

import board
from csv import DictWriter

from smbus2 import SMBus

from PIL import Image, ImageDraw, ImageFont
import adafruit_ssd1306 # display

from utilities.logger import logger as base_logger
logger = base_logger.getChild("Sensors")

from utilities.display import Display
from utilities.config import Config
from utilities.wittypi import WittyPi

config = Config()
package_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

name = config['general']['name']
mode = config['general']['mode']

db_relative_path = config['communication']['weather_db']
db_path = os.path.join(package_root, db_relative_path)

if mode == 'server':
    import adafruit_sht31d # temp humidity
    import adafruit_bmp3xx # pressure
    # import adafruit_mcp3421.mcp3421 as ADC # anemometer adc
    # from adafruit_mcp3421.analog_in import AnalogIn
    import adafruit_ads1x15.ads1115 as ADS
    from adafruit_ads1x15.analog_in import AnalogIn

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
            logger.error(f"Error retrieving {sensor_type} data: {e}")
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
        if self.i2c is not None:
                self.i2c.deinit() 

class TempRHSensor(Sensor):
    def __init__(self, i2c=None):
        try:
            super().__init__(adafruit_sht31d.SHT31D(i2c if i2c else board.I2C()), i2c)
            self.sensor_types = ['temperature', 'relative_humidity']
        except Exception as e:
            logger.error(f"Temperature/Humidity Sensor Initialization Failed: {e}")
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
            logger.error(f"Pressure Sensor Initialization Failed: {e}")
            self.failed = True

    def pressure_data(self):
        if self.failed:
            return None
        return self.add_data(self.sensor_types[0])


def map_range(value, in_min, in_max, out_min, out_max):
    return out_min + (value - in_min) * (out_max - out_min) / (in_max - in_min)

# def adc_to_wind_speed(val):
#     """Convert MCP3421 18-bit ADC value to wind speed in m/s with offset correction."""
#     voltage_val = (val / 131072) * 2.048 
#     corrected_voltage = max(voltage_val - 0.0053, 0.4) 
#     return (corrected_voltage - 0.4) * (32.4 / (2.0 - 0.4))  

def adc_to_wind_speed(voltage_val):
    V = max(voltage_val - 0.00575, 0.4)
    return ((V - 0.4) / 1.6) * 32.4

# class WindSensor(Sensor):
#     def __init__(self, i2c=None):
#         try:
#             super().__init__(i2c=i2c)
#             self.adc = ADC.MCP3421(self.i2c, gain=1, resolution=18, continuous_mode=True)
#             self.adc_channel = AnalogIn(self.adc)
#             self.failed = False
#         except Exception as e:
#             logger.error(f"Wind Sensor Initialization Failed: {e}")
#             self.failed = True

#     def get_data(self, sensor_type="wind_speed"):
#         if self.failed:
#             return None
#         try:
#             adc_val = self.adc_channel.value
#             return adc_to_wind_speed(adc_val)
#         except Exception as e:
#             logger.error(f"Failed to get wind sensor data: {e}")
#             return None

#     def add_data(self, sensor_type="wind_speed"):
#         if self.failed:
#             return None
#         try:
#             data = self.get_data(sensor_type)
#             if data is not None:
#                 self.data_dict.setdefault(sensor_type, []).append(data)
#             return data
#         except Exception as e:
#             logger.error(f"Failed to add wind sensor data: {e}")
#             return None

class WindSensor(Sensor):
    def __init__(self, i2c=None):
        try:
            super().__init__(i2c=i2c)
            self.adc = ADS.ADS1115(self.i2c)
            self.adc_channel = AnalogIn(self.adc, ADS.P0, ADS.P1)
            self.failed = False
        except Exception as e:
            logger.error(f"Wind Sensor (ADS1115) Initialization Failed: {e}")
            self.failed = True

    def get_data(self, sensor_type="wind_speed"):
        if self.failed:
            return None
        try:
            voltage = self.adc_channel.voltage
            return adc_to_wind_speed(voltage)
        except Exception as e:
            logger.error(f"Failed to get wind sensor data: {e}")
            return None

    def add_data(self, sensor_type="wind_speed"):
        if self.failed:
            return None
        try:
            data = self.get_data(sensor_type)
            if data is not None:
                self.data_dict.setdefault(sensor_type, []).append(data)
            return data
        except Exception as e:
            logger.error(f"Failed to add wind sensor data: {e}")
            return None


class MultiSensor(Sensor):
    """
    Class that holds the various different sensors for acquiring data
    """
    def __init__(self, db_path=db_path, i2c=None):
        """
        Initialize the different sensor classes
        """
        super().__init__(i2c=i2c)
        self.unit_name = name

        if mode == 'server':
            self._temp_rh = TempRHSensor(i2c=i2c)
            self._pres = PresSensor(i2c=i2c)
            self._ws = WindSensor(i2c=i2c)

            self.sql_conn = sqlite3.connect(db_path, check_same_thread=False)
            #self.sql_conn.execute("PRAGMA journal_mode=WAL")
            self.sql_cursor = self.sql_conn.cursor()
            self.sql_cursor.execute("""
                CREATE TABLE IF NOT EXISTS weather_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT,
                    time TEXT,
                    temperature REAL,
                    relative_humidity REAL,
                    pressure REAL,
                    wind_speed REAL
                )
            """)
            self.sql_conn.commit()

        #elif mode == 'camera':  # ADD LUX DB DATA SAVE HERE
            
        # with WittyPi() as witty: ### REMOVED TO CLEAN, UPTIME CONTROLLED EXTERNALLY
        #     self._shutdown_dt = witty.get_shutdown_datetime() 

        start_time= datetime.now().strftime('%Y%m%d_%H%M%S')

        self.latest_readings = {
            "temperature": None, "relative_humidity": None,
            "pressure": None, "wind_speed": None
        }

    def add_data(self,date_time):
        # if self._shutdown_dt >= date_time: # UNCOMMENT & FIX INDENTS IF CONTINUED SAVING IS PROBLEMATIC
        timestamp = date_time.strftime("%Y%m%d_%H%M%S")
        self.data_dict['time'].append(timestamp)
        self.data_dict["name"].append(self.unit_name)

        if mode == 'server':
            self.latest_readings["temperature"], self.latest_readings["relative_humidity"] = self._temp_rh.temp_rh_data()
            self.latest_readings["pressure"] = self._pres.pressure_data()
            self.latest_readings["wind_speed"] = self._ws.add_data()

            for k, v in self.latest_readings.items():
                self.data_dict.setdefault(k, []).append(v)

        # else:
        #     raise ShutdownTime

    def insert_into_db(self):
        try:
            len_list = len(next(iter(self.data_dict.values())))
            for i in range(len_list):
                row = {k: self.data_dict[k][i] for k in self.data_dict}
                self.sql_cursor.execute("""
                    INSERT INTO weather_data (name, time, temperature, relative_humidity, pressure, wind_speed)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    row.get("name"),
                    row.get("time"),
                    row.get("temperature"),
                    row.get("relative_humidity"),
                    row.get("pressure"),
                    row.get("wind_speed")
                ))
            self.sql_conn.commit()

            for k in self.data_dict:
                self.data_dict[k] = []

        except Exception as e:
            print(f"An error occurred while inserting into DB: {e}")

    def sensors_deinit(self):
        if hasattr(self, '_temp_rh'): self._temp_rh.sensor_deinit()
        if hasattr(self, '_pres'): self._pres.sensor_deinit()
        if hasattr(self, '_ws'): self._ws.sensor_deinit()
        self.sql_conn.close()
        print("Deinitialized")

if __name__ == "__main__":
    print("Starting Sensor Monitoring...")

    shared_i2c = board.I2C()
    sensors = MultiSensor(db_path=db_path, i2c=shared_i2c)
    display = Display(i2c=shared_i2c)

    start_time = time.time()  # Initialize start_time before entering the loop

    try:
        while True:
            time.sleep(2)  # Sample interval
            time_current = datetime.now()

            sensors.add_data(time_current)
            temp = sensors._temp_rh.get_data('temperature')
            humidity = sensors._temp_rh.get_data('relative_humidity')
            pressure = sensors._pres.get_data('pressure')
            wind_speed = sensors._ws.get_data()

            display.display_sensor_data(temp, humidity, pressure, wind_speed)

            # Save to CSV every 10 seconds
            if (time.time() - start_time) >= 10:
                sensors.insert_into_db()
                start_time = time.time()

    except KeyboardInterrupt:
        print("Exiting Program...")
        display.clear_display()
        sensors.sensors_deinit()

