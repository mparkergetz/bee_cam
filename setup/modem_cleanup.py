#!/usr/bin/env python3
import serial
import time

try:
    ser = serial.Serial('/dev/serial0', 9600, timeout=2)
    time.sleep(1)
    ser.write(b'AT\r')
    time.sleep(1)
    ser.write(b'AT+CGDCONT=2\r')
    time.sleep(1)
    ser.write(b'AT+CGDCONT=3\r')
    time.sleep(1)
    ser.close()
    print("Modem PDP context cleanup complete.")
except Exception as e:
    print("Warning: modem cleanup failed —", e)
