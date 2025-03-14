# -*- coding: utf-8 -*-

from __future__ import absolute_import

from decimal import Decimal
from datetime import datetime, date, time, timedelta

__all__ = ['json', 'mini_jsonpath']

try:
    # try simplejson first because it is faster
    # However, note that simplejson has very different behaviors from the
    # stdlib json module. In particular, it is handling Decimal in a very
    # peculiar way and is not returning a string for them.
    import simplejson as json
except ImportError:
    # Python 2.6+ has a module similar to simplejson
    import json

from monseigneur.monseigneur.core.capabilities.base import BaseObject, NotAvailable, NotLoaded
from monseigneur.monseigneur.core.tools.compat import basestring


def mini_jsonpath(node, path):
    """
    Evaluates a dot separated path against JSON data. Path can contains
    star wilcards. Always returns a generator.

    Relates to http://goessner.net/articles/JsonPath/ but in a really basic
    and simpler form.

    >>> list(mini_jsonpath({"x": 95, "y": 77, "z": 68}, 'y'))
    [77]
    >>> list(mini_jsonpath({"x": {"y": {"z": "nested"}}}, 'x.y.z'))
    ['nested']
    >>> list(mini_jsonpath('{"data": [{"x": "foo", "y": 13}, {"x": "bar", "y": 42}, {"x": "baz", "y": 128}]}', 'data.*.y'))
    [13, 42, 128]
    """

    def iterkeys(i):
        return range(len(i)) if isinstance(i, list) else i

    def cut(s):
        p = s.split('.', 1) if s else [None]
        return p + [None] if len(p) == 1 else p

    if isinstance(node, basestring):
        node = json.loads(node)

    queue = [(node, cut(path))]
    while queue:
        node, (name, rest) = queue.pop(0)
        if name is None:
            yield node
            continue
        elif name == '*':
            keys = iterkeys(node)
        elif type(node) not in (dict, list) or name not in node:
            continue
        else:
            keys = [int(name) if type(node) is list else name]
        for k in keys:
            queue.append((node[k], cut(rest)))


class MonseigneurEncoder(json.JSONEncoder):
    """JSON encoder class for core objects (and Decimal and dates)

    >>> json.dumps(object, cls=MonseigneurEncoder)
    '{"id": "1234@backend", "url": null}'
    """

    def __init__(self, *args, **kwargs):
        # avoid simplejson internal Decimal handling
        if 'use_decimal' in kwargs:
            kwargs['use_decimal'] = False
        super(MonseigneurEncoder, self).__init__(*args, **kwargs)

    def default(self, o):
        if o is NotAvailable:
            return None
        elif o is NotLoaded:
            return None
        elif isinstance(o, BaseObject):
            return o.to_dict()
        elif isinstance(o, Decimal):
            return str(o)
        elif isinstance(o, (datetime, date, time)):
            return o.isoformat()
        elif isinstance(o, timedelta):
            return o.total_seconds()
        return super(MonseigneurEncoder, self).default(o)
