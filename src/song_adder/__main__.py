import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from song_adder.Song_Adder import App


def setup_logger(script_dir: Path):

    logger = logging.getLogger()

    log_path = script_dir / 'song_adder.log'


    logger.setLevel(logging.DEBUG)
    logging.getLogger('PIL').setLevel(logging.INFO)

    formatter = logging.Formatter('%(levelname)s:%(name)s:%(message)s')

    file_handler = RotatingFileHandler(log_path, maxBytes=5_242_880, backupCount=1, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)


if __name__ == "__main__":

    if getattr(sys, 'frozen', False):
        script_dir = Path(sys.executable).parent
    else:
        script_dir = Path(__file__).parent.absolute()

    setup_logger(script_dir)
    
    app = App(script_dir)
    app.main()
