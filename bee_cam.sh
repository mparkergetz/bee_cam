#!/bin/bash

echo "Bee Cam Control Panel"
echo "========================"
echo "Choose an option:"
echo "1) View camera alignment"
echo "2) Test focus"
echo "3) Exit"
read -p "Enter your choice [1-3]: " choice

case $choice in
    1)
        echo "Starting Test Mode: Auto-detect connection type"

        echo "Stopping bee_cam.service..."
        sudo systemctl stop bee_cam.service
        sleep 1

        if [ -n "$SSH_CONNECTION" ]; then
            echo "Detected SSH session."

            read -p "Enter your local system's username: " user
            host=$(echo "$SSH_CONNECTION" | awk '{print $1}')
            dest_dir="/home/${user}/Downloads"

            while true; do
                sudo -u pi -E python3 - <<EOF
from picamera2 import Picamera2
from datetime import datetime
import sys

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
filename = f"/tmp/test_capture_{timestamp}.jpg"

try:
    cam = Picamera2()
    cam.configure(cam.create_still_configuration())
    cam.start()
    cam.capture_file(filename)
    cam.close()
    print(f"Image captured: {filename}")
except Exception as e:
    print(f"Camera error: {e}")
    sys.exit(1)
EOF

                latest_file=$(ls -t /tmp/test_capture_*.jpg | head -n 1)
                echo "Transferring image to ${user}@${host}:${dest_dir}..."
                scp "$latest_file" "${user}@${host}:${dest_dir}" && echo "Transfer complete." || echo "Transfer failed."

                echo ""
                read -p "Take another photo? [y/N]: " again
                if [[ "$again" =~ ^[Yy]$ ]]; then
                    continue
                else
                    break
                fi
            done

        else
            echo "Detected local (non-SSH) session."
            echo "Displaying live preview via HDMI..."

            python3 - <<EOF
from picamera2 import Picamera2, Preview
import time

try:
    cam = Picamera2()
    cam.start_preview(Preview.DRM)
    cam.start()
    print("Preview running. Press Ctrl+C to exit.")
    while True:
        time.sleep(1)

except KeyboardInterrupt:
    cam.stop_preview()
    cam.close()
    print("Exited test mode.")
EOF
        fi

        echo "Restarting bee_cam.service..."
        sudo systemctl start bee_cam.service
        echo "bee_cam.service restarted."
        ;;

    2)
        echo "Starting Focus Sweep Test: 10 photos at different lens positions"
        echo "Stopping bee_cam.service..."
        sudo systemctl stop bee_cam.service
        sleep 1

        if [ -n "$SSH_CONNECTION" ]; then
            echo "Detected SSH session."
            read -p "Enter your local system's username: " user
            host=$(echo "$SSH_CONNECTION" | awk '{print $1}')
            dest_dir="/home/${user}/Downloads"

            sudo -u pi -E python3 - <<EOF
from picamera2 import Picamera2
from datetime import datetime
import time
import os

cam = Picamera2()
cam.configure(cam.create_still_configuration())
cam.start()

lens_positions = [i * 0.1 for i in range(10)]
output_files = []

for i, pos in enumerate(lens_positions):
    filename = f"/tmp/focus_test_{i}_pos{pos:.1f}.jpg"
    cam.set_controls({"LensPosition": pos})
    time.sleep(0.5)
    cam.capture_file(filename)
    output_files.append(filename)
    print(f"Captured {filename}")
    time.sleep(0.5)

cam.close()

with open("/tmp/focus_test_files.txt", "w") as f:
    for file in output_files:
        f.write(file + "\\n")
EOF

        echo "Sending focus test images..."

        focus_dir="/tmp/focus_test_$(date +%Y%m%d_%H%M%S)"
        mkdir -p "$focus_dir"

        while read file; do
           mv "$file" "$focus_dir/"
        done < /tmp/focus_test_files.txt

        echo "Transferring ${focus_dir} to ${user}@${host}:${dest_dir}..."
        scp -r "$focus_dir/" "${user}@${host}:${dest_dir}" \
            && echo "Focus images sent." \
            || echo "Transfer failed."

        rm -rf "$focus_dir"

        else
            echo "Detected local session. Running interactive focus test..."

            timestamp=$(date +%Y%m%d_%H%M%S)
            focus_dir="/tmp/focus_test_${timestamp}"
            mkdir -p "$focus_dir"

            sudo -u pi -E python3 - <<EOF
            from picamera2 import Picamera2
            from datetime import datetime
            import time
            import os

            cam = Picamera2()
            cam.configure(cam.create_still_configuration())
            cam.start()

            lens_positions = [i * 0.1 for i in range(10)]

            save_dir = "${focus_dir}"

            for i, pos in enumerate(lens_positions):
                filename = os.path.join(save_dir, f"focus_{i}_pos{pos:.1f}.jpg")
                cam.set_controls({"LensPosition": pos})
                time.sleep(0.5)
                cam.capture_file(filename)
                print(f"Saved: {filename}")
                time.sleep(0.5)

            cam.close()
            EOF

            echo ""
            echo "Press [Enter] to view images one at a time. Close the image window each time to continue."
            read -p "Start review? " _

            if command -v feh &> /dev/null; then
                echo "Opening interactive image viewer (use ← → arrows to navigate, Q to quit)..."
                feh --auto-zoom --scale-down --title "Focus Test: %f" "$focus_dir"
            else
                echo "No image viewer found (feh or xdg-open). Install feh with: sudo apt install feh"
            fi

            echo ""
            read -p "Delete temporary focus images? [Y/n]: " delete_confirm
            if [[ "$delete_confirm" =~ ^[Yy]$ || -z "$delete_confirm" ]]; then
                rm -rf "$focus_dir"
                echo "Focus test images deleted."
            else
                echo "Images kept at: $focus_dir"
            fi




    3)
        echo "Exiting."
        exit 0
        ;;

    *)
        echo "Invalid choice. Exiting."
        exit 1
        ;;
esac
