# Installing on a fresh OS (bullseye 64bit lite):
### If the RTC has not yet been set, sync it first (with network connection):
timedatectl set-ntp true

### Update the OS, install git, and clone the bee_cam repo:
sudo apt update ; sudo apt upgrade -y ; sudo apt install git -y ; git clone https://github.com/mparkergetz/bee_cam

### Navigate to bee_cam/setup and run the installer (this will install WittyPi utils to the setup dir. Move the WittyPi dir wherever you prefer):
sudo bash install.sh
