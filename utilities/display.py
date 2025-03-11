import sys
import time
from PIL import Image, ImageDraw, ImageFont
import adafruit_ssd1306
import socket
import os
import board

class Display:
    def __init__(self, i2c=None):
        self.width = 128
        self.height = 64
        self.font = ImageFont.load_default()
        self.enabled = True # set to False on error
        self.ip = self.get_ip_address()
        self._i2c = i2c if i2c is not None else board.I2C()
        try:
            self._disp = adafruit_ssd1306.SSD1306_I2C(self.width,self.height, self._i2c)
            self._disp.fill(0)
            self._disp.show()
        except RuntimeError as e:
            print(f'Display: {e}', file=sys.stderr)
            self.enabled = False
        
    def show_message(self, msg, line_height=14):
        if not self.enabled:
            return
        image = Image.new('1', (self.width, self.height))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, self.width, self.height), outline=0, fill=0)
        
        x, y = 0, 0
        for item in msg:
            draw.text((x, y), item, font=self.font, fill=255)
            y += line_height

        self._disp.image(image)
        self._disp.show()

    def display_sensor_data(self, temperature, humidity, pressure, wind_speed):
        if not self.enabled:
            return

        temp_str = f'Temp: {temperature:.1f} C' if temperature is not None else 'Temp: N/A'
        humidity_str = f'Humid: {humidity:.1f}%' if humidity is not None else 'Humid: N/A'
        pressure_str = f'Pres: {pressure:.1f} hPa' if pressure is not None else 'Pres: N/A'
        wind_speed_str = f'Wind: {wind_speed:.1f} m/s' if wind_speed is not None else 'Wind: N/A'


        msg = [
            time.strftime('%Y-%m-%d | %H:%M:%S'),
            temp_str,
            humidity_str,
            pressure_str,
            wind_speed_str
        ]
        
        self.show_message(msg)


    def display_msg(self, status):
        if not self.enabled:
            return

        msg = [time.strftime('%H:%M:%S'),
                f'{status}',
                f'IP: {self.ip}']

        self.show_message(msg)

    def display_weather(self, temp="NA", humid="NA", pres="NA", wind="NA"):
        if not self.enabled:
            return

        msg = [time.strftime('%H:%M:%S'),
                f'Temp: {temp} C   Humid: {humid}%',
                f'Pres: {pres} kPa, Wind: {wind} m/s',
                f'IP: {self.ip}']

        self.show_message(msg)

    def clear_display(self):
        if not self.enabled:
            return
        self._disp.fill(0)
        self._disp.show()

    def get_ip_address(self):
        try:
            hostname = socket.gethostname()
            result = os.popen(f"ifconfig eth0").read()
            IPAddr = result.split("inet ")[1].split()[0]
            return f'{IPAddr}'
        except:
            return "Unknown"

    def disp_deinit(self):
        self.clear_display()
        self._i2c.deinit()

if __name__ == '__main__':
    disp = Display()
    ip = disp.get_ip_address()

    try:
        while True:
            disp.display_weather()
            current_second_fraction = time.time() % 1
            sleep_duration = 1 - current_second_fraction
            time.sleep(sleep_duration)
    except KeyboardInterrupt:
        disp.clear_display()

    finally:
        disp.clear_display()
