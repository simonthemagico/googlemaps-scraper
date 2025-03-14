# -*- coding: utf-8 -*-

from collections import OrderedDict

__all__ = ['LimitedLRUDict', 'LRUDict']


class LRUDict(OrderedDict):
    """dict to store items in the order the keys were last added/fetched."""

    def __setitem__(self, key, value):
        if key in self:
            del self[key]
        super(LRUDict, self).__setitem__(key, value)

    def __getitem__(self, key):
        value = super(LRUDict, self).__getitem__(key)
        self[key] = value
        return value


class LimitedLRUDict(LRUDict):
    """dict to store only the N most recent items."""

    max_entries = 100

    def __setitem__(self, key, value):
        super(LimitedLRUDict, self).__setitem__(key, value)
        if len(self) > self.max_entries:
            self.popitem(last=False)
