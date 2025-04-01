import serial
import time
import subprocess
import os
import RPi.GPIO as GPIO

lockfile = "/var/lock/LCK..serial0"
if os.path.exists(lockfile):
    os.remove(lockfile)

def ppp0_up():
    result = subprocess.run(['ip', 'link', 'show', 'ppp0'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return result.returncode == 0

def modem_responds(max_attempts=5):
    for attempt in range(max_attempts):
        try:
            ser = serial.Serial('/dev/serial0', 9600, timeout=1)
            ser.write(b'AT\r')
            time.sleep(1)
            ser.write(b'AT\r')
            time.sleep(1)
            ser.write(b'AT\r')
            time.sleep(1)
            if ser.inWaiting():
                time.sleep(0.01)
                recBuff = ser.read(ser.inWaiting())
                print('SOM7080X is ready\r\n')
                print( 'try to start\r\n' + recBuff.decode() )
                ser.close()
                if 'OK' in recBuff.decode():
                    return True
        except:
            pass
        time.sleep(1) 
    return False

def keypress():
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(21, GPIO.OUT)
    GPIO.output(21, GPIO.HIGH)
    time.sleep(1.5)
    GPIO.setup(21, GPIO.IN)

while True:
    if not ppp0_up():
        print('ppp0 down, checking modem...')
        if modem_responds():
            print('Modem responsive, starting pppd...')
            subprocess.run(['sudo', 'pppd', 'call', 'sim7080g'])
            time.sleep(10)
        elif modem_responds():
            print('Modem responsive on second try, starting pppd...')
            subprocess.run(['sudo', 'pppd', 'call', 'sim7080g'])
            time.sleep(10)
        else:
            print('Modem unresponsive after two attempts, triggering keypress...')
            keypress()
            time.sleep(10)
    else:
        print('ppp0 is up')
        time.sleep(300)