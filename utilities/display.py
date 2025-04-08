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
        
    def show_message(self, msg, line_height=12):
        if not self.enabled:
            return
        image = Image.new('1', (self.width, self.height))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, self.width, self.height), outline=0, fill=0)
        
        x, y = 0, 0
        for i, item in enumerate(msg):
            draw.text((x, y), item, font=self.font, fill=255)
            y += line_height
            if i == 0:
                y += 2

        self._disp.image(image)
        self._disp.show()

    def display_sensor_data(self, temperature, humidity, pressure, wind_speed, net_status=None):
        if not self.enabled:
            return

        temp_str = f'{temperature:.1f} C' if temperature is not None else 'Temp: N/A'
        humidity_str = f'{humidity:.1f}% RH' if humidity is not None else 'Humid: N/A'
        pressure_str = f'{pressure:.1f} hPa' if pressure is not None else 'Pres: N/A'
        wind_speed_str = f'{wind_speed:.1f} m/s' if wind_speed is not None else 'Wind: N/A'

        cell_status = "Connected" if net_status and net_status.get("cell") else "Down"
        local_cams = net_status.get("local", []) if net_status else []
        local_status = ",".join(local_cams) if local_cams else "None"


        msg = [
            time.strftime('%Y-%m-%d | %H:%M:%S'),
            f'{temp_str} | {pressure_str}',
            f'{humidity_str} | {wind_speed_str}',
            f'Cell: {cell_status}',
            f'LAN: {local_status}'
        ]
        
        self.show_message(msg)


    def display_msg(self, status, img_count=None):
        if not self.enabled:
            return

        base = [time.strftime('%Y-%m-%d | %H:%M:%S')]
        
        if img_count is None:
            lines = status.splitlines()
            msg = base + lines
        else:
            msg = base + [
                status,
                f'Image count: {img_count}',
                f'IP: {self.ip}'
            ]

        self.show_message(msg)

    def display_weather(self, temp="NA", humid="NA", pres="NA", wind="NA"):
        if not self.enabled:
            return

        msg = [time.strftime('%Y-%m-%d | %H:%M:%S'),
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
