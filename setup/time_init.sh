#!/bin/bash
# Description: This script attempts to connect to the network over a 1 second period, if network connection can be established then will reestablish time to the hwclock and system time.  
## If no network connection can be established then will check that hwclock and date times are equal. If that is the case then will set the wittyPi time based on that.

# call wittypi utilities
util_dir="/home/pi/wittypi"
echo "$util_dir"
. "$util_dir/utilities.sh"

echo "Setting system time from DS3231"
sudo hwclock -s
echo "System time after hwclock -s: $(date '+%Y-%m-%d %H:%M:%S')"

time_sys=$(date '+%Y-%m-%d %H:%M:%S')
time_witty=$(get_rtc_time)
echo "System Time vs WittyPi RTC: $time_sys and $time_witty"

sec_sys=$(date -d "$time_sys" +%s)
sec_witty=$(date -d "$time_witty" +%s)
diff_witty=$((sec_sys - sec_witty))
[ "$diff_witty" -lt 0 ] && diff_witty=$((diff_witty * -1))

if [ "$diff_witty" -ge 2 ]; then
    echo "System and WittyPi RTC are out of sync by $diff_witty sec. Updating WittyPi RTC from system..."
    system_to_rtc
else
    echo "System and WittyPi RTC are synced."
fi

if ping -q -c 1 -W 1 8.8.8.8 >/dev/null; then
    echo "Network is up. Attempting NTP sync..."
    sudo systemctl restart systemd-timesyncd
    sleep 10

    echo "System time after NTP: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "Updating DS3231 and WittyPi RTCs from system..."
    sudo hwclock -w
    system_to_rtc
else
    echo "Network is down. Skipping NTP sync and RTC updates."
fi

echo "Final times:"
echo "  System:   $(date '+%Y-%m-%d %H:%M:%S')"
echo "  DS3231:   $(sudo hwclock -r | cut -d'-' -f1-3)"
echo "  WittyPi:  $(get_rtc_time)"
