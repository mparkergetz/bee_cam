import configparser
import sys
from server.server_main import run_server
from camera.camera_main import run_camera

def main():
    config = configparser.ConfigParser()
    config.read("config.ini")

    mode = config["general"].get("mode", "camera").strip().lower()

    if mode == "server":
        print("Starting in SERVER mode...")
        run_server()

    elif mode == "camera":
        print("Starting in CAMERA mode...")

    else:
        print("Invalid mode in config.ini. Choose 'server' or 'camera'.")
        sys.exit(1)

if __name__ == "__main__":
    main()
