# -*- coding: utf-8 -*-

from copy import copy
from posixpath import sep, join

from .compat import StrConv, unicode


class WorkingPath(StrConv, object):
    def __init__(self):
        self.split_path = []
        self.previous = copy(self.split_path)

    def cd1(self, user_input):
        """
        Append *one* level to the current path.
        This means that separators (/) will get escaped.
        """
        split_path = self.get()
        split_path.append(user_input)
        self.location(split_path)

    def location(self, split_path):
        """
        Go to a new path, and store the previous path.
        """
        self.previous = self.get()
        self.split_path = split_path

    def restore(self):
        """
        Go to the previous path
        """
        self.split_path, self.previous = self.previous, self.split_path

    def home(self):
        """
        Go to the root
        """
        self.location([])

    def up(self):
        """
        Go up one directory
        """
        self.location(self.split_path[:-1])

    def get(self):
        """
        Get the current working path
        """
        return copy(self.split_path)

    def __unicode__(self):
        return join(sep, *[s.replace(u'/', u'\/') for s in self.split_path])


def test():
    wp = WorkingPath()
    assert wp.get() == []
    assert unicode(wp) == u'/'
    wp.cd1(u'lol')
    assert wp.get() == [u'lol']
    assert unicode(wp) == u'/lol'
    wp.cd1(u'cat')
    assert wp.get() == [u'lol', u'cat']
    assert unicode(wp) == u'/lol/cat'
    wp.restore()
    assert unicode(wp) == u'/lol'
    wp.home()
    assert wp.get() == []
    assert unicode(wp) == u'/'
    wp.up()
    assert wp.get() == []
    assert unicode(wp) == u'/'
    wp.location(['aa / aa', 'bbbb'])
    assert unicode(wp) == u'/aa \/ aa/bbbb'
    wp.up()
    assert unicode(wp) == u'/aa \/ aa'
    wp.cd1(u'héhé/hé')
    assert unicode(wp) == u'/aa \/ aa/héhé\/hé'
