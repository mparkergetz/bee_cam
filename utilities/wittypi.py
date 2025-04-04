import time
import os
import csv
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

    def get_sun_times(self, csv_path: str) -> tuple[datetime, datetime, datetime]:
        """
        Returns (sunrise_today, sunset_today, sunrise_tomorrow) from the CSV.
        """
        now = datetime.now()
        today_str = now.strftime('%Y-%m-%d')
        tomorrow_str = (now + timedelta(days=1)).strftime('%Y-%m-%d')

        logger.debug(f"Reading sun times from: {csv_path}")
        logger.debug(f"Today: {today_str}, Tomorrow: {tomorrow_str}")

        try:
            with open(csv_path, newline='') as f:
                reader = csv.DictReader(f)
                sun_data = {row['date']: row for row in reader}
        except FileNotFoundError:
            logger.error(f"CSV file not found: {csv_path}")
            raise

        try:
            today_row = sun_data[today_str]
            tomorrow_row = sun_data[tomorrow_str]

            sunrise_today = datetime.strptime(f"{today_str} {today_row['sunrise']}", "%Y-%m-%d %H:%M:%S") + timedelta(hours=1)
            sunset_today = datetime.strptime(f"{today_str} {today_row['sunset']}", "%Y-%m-%d %H:%M:%S") - timedelta(hours=1)
            sunrise_tomorrow = datetime.strptime(f"{tomorrow_str} {tomorrow_row['sunrise']}", "%Y-%m-%d %H:%M:%S") + timedelta(hours=1)
            logger.debug(f'Sunrise today: {sunrise_today}, Sunset today: {sunset_today}, Sunrise_tomorrow: {sunrise_tomorrow}')
            return sunrise_today, sunset_today, sunrise_tomorrow

        except KeyError as e:
            logger.error(f"Missing sun data for: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to parse sun times: {e}")
            raise

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
        logger.debug(f"Shutdown time scheduled at {dt}. Status: {'Triggered' if status else 'Not Triggered'}")

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
        logger.debug(f"Startup time scheduled at {dt}. Status: {'Triggered' if status else 'Not Triggered'}")

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

    def shutdown_startup(self, start_today: datetime, stop_today: datetime, start_tomorrow: datetime) -> datetime:
        """
        Schedules shutdown and startup between two datetime ranges.
        If current time is before start, shuts down now and starts at start_time.
        If within the range, shuts down at end_time and schedules startup at tomorrow start_time.
        If past the range, shuts down now and schedules startup at start_tomorrow.
        """
        now = datetime.now()
        mins_until_start = (start_today - now).total_seconds() / 60

        if now < start_today:
            if mins_until_start > 5:
                self.shutdown_in(delay_minutes=5)
                self.schedule_startup(start_today)
                logger.info(f"Shutdown scheduled in 5 min, startup at {start_today}")
            else: # Skip shutdown, startup is too soon
                self.schedule_shutdown(stop_today)
                self.set_startup_at(start_tomorrow.hour, start_tomorrow.minute, start_tomorrow.second)
                logger.info(f"Startup is in {mins_until_start:.1f} min — skipping shutdown, next shutdown at {stop_today}")
        elif start_today <= now < stop_today:
            self.schedule_shutdown(stop_today)
            self.set_startup_at(start_tomorrow.hour, start_tomorrow.minute, start_tomorrow.second)
            logger.info(f"Within active window — shutdown at {stop_today}, restart at {start_tomorrow}")
        else:
            self.shutdown_in(delay_minutes=5)
            self.set_startup_at(start_tomorrow.hour, start_tomorrow.minute, start_tomorrow.second)
            logger.info(f"Outside today's range — shutdown in 5 min, restart at {start_tomorrow}")

        return self.get_current_time()
