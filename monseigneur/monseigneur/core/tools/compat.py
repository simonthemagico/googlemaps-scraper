# -*- coding: utf-8 -*-

import sys
import pickle


__all__ = ['unicode', 'long', 'basestring', 'range',
           'with_metaclass', 'unpickle',
           'quote', 'quote_plus', 'unquote', 'unquote_plus',
           'urlparse', 'urlunparse', 'urlsplit', 'urlunsplit',
           'urlencode', 'urljoin', 'parse_qs', 'parse_qsl',
           'getproxies',
           ]


try:
    unicode = unicode
except NameError:
    unicode = str

try:
    long = long
except NameError:
    long = int

try:
    basestring = basestring
except NameError:
    basestring = str


try:
    range = xrange
except NameError:
    range = range


try:
    from future.utils import with_metaclass
except ImportError:
    from six import with_metaclass


if sys.version_info.major == 2:
    class StrConv(object):
        def __str__(self):
            if hasattr(self, '__unicode__'):
                return self.__unicode__().encode('utf-8')
            else:
                return repr(self)
else:
    class StrConv(object):
        def __str__(self):
            if hasattr(self, '__unicode__'):
                return self.__unicode__()
            else:
                return repr(self)


try:
    from urllib import quote as _quote, quote_plus as _quote_plus, unquote as _unquote, unquote_plus as _unquote_plus, urlencode as _urlencode, getproxies
    from urlparse import urlparse, urlunparse, urljoin, urlsplit, urlunsplit, parse_qsl as _parse_qsl, parse_qs as _parse_qs

    def _reencode(s):
        if isinstance(s, unicode):
            s = s.encode('utf-8')
        return s

    def quote(p, *args, **kwargs):
        return _quote(_reencode(p), *args, **kwargs)

    def quote_plus(p, *args, **kwargs):
        return _quote_plus(_reencode(p), *args, **kwargs)

    def urlencode(d, *args, **kwargs):
        if hasattr(d, 'items'):
            d = list(d.items())
        else:
            d = list(d)

        d = [(_reencode(k), _reencode(v)) for k, v in d]

        return _urlencode(d, *args, **kwargs)

    def unquote(s):
        s = _reencode(s)
        return _unquote(s).decode('utf-8')

    def unquote_plus(s):
        s = _reencode(s)
        return _unquote_plus(s).decode('utf-8')

    def parse_qs(s):
        s = _reencode(s)
        orig = _parse_qs(s)
        return {k.decode('utf-8'): [vv.decode('utf-8') for vv in v] for k, v in orig.items()}

    def parse_qsl(s):
        s = _reencode(s)
        return [(k.decode('utf-8'), v.decode('utf-8')) for k, v in _parse_qsl(s)]

except ImportError:
    from urllib.parse import (
        urlparse, urlunparse, urlsplit, urlunsplit, urljoin, urlencode,
        quote, quote_plus, unquote, unquote_plus, parse_qsl, parse_qs,
    )
    from urllib.request import getproxies

def unpickle(pickled_data):
    if sys.version_info.major < 3:
        pyobject = pickle.loads(pickled_data)
    else:  # Assuming future Python versions will not remove encoding argument
        pyobject = pickle.loads(pickled_data, encoding='UTF-8')
    return pyobject


def test_base():
    assert type(range(3)) != list
    assert type(u'') == unicode
    assert type(b'') == bytes
    assert isinstance(u'', basestring)


def test_url():
    assert quote( 'foo=é&bar=qux ,/%') == u'foo%3D%C3%A9%26bar%3Dqux%20%2C/%25'
    assert quote(u'foo=é&bar=qux ,/%') == u'foo%3D%C3%A9%26bar%3Dqux%20%2C/%25'

    assert quote_plus( 'foo=é&bar=qux ,/%') == u'foo%3D%C3%A9%26bar%3Dqux+%2C%2F%25'
    assert quote_plus(u'foo=é&bar=qux ,/%') == u'foo%3D%C3%A9%26bar%3Dqux+%2C%2F%25'

    assert unquote( 'foo%3D%C3%A9%26bar%3Dqux%20%2C/%25') == u'foo=é&bar=qux ,/%'
    assert unquote(u'foo%3D%C3%A9%26bar%3Dqux%20%2C/%25') == u'foo=é&bar=qux ,/%'

    assert unquote_plus( 'foo%3D%C3%A9%26bar%3Dqux+%2C%2F%25') == u'foo=é&bar=qux ,/%'
    assert unquote_plus(u'foo%3D%C3%A9%26bar%3Dqux+%2C%2F%25') == u'foo=é&bar=qux ,/%'

    assert urlencode([( 'foo', u'é'), ( 'bar',  'qux ,/%')]) == u'foo=%C3%A9&bar=qux+%2C%2F%25'
    assert urlencode([(u'foo', u'é'), (u'bar', u'qux ,/%')]) == u'foo=%C3%A9&bar=qux+%2C%2F%25'

    assert urlencode(dict([( 'foo', u'é'), ( 'bar',  'qux ,/%')])) == u'foo=%C3%A9&bar=qux+%2C%2F%25'
    assert urlencode(dict([(u'foo', u'é'), (u'bar', u'qux ,/%')])) == u'foo=%C3%A9&bar=qux+%2C%2F%25'

    assert parse_qs( 'foo=%C3%A9&bar=qux+%2C%2F%25') == dict([(u'foo', [u'é']), (u'bar', [u'qux ,/%'])])
    assert parse_qs(u'foo=%C3%A9&bar=qux+%2C%2F%25') == dict([(u'foo', [u'é']), (u'bar', [u'qux ,/%'])])

    assert parse_qsl( 'foo=%C3%A9&bar=qux+%2C%2F%25') == [(u'foo', u'é'), (u'bar', u'qux ,/%')]
    assert parse_qsl(u'foo=%C3%A9&bar=qux+%2C%2F%25') == [(u'foo', u'é'), (u'bar', u'qux ,/%')]
