# -*- coding: utf-8 -*-

import logging
import os
import tempfile
import sys

import core.tools.date
import yaml

from .iconfig import ConfigError, IConfig

try:
    from yaml import CLoader as Loader
    from yaml import CDumper as Dumper
except ImportError:
    from yaml import Loader
    from yaml import Dumper


__all__ = ['YamlConfig']


class MonseigneurDumper(Dumper):
    pass


MonseigneurDumper.add_representer(core.tools.date.date, MonseigneurDumper.represent_date)

MonseigneurDumper.add_representer(core.tools.date.datetime, MonseigneurDumper.represent_datetime)


class YamlConfig(IConfig):
    def __init__(self, path):
        self.path = path
        self.values = {}

    def load(self, default={}):
        self.values = default.copy()

        logging.debug(u'Loading application configuration file: %s.' % self.path)
        try:
            with open(self.path, 'r') as f:
                self.values = yaml.load(f, Loader=Loader)
            logging.debug(u'Application configuration file loaded: %s.' % self.path)
        except IOError:
            self.save()
            logging.debug(u'Application configuration file created with default values: %s. Please customize it.' % self.path)

        if self.values is None:
            self.values = {}

    def save(self):
        # write in a temporary file to avoid corruption problems
        if sys.version_info.major == 2:
            f = tempfile.NamedTemporaryFile(dir=os.path.dirname(self.path), delete=False)
        else:
            f = tempfile.NamedTemporaryFile(mode='w', dir=os.path.dirname(self.path), delete=False, encoding='utf-8')
        with f:
            yaml.dump(self.values, f, Dumper=MonseigneurDumper, default_flow_style=False)
        if os.path.isfile(self.path):
            os.remove(self.path)
        os.rename(f.name, self.path)

    def get(self, *args, **kwargs):
        v = self.values
        for a in args[:-1]:
            try:
                v = v[a]
            except KeyError:
                if 'default' in kwargs:
                    v[a] = {}
                    v = v[a]
                else:
                    raise ConfigError()
            except TypeError:
                raise ConfigError()

        try:
            v = v[args[-1]]
        except KeyError:
            v = kwargs.get('default')

        return v

    def set(self, *args):
        v = self.values
        for a in args[:-2]:
            try:
                v = v[a]
            except KeyError:
                v[a] = {}
                v = v[a]
            except TypeError:
                raise ConfigError()

        v[args[-2]] = args[-1]

    def delete(self, *args):
        v = self.values
        for a in args[:-1]:
            try:
                v = v[a]
            except KeyError:
                return
            except TypeError:
                raise ConfigError()

        v.pop(args[-1], None)
