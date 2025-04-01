# import serial
# import time
# import subprocess
# import psutil

# if 'ppp0' in psutil.net_if_addrs():
#     print('ppp0 already up')
#     exit(0)

# ser = serial.Serial('/dev/serial0', 9600, timeout=1)
# ser.write(b'AT\r')
# time.sleep(1)
# response = ser.read(64).decode(errors='ignore')

# ser.close()

# if 'OK' in response:
#     print('Modem OK, connecting')
#     subprocess.run(['sudo', 'pppd', 'call', 'sim7080g'])
# else:
#     print('Modem not responding')

import serial
import time
import subprocess
import os

#time.sleep(10)

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

            # response = ser.read(64).decode(errors='ignore')
            # ser.close()
            # if 'OK' in response:
            #     return True
        except:
            pass
        time.sleep(1) 
    return False

while True:
    if not ppp0_up():
        print('ppp0 down, checking modem...')
        if modem_responds():
            print('Modem responsive, starting pppd...')
            subprocess.run(['sudo', 'pppd', 'call', 'sim7080g'])
            time.sleep(10)
        else:
            print('Modem unresponsive, retrying...')
            time.sleep(10)
    else:
        print('ppp0 is up')
        time.sleep(600)
