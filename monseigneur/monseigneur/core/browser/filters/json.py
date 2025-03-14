# -*- coding: utf-8 -*-

from monseigneur.monseigneur.core.tools.compat import basestring, with_metaclass

from .base import _Filter, _NO_DEFAULT, Filter, debug, ItemNotFound

__all__ = ['Dict']


class NotFound(object):
    def __repr__(self):
        return 'NOT_FOUND'

_NOT_FOUND = NotFound()


class _DictMeta(type):
    def __getitem__(cls, name):
        return cls(name)


class Dict(with_metaclass(_DictMeta, Filter)):
    def __init__(self, selector=None, default=_NO_DEFAULT):
        super(Dict, self).__init__(self, default=default)
        if selector is None:
            self.selector = []
        elif isinstance(selector, basestring):
            self.selector = selector.split('/')
        elif callable(selector):
            self.selector = [selector]
        else:
            self.selector = selector

    def __getitem__(self, name):
        self.selector.append(name)
        return self

    @debug()
    def filter(self, elements):
        if elements is not _NOT_FOUND:
            return elements
        else:
            return self.default_or_raise(ItemNotFound('Element %r not found' % self.selector))

    @classmethod
    def select(cls, selector, item, obj=None, key=None):
        if isinstance(item, (dict, list)):
            content = item
        else:
            content = item.el

        for el in selector:
            if isinstance(content, list):
                el = int(el)
            elif isinstance(el, _Filter):
                el._key = key
                el._obj = obj
                el = el(item)
            elif callable(el):
                el = el(item)

            try:
                content = content[el]
            except (KeyError, IndexError, TypeError):
                return _NOT_FOUND

        return content
