# -*- coding: utf-8 -*-

from __future__ import absolute_import

import sys
import os
import logging
import locale
from pytz import timezone

from monseigneur.core.tools.log import createColoredFormatter, getLogger
from pathlib import Path

__all__ = ['Application']


class Application(object):

    try:
        data_path = os.environ['DATAPATH']
    except KeyError:
        data_path = '{}/{}'.format(str(Path.home()), 'mdev/monseigneur/mbackend')

    LOG_LEVEL = logging.DEBUG

    def __init__(self, name, send_email=False, tz='Europe/Paris'):
        self.name = name
        self.send_email = send_email
        self.logger = getLogger(name)
        self.tz = timezone(tz)

        try:
            locale.setlocale(locale.LC_ALL, '')
        except locale.Error:
            pass

    def setup_logging(self):
        logging.root.handlers = []
        logging.root.setLevel(self.LOG_LEVEL)
        logging.root.addHandler(self.create_default_logger())

    # creates the logger for the console
    @classmethod
    def create_default_logger(klass):
        format = '%(asctime)s:%(levelname)s:%(name)s:%(filename)s:%(lineno)d:%(funcName)s %(message)s'
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(klass.LOG_LEVEL)
        handler.setFormatter(createColoredFormatter(sys.stdout, format))
        return handler
