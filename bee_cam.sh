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

width, height = 2304, 1296
size = (width, height)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
filename = f"/tmp/test_capture_{timestamp}.jpg"

try:
    cam = Picamera2()
    config = cam.create_still_configuration(main={"size": size})
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

width, height = 2304, 1296
size = (width, height)

try:
    cam = Picamera2()
    config = cam.create_preview_configuration(main={"size": size})
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

            focus_dir="/tmp/focus_test_$(date +%Y%m%d_%H%M%S)"
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
    print(f"📸 Captured: {filename}")
    time.sleep(0.5)

cam.close()
EOF

            echo "Transferring ${focus_dir} to ${user}@${host}:${dest_dir}..."
            scp -r "$focus_dir/" "${user}@${host}:${dest_dir}" \
                && echo "Focus images sent." \
                || echo "Transfer failed."

            # Optional cleanup
            rm -rf "$focus_dir"

        else
            echo "Detected local session. Run via ssh for best results"
        fi
#             timestamp=$(date +%Y%m%d_%H%M%S)
#             focus_dir="/tmp/focus_test_${timestamp}"
#             mkdir -p "$focus_dir"

#             sudo -u pi -E python3 - <<EOF
# from picamera2 import Picamera2
# from datetime import datetime
# import time
# import os

# cam = Picamera2()
# cam.configure(cam.create_still_configuration())
# cam.start()

# lens_positions = [i * 0.1 for i in range(10)]
# save_dir = "${focus_dir}"

# for i, pos in enumerate(lens_positions):
#     filename = os.path.join(save_dir, f"focus_{i}_pos{pos:.1f}.jpg")
#     cam.set_controls({"LensPosition": pos})
#     time.sleep(0.5)
#     cam.capture_file(filename)
#     print(f"Saved: {filename}")
#     time.sleep(0.5)

# cam.close()
# EOF

#             echo ""
#             read -p "Press [Enter] to view images using interactive viewer..."

#             if command -v feh &> /dev/null; then
#                 echo "Opening viewer — use ← → to navigate, Q to quit"
#                 feh --auto-zoom --scale-down --title "Focus Test: %f" "$focus_dir"
#             else
#                 echo "No image viewer found (feh). Install it with: sudo apt install feh"
#             fi

#             echo ""
#             read -p "Delete temporary focus images? [Y/n]: " delete_confirm
#             if [[ "$delete_confirm" =~ ^[Yy]$ || -z "$delete_confirm" ]]; then
#                 rm -rf "$focus_dir"
#                 echo "Focus test images deleted."
#             else
#                 echo "Images kept at: $focus_dir"
#             fi
#         fi

        echo "Restarting bee_cam.service..."
        sudo systemctl start bee_cam.service
        echo "bee_cam.service restarted."
        ;;


    3)
        echo "Exiting."
        exit 0
        ;;

    *)
        echo "Invalid choice. Exiting."
        exit 1
        ;;
esac
