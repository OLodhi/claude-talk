"""One rotating log file shared by every Claude Talk process. Logging never writes to stderr."""
import logging
import os
from logging.handlers import RotatingFileHandler

from talk import paths

logging.raiseExceptions = False  # a logging failure must never print to stderr inside a hook


def get_logger() -> logging.Logger:
    logger = logging.getLogger("claude_talk")
    target = os.path.abspath(paths.log_file())
    if not any(getattr(handler, "baseFilename", None) == target for handler in logger.handlers):
        for old in list(logger.handlers):
            logger.removeHandler(old)
            old.close()
        handler = RotatingFileHandler(target, maxBytes=1_000_000, backupCount=1, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s pid=%(process)d %(levelname)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger
