#!/bin/bash
set -e

MODE=$1  # server or camera
BASE_DIR=$(dirname "$(realpath "$0")")

if [[ "$EUID" -ne 0 ]]; then
  echo "YOU FORGOT THE SUDO"
  exit 1
fi

read -rp "Mode? [camera/server]: " MODE
MODE=$(echo "$MODE" | tr '[:upper:]' '[:lower:]')

if [[ "$MODE" != "server" && "$MODE" != "camera" ]]; then
  echo "$MODE is not an option"
  echo "Please try typing better"
  exit 1
fi

read -rp "Enter unit name (camera1/server1): " UNIT_NAME
echo ">>> Setting hostname to '$UNIT_NAME'"
echo "$UNIT_NAME" > /etc/hostname
sed -i "s/127.0.1.1.*/127.0.1.1\t$UNIT_NAME/" /etc/hosts

read -rp "Set location: tt (Talking Trees), sm (Sunrise Mountain), eq (Emerald Queen), or none: " LOCATION_SHORT
LOCATION_SHORT=$(echo "$LOCATION_SHORT" | tr '[:upper:]' '[:lower:]')

case "$LOCATION_SHORT" in
  tt)
    LOCATION="talking_trees"
    ;;
  sm)
    LOCATION="sunrise_mountain"
    ;;
  eq)
    LOCATION="emerald_queen"
    ;;
  none)
    LOCATION="none"
    ;;
  *)
    echo "Invalid location code: $LOCATION_SHORT"
    echo "Location code options: [tt/sm/eq/none]"
    exit 1
    ;;
esac

echo ">>> Updating system and installing dependencies"
apt update
apt upgrade -y
apt install -y git python3-pip mosquitto mosquitto-clients avahi-daemon

if [[ "$MODE" == "server" ]]; then
  echo ">>> Configuring as SERVER (Wi-Fi AP + Modem)"

  apt install -y hostapd dnsmasq minicom screen python3-serial ppp

  systemctl stop hostapd
  systemctl stop dnsmasq

  echo ">>> Copying config files for server..."
  cp "$BASE_DIR/server/config_server.txt" /boot/config.txt
  cp "$BASE_DIR/server/dhcpcd.conf" /etc/dhcpcd.conf
  cp "$BASE_DIR/server/dnsmasq.conf" /etc/dnsmasq.conf
  cp "$BASE_DIR/server/hostapd.conf" /etc/hostapd/hostapd.conf
  cp "$BASE_DIR/server/hostapd" /etc/default/hostapd
  cp "$BASE_DIR/server/sim7080g_peers" /etc/ppp/peers/sim7080g
  cp "$BASE_DIR/server/sim7080g" /etc/chatscripts/sim7080g
  cp "$BASE_DIR/server/resolv.conf" /etc/ppp/resolv.conf
  cp "$BASE_DIR/server/ip-up" /etc/ppp/ip-up

  chmod +x /etc/ppp/ip-up

  echo ">>> Setting up hostapd and dnsmasq services"
  systemctl unmask hostapd
  systemctl enable hostapd
  systemctl enable dnsmasq
  systemctl restart dhcpcd
  systemctl start hostapd
  systemctl start dnsmasq

  #echo ">>> Setting permissions on serial port"
  #chown root:dialout /dev/serial0
  #chmod 660 /dev/serial0

else
  echo ">>> Configuring as CAMERA (node)"
  cp "$BASE_DIR/node/config_camera.txt" /boot/config.txt
  cp "$BASE_DIR/node/wpa_supplicant.conf" /etc/wpa_supplicant/wpa_supplicant.conf
fi

echo ">>> Enabling I2C kernel modules"
grep -q '^i2c-dev' /etc/modules || echo "i2c-dev" >> /etc/modules
modprobe i2c-dev || echo "Failed to load i2c-dev module"
modprobe i2c-bcm2835 || echo "⚠Failed to load i2c-bcm2835 module"

echo ">>> Installing Python requirements"
pip3 install --upgrade pip
pip3 install -r "$BASE_DIR/requirements.txt"

echo ">>> Installing systemd services"

cp "$BASE_DIR/systemd_services/bee_cam.service" /etc/systemd/system/
cp "$BASE_DIR/systemd_services/datetime_sync.service" /etc/systemd/system/
systemctl enable bee_cam.service
systemctl enable datetime_sync.service

if [[ "$MODE" == "server" ]]; then
  echo ">>> Installing ppp_connect.service"
  cp "$BASE_DIR/systemd_services/ppp_connect.service" /etc/systemd/system/
  systemctl enable ppp_connect.service
fi

if [[ "$MODE" == "camera" ]]; then
  echo ">>> Installing camera_monitor.service"
  cp "$BASE_DIR/systemd_services/camera_monitor.service" /etc/systemd/system/
  systemctl enable camera_monitor.service
fi

CONFIG_TARGET="$(realpath "$BASE_DIR/..")/config.ini"
if grep -q "^name *= *" "$CONFIG_TARGET"; then
  sed -i "s/^name *= *.*/name = $UNIT_NAME/" "$CONFIG_TARGET"
else
  sed -i "/^\[general\]/a name = $UNIT_NAME" "$CONFIG_TARGET"
fi

if grep -q "^mode *= *" "$CONFIG_TARGET"; then
  sed -i "s/^mode *= *.*/mode = $MODE/" "$CONFIG_TARGET"
else
  sed -i "/^\[general\]/a mode = $MODE" "$CONFIG_TARGET"
fi

if [[ "$LOCATION" != "none" ]]; then
  echo ">>> Generating sunrise/sunset times for $LOCATION..."
  python3 "$BASE_DIR/generate_sunrise_sunset_times.py" "$LOCATION"
else
  echo ">>> Skipping sunrise/sunset generation (no location selected)."
fi

echo ">>> Done. Please reboot!"
