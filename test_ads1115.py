import board
import busio
i2c = busio.I2C(board.SCL, board.SDA)
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn

ads = ADS.ADS1115(i2c)
chan = AnalogIn(ads, ADS.P0, ADS.P1)

V = chan.voltage - 0.00575

if V < 0.41:
    wind_speed = 0.0
else:
    wind_speed = ((V - 0.4) / 1.6) * 32.4

print(f'Voltage: {chan.voltage}')
print(f"Wind speed: {wind_speed:.2f} m/s")