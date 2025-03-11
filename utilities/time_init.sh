#!/bin/bash
# Description: Attempts to connect to the network, synchronize system time with RTC, and adjust WittyPi RTC if needed.

# Load WittyPi Utilities
util_dir="$HOME/wittypi"
if [ ! -d "$util_dir" ]; then
    echo "Error: WittyPi utility directory not found: $util_dir"
    exit 1
fi
. "$util_dir/utilities.sh"

# Check network connectivity
check_network() {
    if ping -q -c 1 -W 1 8.8.8.8 >/dev/null; then
        echo "Network is up"
        return 0
    else
        echo "Network is down"
        return 1
    fi
}

# Safely get system time
get_system_time() {
    local sys_time
    sys_time=$(date '+%Y-%m-%d %H:%M:%S')
    if [ -z "$sys_time" ]; then
        echo "Error: Failed to retrieve system time."
        exit 1
    fi
    echo "$sys_time"
}

# Safely get RTC time
get_rtc_time_safe() {
    local rtc_time
    rtc_time=$(sudo hwclock -r 2>/dev/null)
    if [ -z "$rtc_time" ]; then
        echo "Error: Failed to retrieve RTC time."
        exit 1
    fi
    echo "$rtc_time"
}

# Safely get WittyPi RTC time
get_witty_time_safe() {
    local witty_time
    witty_time=$(get_rtc_time 2>/dev/null)
    if [ -z "$witty_time" ]; then
        echo "Error: Failed to retrieve WittyPi RTC time."
        exit 1
    fi
    echo "$witty_time"
}

# Get system, RTC, and WittyPi times
time_sys=$(get_system_time)
time_rtc=$(get_rtc_time_safe)
time_witty=$(get_witty_time_safe)

#echo "DEBUG: System Time = '$time_sys'"
#echo "DEBUG: RTC Time = '$time_rtc'"
#echo "DEBUG: WittyPi Time = '$witty_time'"

# Convert times to epoch seconds
sec_sys=$(date -d "$time_sys" +%s 2>/dev/null)
sec_rtc=$(date -d "$time_rtc" +%s 2>/dev/null)
sec_witty=$(date -d "$time_witty" +%s 2>/dev/null)

if [ -z "$sec_sys" ] || [ -z "$sec_rtc" ] || [ -z "$sec_witty" ]; then
    echo "Error: Failed to convert time to seconds."
    exit 1
fi

# Calculate absolute differences
num_sec=$((sec_sys > sec_rtc ? sec_sys - sec_rtc : sec_rtc - sec_sys))
num_sec_witty=$((sec_sys > sec_witty ? sec_sys - sec_witty : sec_witty - sec_sys))

# Sync time based on network availability
if check_network; then
    echo "Network detected, checking RTC sync..."
    if [ "$num_sec" -ge 1 ]; then
        echo "System and RTC are out of sync by $num_sec seconds. Restarting time sync service..."
        if sudo systemctl restart systemd-timesyncd; then
            echo "Time synchronization restarted successfully."
        else
            echo "Error: Failed to restart time synchronization service."
            exit 1
        fi
    else
        echo "System and RTC are synchronized."
    fi

    # Sync System Time to WittyPi RTC
    echo "Syncing system time to WittyPi RTC..."
    if system_to_rtc; then
        echo "Successfully updated WittyPi RTC with system time."
    else
        echo "Error: Failed to update WittyPi RTC."
        exit 1
    fi


else
    echo "No network detected, checking system vs. WittyPi RTC..."

    # Set Hardware Clock (hwclock) to System Time
    if sudo hwclock --hctosys; then
        echo "System time updated from hwclock."
    else
        echo "Error: Failed to update hwclock from system time."
        exit 1
    fi

    if [ "$num_sec_witty" -ge 1 ]; then
        echo "System and WittyPi RTC are out of sync by $num_sec_witty seconds."
        echo "Setting system time to WittyPi RTC..."
        if system_to_rtc; then
            echo "System time successfully set to WittyPi RTC."
        else
            echo "Error: Failed to set system time to WittyPi RTC."
            exit 1
        fi
    else
        echo "System and WittyPi RTC are already synchronized."
    fi
fi

echo "Time synchronization check completed successfully."

