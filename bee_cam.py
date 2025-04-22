#!/usr/bin/env python3

import os
import sys
import time
import shutil
import socket
import subprocess
from datetime import datetime
from configparser import ConfigParser

from picamera2 import Picamera2, Preview

CONFIG_PATH = "/home/pi/bee_cam/config.ini"

def get_image_size_from_config():
    config = ConfigParser()
    config.read(CONFIG_PATH)
    width = config.getint("imaging", "w")
    height = config.getint("imaging", "h")
    return (width, height)

def stop_service():
    subprocess.run(["sudo", "systemctl", "stop", "bee_cam.service"])
    time.sleep(1)

def start_service():
    subprocess.run(["sudo", "systemctl", "start", "bee_cam.service"])

def is_ssh():
    return os.environ.get("SSH_CONNECTION") is not None

def run_alignment_mode(image_size):
    stop_service()
    if is_ssh():
        host = os.environ.get("SSH_CONNECTION").split()[0]
        user = input("Enter your local system's username: ")
        dest_dir = f"/home/{user}/Downloads"

        while True:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"/tmp/test_capture_{timestamp}.jpg"

            cam = Picamera2()
            config = cam.create_still_configuration(main={"size": image_size})
            cam.configure(config)
            cam.start()
            cam.capture_file(filename)
            cam.close()

            print(f"Image captured: {filename}")
            print(f"Transferring to {user}@{host}:{dest_dir}...")
            scp_result = subprocess.run(["scp", filename, f"{user}@{host}:{dest_dir}"])
            if scp_result.returncode == 0:
                print("Transfer complete.")
            else:
                print("Transfer failed.")

            again = input("Take another photo? [y/N]: ").strip().lower()
            if again != "y":
                break
    else:
        print("Detected local session. Displaying preview...")
        try:
            cam = Picamera2()
            config = cam.create_preview_configuration(main={"size": image_size})
            cam.configure(config)
            cam.start_preview(Preview.DRM)
            cam.start()
            print("📺 Preview running. Press Ctrl+C to stop.")
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            cam.stop_preview()
            cam.close()
            print("Preview stopped.")
    start_service()

def run_focus_test(image_size):
    stop_service()
    if is_ssh():
        host = os.environ.get("SSH_CONNECTION").split()[0]
        user = input("Enter your local system's username: ")
        dest_dir = f"/home/{user}/Downloads"
        focus_dir = f"/tmp/focus_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        os.makedirs(focus_dir, exist_ok=True)

        cam = Picamera2()
        config = cam.create_still_configuration(main={"size": image_size})
        cam.configure(config)
        cam.start()

        lens_positions = [i * 0.1 for i in range(10)]
        for i, pos in enumerate(lens_positions):
            cam.set_controls({"LensPosition": pos})
            time.sleep(0.5)
            filename = os.path.join(focus_dir, f"focus_{i}_pos{pos:.1f}.jpg")
            cam.capture_file(filename)
            print(f"Captured {filename}")
            time.sleep(0.5)

        cam.close()

        print(f"Transferring {focus_dir} to {user}@{host}:{dest_dir}...")
        subprocess.run(["scp", "-r", focus_dir, f"{user}@{host}:{dest_dir}"])
        shutil.rmtree(focus_dir)
    else:
        print("Detected local session. Using Preview.DRM to view results.")
        focus_dir = f"/tmp/focus_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        os.makedirs(focus_dir, exist_ok=True)

        cam = Picamera2()
        config = cam.create_still_configuration(main={"size": image_size})
        cam.configure(config)
        cam.start()

        lens_positions = [i * 0.1 for i in range(10)]
        for i, pos in enumerate(lens_positions):
            cam.set_controls({"LensPosition": pos})
            time.sleep(0.5)
            filename = os.path.join(focus_dir, f"focus_{i}_pos{pos:.1f}.jpg")
            cam.capture_file(filename)
            print(f"Saved: {filename}")
            time.sleep(0.5)

        cam.close()

        try:
            print("Launching image viewer (Preview.DRM)")
            config = cam.create_preview_configuration(main={"size": image_size})
            cam.configure(config)
            cam.start_preview(Preview.DRM)
            cam.start()

            image_files = sorted(os.listdir(focus_dir))
            index = 0

            def show_image(path):
                import cv2
                img = cv2.imread(path)
                cam.set_overlay(cv2.resize(img, image_size))

            show_image(os.path.join(focus_dir, image_files[index]))

            print("Arrows to navigate, q to quit")

            import tty, termios
            def getch():
                fd = sys.stdin.fileno()
                old = termios.tcgetattr(fd)
                try:
                    tty.setraw(fd)
                    return sys.stdin.read(1)
                finally:
                    termios.tcsetattr(fd, termios.TCSADRAIN, old)

            while True:
                key = getch()
                if key == "q":
                    break
                elif key == "\r" or key == "n":
                    index = min(index + 1, len(image_files) - 1)
                elif key == "p":
                    index = max(index - 1, 0)
                show_image(os.path.join(focus_dir, image_files[index]))

        except KeyboardInterrupt:
            pass
        finally:
            cam.stop_preview()
            cam.close()

        delete = input("Delete captured images? [Y/n]: ").strip().lower()
        if delete in ["", "y", "yes"]:
            shutil.rmtree(focus_dir)
            print("Images deleted.")
        else:
            print(f"Images kept at {focus_dir}")
    start_service()

def main():
    image_size = get_image_size_from_config()

    print("Bee Cam Control Panel")
    print("========================")
    print("1) View camera alignment")
    print("2) Test focus")
    print("3) Exit")

    choice = input("Enter your choice [1-3]: ").strip()
    if choice == "1":
        run_alignment_mode(image_size)
    elif choice == "2":
        run_focus_test(image_size)
    elif choice == "3":
        print("Exiting.")
        sys.exit(0)
    else:
        print("Invalid choice. Exiting.")
        sys.exit(1)

if __name__ == "__main__":
    main()
