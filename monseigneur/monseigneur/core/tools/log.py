# -*- coding: utf-8 -*-

from __future__ import print_function

import sys
from collections import defaultdict
from logging import addLevelName, Formatter, getLogger as _getLogger, LoggerAdapter

__all__ = ['getLogger', 'createColoredFormatter', 'settings']


RESET_SEQ = "\033[0m"
COLOR_SEQ = "%s%%s" + RESET_SEQ

COLORS = {
    'DEBUG': COLOR_SEQ % "\033[0;36m",
    'INFO': COLOR_SEQ % "\033[32m",
    'WARNING': COLOR_SEQ % "\033[1;33m",
    'ERROR': COLOR_SEQ % "\033[1;31m",
    'CRITICAL': COLOR_SEQ % ("\033[1;33m\033[1;41m"),
    'DEBUG_FILTERS': COLOR_SEQ % "\033[0;35m",
    'USER': COLOR_SEQ % "\x1b[33;21m"
}

DEBUG_FILTERS = 8
addLevelName(DEBUG_FILTERS, 'DEBUG_FILTERS')


# Global settings f logger.
settings = defaultdict(lambda: None)


def getLogger(name, parent=None):
    if isinstance(parent, LoggerAdapter):
        klass = type(parent)
        extra = parent.extra
        parent = parent.logger
    else:
        klass = None
        extra = None

    if parent:
        name = parent.name + '.' + name
    logger = _getLogger(name)
    logger.settings = settings

    if extra:
        logger = klass(logger, extra)
        logger.settings = settings
    return logger


class ColoredFormatter(Formatter):
    """
    Class written by airmind:
    http://stackoverflow.com/questions/384076/how-can-i-make-the-python-logging-output-to-be-colored
    """

    def format(self, record):
        levelname = record.levelname
        msg = Formatter.format(self, record)
        if levelname in COLORS:
            msg = COLORS[levelname] % msg
        return msg


def createColoredFormatter(stream, format):
    if (sys.platform != 'win32') and stream.isatty():
        return ColoredFormatter(format)
    else:
        return Formatter(format)


if __name__ == '__main__':
    for levelname, cs in COLORS.items():
        print(cs % levelname, end=' ')
