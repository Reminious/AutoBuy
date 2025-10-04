import logging

from colorama import init as colorama_init, Fore, Style


colorama_init(autoreset=True)


class ColorFormatter(logging.Formatter):
    LEVEL_COLORS = {
        logging.DEBUG: Style.DIM,
        logging.INFO: Fore.CYAN,
        logging.WARNING: Fore.YELLOW,
        logging.ERROR: Fore.RED,
        logging.CRITICAL: Fore.RED + Style.BRIGHT,
    }


    def format(self, record):
        color = self.LEVEL_COLORS.get(record.levelno, "")
        reset = Style.RESET_ALL
        record.levelname = f"{color}{record.levelname}{reset}"
        return super().format(record)


logger = logging.getLogger("autobuy")
logger.setLevel(logging.DEBUG)
_handler = logging.StreamHandler()
_handler.setFormatter(
    ColorFormatter(fmt="%(asctime)s [%(levelname)s] [%(threadName)s] %(message)s", datefmt="%H:%M:%S"))
logger.addHandler(_handler)

COMP_COLORS = {
    "CORE": Fore.WHITE + Style.BRIGHT,
    "DETECT": Fore.MAGENTA + Style.BRIGHT,
    "BUY": Fore.GREEN + Style.BRIGHT,
    "EMAIL": Fore.BLUE + Style.BRIGHT,
    "STATS": Fore.CYAN + Style.BRIGHT,
}


def clog(level, comp, msg):
    c = COMP_COLORS.get(comp, "")
    reset = Style.RESET_ALL
    logger.log(level, f"{c}[{comp}]{reset} {msg}")
