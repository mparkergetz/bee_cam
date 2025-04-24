# utilities/logger.py
import logging
import os

from utilities.config import Config
config = Config()
log_level = config['general']['log_level']

logger = logging.getLogger("Main")
logger.setLevel(getattr(logging, log_level, logging.INFO))

if not logger.handlers: # avoids duplicate handlers
    package_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    log_dir = os.path.join(package_root, "data")
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, "system.log")
    file_handler = logging.FileHandler(log_file)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
