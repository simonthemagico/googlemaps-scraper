# -*- coding: utf-8 -*-

import datetime

try:
    import feedparser
except ImportError:
    raise ImportError('Please install python-feedparser')


__all__ = ['Entry', 'Newsfeed']


class Entry(object):
    def __init__(self, entry, rssid_func=None):
        if hasattr(entry, 'id'):
            self.id = entry.id
        else:
            self.id = None

        if "link" in entry:
            self.link = entry["link"]
            if not self.id:
                self.id = entry["link"]
        else:
            self.link = None

        if "title" in entry:
            self.title = entry["title"]
        else:
            self.title = None

        if "author" in entry:
            self.author = entry["author"]
        else:
            self.author = None

        if "updated_parsed" in entry:
            self.datetime = datetime.datetime(*entry['updated_parsed'][:7])
        elif "published_parsed" in entry:
            self.datetime = datetime.datetime(*entry['published_parsed'][:7])
        else:
            self.datetime = None

        if "summary" in entry:
            self.summary = entry["summary"]
        else:
            self.summary = None

        self.content = []
        if "content" in entry:
            for i in entry["content"]:
                self.content.append(i.value)
        elif self.summary:
            self.content.append(self.summary)

        if "wfw_commentrss" in entry:
            self.rsscomment = entry["wfw_commentrss"]
        else:
            self.rsscomment = None

        if rssid_func:
            self.id = rssid_func(self)


class Newsfeed(object):
    def __init__(self, url, rssid_func=None):
        self.feed = feedparser.parse(url)
        self.rssid_func = rssid_func

    def iter_entries(self):
        for entry in self.feed['entries']:
            yield Entry(entry, self.rssid_func)

    def get_entry(self, id):
        for entry in self.iter_entries():
            if entry.id == id:
                return entry
