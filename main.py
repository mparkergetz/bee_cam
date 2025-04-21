import configparser
import sys

def main():
    config = configparser.ConfigParser()
    config.read("config.ini")

    mode = config["general"].get("mode", "camera").strip().lower()

    if mode == "server":
        from utilities.server_main import run_server
        print("Starting in SERVER mode...")
        run_server()

    elif mode == "camera":
        from utilities.camera_main import run_camera
        print("Starting in CAMERA mode...")
        run_camera()

    else:
        print("Invalid mode in config.ini. Choose 'server' or 'camera'.")
        sys.exit(1)

if __name__ == "__main__":
    main()
