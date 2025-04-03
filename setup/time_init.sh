#!/bin/bash
# Description: This script attempts to connect to the network over a 10 second period, if network connection can be established then will reestablish time to the hwclock and system time.  
## If no network connection can be established then will check that hwclock and date times are equal. If that is the case then will set the wittyPi time based on that.

# call wittypi utilities
util_dir="/home/pi/wittypi"
echo "$util_dir"
. "$util_dir/utilities.sh"

time_sys=$(date '+%Y-%m-%d %H:%M:%S')
time_rtc=$(sudo hwclock -r)
time_rtc=$(echo "$time_rtc" | cut -d'-' -f1-3)

echo "System Time vs System RTC: $time_sys and $time_rtc"

sec_sys=$(date -d "$time_sys" +%s)
sec_rtc=$(date -d "$time_rtc" +%s)

num_sec=$((sec_sys - sec_rtc))

# Absolute Difference:
if [ "$num_sec" -lt 0 ]; then
  num_sec=$((num_sec * -1))
fi

# Check if can connect to network within 1 second
if ping -q -c 1 -W 1 8.8.8.8 >/dev/null; then
   echo "IPv4 is up"
   # Check if the System and DS3231 RTC (hwclock) are off by more than 1 second
   if [ "$num_sec" -ge 1 ]; then
      echo "System and DS3231 are $num_sec seconds off"
      # Now apply the systemctl restart systemd-timesyncd
      echo "Current RTC: $(sudo hwclock -r) | Current Sys: $(date '+%Y-%m-%d %H:%M:%S')"
      echo "RESTARTING..TIME SYNC..."
      sudo systemctl restart systemd-timesyncd
      echo "Current RTC: $(sudo hwclock -r) | Current Sys: $(date '+%Y-%m-%d %H:%M:%S')"
   
   else
      echo "Num of seconds over: $num_sec"

   fi

else
  echo "IPv4 is down"
  if [ "$num_sec" -ge 1 ]; then
     echo "System and DS3231 Require Calibration"
  else
     echo "System and DS3231 are synced"
  fi
fi

# After Setting System and DS3231 RTC if not the same then looked at WittyPi RTC
## If WittyPi RTC not equal or within 1 second then reset...
time_sys=$(date '+%Y-%m-%d %H:%M:%S')
time_rtc=$(sudo hwclock -r)
time_rtc=$(echo "$time_rtc" | cut -d'-' -f1-3)
time_witty=$(get_rtc_time) # uses wittypi utility function to get wittypi's rtc time
echo "System Time vs System WittyPi: $time_sys and $time_rtc and $time_witty"
sec_sys=$(date -d "$time_sys" +%s) # system time in seconds
sec_witty=$(date -d "$time_witty" +%s) # wittypi rtc time in seconds

num_sec_witty=$((sec_sys - sec_witty))
if [ "$num_sec_witty" -lt 0 ]; then
  num_sec_witty=$((num_sec_witty * -1))
fi

## If the wittypi time and the system time are off then set system to wittypi
if [ "$num_sec_witty" -ge 1 ]; then
   echo "System and WittyPi are $num_sec_witty seconds off"
   # Now apply the systemctl restart systemd-timesyncd
   echo "Current Sys: $(date '+%Y-%m-%d %H:%M:%S') | Current Witty time: $(get_rtc_time)"
   echo "Set System to WittyPi RTC"
   system_to_rtc
   echo "Current Sys: $(date '+%Y-%m-%d %H:%M:%S') | Current Witty time: $(get_rtc_time)"
   
else
   echo "Num of seconds over: $num_sec_witty"
fi
