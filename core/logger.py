import logging
import sys
from datetime import datetime

from core.config import conf

class Colors:
    ERROR = '\033[91m'
    WARNING = '\033[93m'
    INFO = '\033[97m'
    DEBUG = '\033[94m'
    RESET = '\033[0m'

class ColoredFormatter(logging.Formatter):
    def format(self, record):
        if record.levelno == logging.ERROR:
            color = Colors.ERROR
        elif record.levelno == logging.WARNING:
            color = Colors.WARNING
        elif record.levelno == logging.INFO:
            color = Colors.INFO
        elif record.levelno == logging.DEBUG:
            color = Colors.DEBUG
        else:
            color = Colors.RESET
        
        record.levelname = f"{color}{record.levelname}{Colors.RESET}"
        return super().format(record)

logger = logging.getLogger("boosty_downloader")
logger.setLevel(logging.DEBUG if conf.debug else logging.INFO)

logger.handlers.clear()
stream_handler = logging.StreamHandler(sys.stdout)
colored_formatter = ColoredFormatter("%(asctime)s [%(levelname)s] %(message)s")
stream_handler.setFormatter(colored_formatter)
logger.addHandler(stream_handler)

if conf.save_logs_to_file:
    filename = f"boosty_downloader_{datetime.timestamp(datetime.now())}_launch.log"
    file_handler = logging.FileHandler(filename)
    file_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
