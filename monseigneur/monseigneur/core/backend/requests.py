# -*- coding: utf-8 -*-

from threading import RLock
from collections import defaultdict


__all__ = ['RequestsManager']


class RequestsManager(object):
    def __init__(self):
        self.callbacks = defaultdict(lambda: lambda *args, **kwargs: None)
        self.lock = RLock()

    def request(self, name, *args, **kwargs):
        with self.lock:
            return self.callbacks[name](*args, **kwargs)

    def register(self, name, callback):
        self.callbacks[name] = callback
