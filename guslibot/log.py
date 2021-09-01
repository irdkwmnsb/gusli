import datetime
import logging
import os

from pathvalidate import sanitize_filename
from rich.logging import RichHandler

root_logger = logging.root
root_logger.setLevel(logging.DEBUG)

os.makedirs("logs", exist_ok=True)
fname = sanitize_filename(datetime.datetime.now().strftime("log_%x_%X%p.log"))
file_handler = logging.FileHandler(f"./logs/{fname}", encoding="UTF-8")
file_handler.setLevel(logging.DEBUG)
log_formatter = logging.Formatter("[%(asctime)s] [%(name)s] [%(levelname)-5.5s] --- %(message)s")
file_handler.setFormatter(log_formatter)
root_logger.addHandler(file_handler)

console_handler = RichHandler()
# console_handler = RichHandler(log_time_format="[%X]", show_path=False)
console_handler.setLevel(logging.DEBUG)
root_logger.addHandler(console_handler)

logger = logging.getLogger("goboards-bot")