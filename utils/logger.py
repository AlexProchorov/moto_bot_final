import logging
import sys
from logging.handlers import RotatingFileHandler

def setup_logger(level='INFO'):
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, level))
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    logger.addHandler(console)
    file_handler = RotatingFileHandler('bot.log', maxBytes=10_000_000, backupCount=5, encoding='utf-8')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
