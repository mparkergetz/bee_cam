import time
import os
from datetime import datetime, timedelta
from smbus2 import SMBus
from utilities.logger import logger as base_logger
logger = base_logger.getChild("WittyPi")

class ShutdownTime(Exception):
    """Raised when the shutdown time is reached."""
    pass

class WittyPi:
    def __init__(self, bus_num: int = 1):
        self._bus_num = bus_num
        self._bus = None
        self.latest_temp = {}

    def __enter__(self):
        self._bus = SMBus(self._bus_num)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._bus.close()

    @staticmethod
    def int_to_bcd(value: int) -> int:
        return ((value // 10) << 4) | (value % 10)

    @staticmethod
    def bcd_to_int(bcd: int) -> int:
        return ((bcd & 0xF0) >> 4) * 10 + (bcd & 0x0F)

    @staticmethod
    def weekday_conv(val: int) -> int:
        return (val + 1) % 7

    def _write_bcd_data(self, start_register: int, values: list[int]):
        for offset, val in enumerate(values):
            self._bus.write_byte_data(8, start_register + offset, self.int_to_bcd(val))
            time.sleep(1)

    def _read_bcd_data(self, start_register: int, count: int) -> list[int]:
        return [self.bcd_to_int(self._bus.read_byte_data(8, start_register + i)) for i in range(count)]

    def get_current_time(self) -> datetime:
        try:
            values = self._read_bcd_data(58, 7)
            sec, minute, hour, day, weekday, month, year = values
            return datetime(year=2000 + year, month=month, day=day, hour=hour, minute=minute, second=sec)
        except ValueError as e:
            logger.warning(f"Invalid RTC values: {e}. Falling back to system time.")
            return datetime.now()

    def schedule_shutdown(self, shutdown_time: datetime):
        shutdown_time += timedelta(minutes=5)
        shutdown_values = [
            shutdown_time.second,
            shutdown_time.minute,
            shutdown_time.hour,
            shutdown_time.day,
            self.weekday_conv(shutdown_time.weekday())
        ]
        self._write_bcd_data(32, shutdown_values)
        status = self.bcd_to_int(self._bus.read_byte_data(8, 40))
        scheduled = self._read_bcd_data(32, 5)
        dt = datetime(shutdown_time.year, shutdown_time.month, scheduled[3], scheduled[2], scheduled[1], scheduled[0])
        logger.info(f"Shutdown time scheduled at {dt}. Status: {'Triggered' if status else 'Not Triggered'}")

    def schedule_startup(self, startup_time: datetime):
        startup_values = [
            startup_time.second,
            startup_time.minute,
            startup_time.hour,
            startup_time.day,
            self.weekday_conv(startup_time.weekday())
        ]
        self._write_bcd_data(27, startup_values)
        status = self.bcd_to_int(self._bus.read_byte_data(8, 39))
        scheduled = self._read_bcd_data(27, 5)
        dt = datetime(startup_time.year, startup_time.month, scheduled[3], scheduled[2], scheduled[1], scheduled[0])
        logger.info(f"Startup time scheduled at {dt}. Status: {'Triggered' if status else 'Not Triggered'}")

    def shutdown_in(self, delay_minutes: int = 5):
        shutdown_time = self.get_current_time() + timedelta(minutes=delay_minutes)
        self.schedule_shutdown(shutdown_time)

    def startup_in(self, delay_minutes: int = 10):
        startup_time = self.get_current_time() + timedelta(minutes=delay_minutes)
        self.schedule_startup(startup_time)

    def set_startup_at(self, hr: int = 5, min: int = 0, sec: int = 0, use_next_day: bool = True):
        start_time = self.get_current_time()
        if use_next_day:
            start_time += timedelta(days=1)
        start_time = start_time.replace(hour=hr, minute=min, second=sec)
        self.schedule_startup(start_time)

    def get_internal_temperature(self) -> dict:
        """
        Reads the internal temperature from the WittyPi and returns it as a dict.
        The dict contains both Celsius and Fahrenheit values.
        """
        temp_c = self._bus.read_byte_data(8, 50)
        temp_f = temp_c * (9 / 5) + 32
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self.latest_temp = {
            "timestamp": timestamp,
            "temp_c": round(temp_c, 2),
            "temp_f": round(temp_f, 2)
        }

        return self.latest_temp

    def shutdown_startup(self, start_str: str, end_str: str) -> datetime:
        """
        Schedules shutdown and startup based on two time ranges (e.g. '5,0,0' and '8,0,0')
        """
        now = datetime.now()
        start_h, start_m, start_s = map(int, start_str.split(","))
        end_h, end_m, end_s = map(int, end_str.split(","))
        start_dt = now.replace(hour=start_h, minute=start_m, second=start_s)
        end_dt = now.replace(hour=end_h, minute=end_m, second=end_s)

        if now < start_dt:
            self.schedule_shutdown(now)
            self.schedule_startup(start_dt)
        elif start_dt <= now < end_dt:
            self.schedule_shutdown(end_dt)
            self.set_startup_at(start_h, start_m, start_s)
        else:
            self.schedule_shutdown(now)
            self.set_startup_at(start_h, start_m, start_s)

        return self.get_current_time()
