# -*- coding: utf-8 -*-

try:
    from configparser import RawConfigParser, DEFAULTSECT
except ImportError:
    from ConfigParser import RawConfigParser, DEFAULTSECT

from collections import OrderedDict
from decimal import Decimal
import logging
import os
import io
import sys

from core.tools.compat import basestring, unicode

from .iconfig import IConfig


__all__ = ['INIConfig']


class INIConfig(IConfig):
    ROOTSECT = 'ROOT'

    def __init__(self, path):
        self.path = path
        self.values = OrderedDict()
        self.config = RawConfigParser()

    def load(self, default={}):
        self.values = OrderedDict(default)

        if os.path.exists(self.path):
            logging.debug(u'Loading application configuration file: %s.' % self.path)
            if sys.version_info.major < 3:
                self.config.readfp(io.open(self.path, "r", encoding='utf-8'))
            else:
                self.config.read(self.path, encoding='utf-8')
            for section in self.config.sections():
                args = section.split(':')
                if args[0] == self.ROOTSECT:
                    args.pop(0)
                for key, value in self.config.items(section):
                    self.set(*(args + [key, value]))
            # retro compatibility
            if len(self.config.sections()) == 0:
                first = True
                for key, value in self.config.items(DEFAULTSECT):
                    if first:
                        logging.warning('The configuration file "%s" uses an old-style' % self.path)
                        logging.warning('Please rename the %s section to %s' % (DEFAULTSECT, self.ROOTSECT))
                        first = False
                    self.set(key, value)
            logging.debug(u'Application configuration file loaded: %s.' % self.path)
        else:
            self.save()
            logging.debug(u'Application configuration file created with default values: %s. '
                          'Please customize it.' % self.path)
        return self.values

    def save(self):
        def save_section(values, root_section=self.ROOTSECT):
            for k, v in values.items():
                if isinstance(v, (int, Decimal, float, basestring)):
                    if not self.config.has_section(root_section):
                        self.config.add_section(root_section)
                    self.config.set(root_section, k, unicode(v))
                elif isinstance(v, dict):
                    new_section = ':'.join((root_section, k)) if (root_section != self.ROOTSECT or k == self.ROOTSECT) else k
                    if not self.config.has_section(new_section):
                        self.config.add_section(new_section)
                    save_section(v, new_section)
        save_section(self.values)
        with io.open(self.path, 'w', encoding='utf-8') as f:
            self.config.write(f)

    def get(self, *args, **kwargs):
        default = None
        if 'default' in kwargs:
            default = kwargs['default']

        v = self.values
        for k in args[:-1]:
            if k in v:
                v = v[k]
            else:
                return default
        try:
            return v[args[-1]]
        except KeyError:
            return default

    def set(self, *args):
        v = self.values
        for k in args[:-2]:
            if k not in v:
                v[k] = OrderedDict()
            v = v[k]
        v[args[-2]] = args[-1]

    def delete(self, *args):
        v = self.values
        for k in args[:-1]:
            if k not in v:
                return
            v = v[k]
        v.pop(args[-1], None)
