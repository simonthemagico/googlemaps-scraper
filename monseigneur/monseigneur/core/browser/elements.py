# -*- coding: utf-8 -*-

from __future__ import print_function

import os
import re
import sys
from collections import OrderedDict
from copy import deepcopy
import traceback

import lxml.html

from monseigneur.monseigneur.core.tools.log import getLogger, DEBUG_FILTERS
from monseigneur.monseigneur.core.tools.compat import basestring, unicode, with_metaclass
from monseigneur.monseigneur.core.browser.pages import NextPage
from monseigneur.monseigneur.core.capabilities.base import FetchError

from .filters.standard import _Filter, CleanText
from .filters.html import AttributeNotFound, XPathNotFound


__all__ = ['DataError', 'AbstractElement', 'ListElement', 'ItemElement', 'TableElement', 'SkipItem']


def generate_table_element(doc, head_xpath, cleaner=CleanText):
    """
    Prints generated base code for TableElement/TableCell usage.
    It is intended for development purposes, typically in monseigneur-debug.
    :param doc: lxml tree of the page (e.g. browser.page.doc)
    :param head_xpath: xpath of header columns (e.g. //table//th)
    :type head_xpath: str
    :param cleaner: cleaner class (Filter)
    :type cleaner: Filter
    """
    from unidecode import unidecode
    indent = 4
    headers = doc.xpath(head_xpath)
    cols = dict()
    for el in headers:
        th = cleaner.clean(el)
        cols.update({re.sub('[^a-zA-Z]', '_', unidecode(th)).lower(): th})

    print(' ' * indent + '@method')
    print(' ' * indent + 'class get_items(TableElement):')
    if cleaner is not CleanText:
        print(' ' * indent * 2 + 'cleaner = %s' % cleaner.__name__)
    print(' ' * indent * 2 + 'head_xpath = ' + repr(head_xpath))
    print(' ' * indent * 2 + 'item_xpath = ' + repr('...') + '\n')

    for col, name in cols.items():
        print(' ' * indent * 2 + 'col_' + col + ' = ' + repr(name))

    print('\n' + ' ' * indent * 2 + 'class item(ItemElement):')
    print(' ' * indent * 3 + 'klass = BaseObject' + '\n')

    for col in cols:
        print(' ' * indent * 3 + 'obj_' + col + ' = ' + "TableCell('%s') & CleanText()" % col)


class DataError(Exception):
    """
    Returned data from pages are incoherent.
    """


def method(klass):
    """
    Class-decorator to call it as a method.
    """

    def inner(self, *args, **kwargs):
        return klass(self)(*args, **kwargs)
    return inner


class AbstractElement(object):
    _creation_counter = 0
    condition = None

    def __init__(self, page, parent=None, el=None):
        self.page = page
        self.parent = parent
        if el is not None:
            self.el = el
        elif parent is not None:
            self.el = parent.el
        else:
            self.el = page.doc

        if parent is not None:
            self.env = deepcopy(parent.env)
        else:
            self.env = deepcopy(page.params)

        # Used by debug
        self._random_id = AbstractElement._creation_counter
        AbstractElement._creation_counter += 1

        self.loaders = {}

    def use_selector(self, func, key=None):
        if isinstance(func, _Filter):
            func._obj = self
            func._key = key
            value = func(self)
        elif isinstance(func, type) and issubclass(func, ItemElement):
            value = func(self.page, self, self.el)()
        elif isinstance(func, type) and issubclass(func, ListElement):
            value = list(func(self.page, self, self.el)())
        elif callable(func):
            value = func()
        else:
            value = deepcopy(func)

        return value

    def parse(self, obj):
        pass

    def cssselect(self, *args, **kwargs):
        return self.el.cssselect(*args, **kwargs)

    def xpath(self, *args, **kwargs):
        return self.el.xpath(*args, **kwargs)

    def handle_loaders(self):
        for attrname in dir(self):
            m = re.match('load_(.*)', attrname)
            if not m:
                continue
            name = m.group(1)
            if name in self.loaders:
                continue
            loader = getattr(self, attrname)
            self.loaders[name] = self.use_selector(loader, key=attrname)


class ListElement(AbstractElement):
    item_xpath = None
    flush_at_end = False
    ignore_duplicate = False

    def __init__(self, *args, **kwargs):
        super(ListElement, self).__init__(*args, **kwargs)
        self.logger = getLogger(self.__class__.__name__.lower())
        self.objects = OrderedDict()

    def __call__(self, *args, **kwargs):
        for key, value in kwargs.items():
            self.env[key] = value

        return self.__iter__()

    def find_elements(self):
        """
        Get the nodes that will have to be processed.
        This method can be overridden if xpath filters are not
        sufficient.
        """
        if self.item_xpath is not None:
            for el in self.el.xpath(self.item_xpath):
                yield el
        else:
            yield self.el

    def __iter__(self):
        if self.condition is not None and not self.condition():
            return

        self.parse(self.el)

        items = []
        for el in self.find_elements():
            for attrname in dir(self):
                attr = getattr(self, attrname)
                if isinstance(attr, type) and issubclass(attr, AbstractElement) and attr != type(self):
                    item = attr(self.page, self, el)
                    if item.condition is not None and not item.condition():
                        continue

                    item.handle_loaders()
                    items.append(item)

        for item in items:
            for obj in item:
                obj = self.store(obj)
                if obj and not self.flush_at_end:
                    yield obj

        if self.flush_at_end:
            for obj in self.flush():
                yield obj

        self.check_next_page()

    def flush(self):
        for obj in self.objects.values():
            yield obj

    def check_next_page(self):
        if not hasattr(self, 'next_page'):
            return

        next_page = getattr(self, 'next_page')
        try:
            value = self.use_selector(next_page)
        except (AttributeNotFound, XPathNotFound):
            return

        if value is None:
            return
        raise NextPage(value)


    def store(self, obj):
        if obj.id:
            if obj.id in self.objects:
                if self.ignore_duplicate:
                    self.logger.warning('There are two objects with the same ID! %s' % obj.id)
                    return
                else:
                    raise DataError('There are two objects with the same ID! %s' % obj.id)
            self.objects[obj.id] = obj
        return obj


class SkipItem(Exception):
    """
    Raise this exception in an :class:`ItemElement` subclass to skip an item.
    """


class _ItemElementMeta(type):
    """
    Private meta-class used to keep order of obj_* attributes in :class:`ItemElement`.
    """
    def __new__(mcs, name, bases, attrs):
        _attrs = []
        for base in bases:
            if hasattr(base, '_attrs'):
                _attrs += base._attrs

        filters = [(re.sub('^obj_', '', attr_name), attrs[attr_name]) for attr_name, obj in attrs.items() if attr_name.startswith('obj_')]
        # constants first, then filters, then methods
        filters.sort(key=lambda x: x[1]._creation_counter if hasattr(x[1], '_creation_counter') else (sys.maxsize if callable(x[1]) else 0))

        attrs['_class_file'], attrs['_class_line'] = traceback.extract_stack()[-2][:2]
        new_class = super(_ItemElementMeta, mcs).__new__(mcs, name, bases, attrs)
        new_class._attrs = _attrs + [f[0] for f in filters]
        return new_class


class ItemElement(with_metaclass(_ItemElementMeta, AbstractElement)):
    _attrs = None
    _loaders = None
    klass = None
    validate = None
    skip_optional_fields_errors = False

    class Index(object):
        pass

    def __init__(self, *args, **kwargs):
        super(ItemElement, self).__init__(*args, **kwargs)
        self.logger = getLogger(self.__class__.__name__.lower())
        self.obj = None
        self.saved_attrib = {}  # safer way would be to clone lxml tree

    def build_object(self):
        if self.klass is None:
            return
        return self.klass()

    def _restore_attrib(self):
        for el in self.saved_attrib:
            el.attrib.clear()
            el.attrib.update(self.saved_attrib[el])
        self.saved_attrib = {}

    def should_highlight(self):
        try:
            responses_dirname = self.page.browser.responses_dirname and self.page.browser.highlight_el
            if not responses_dirname:
                return False
            if not self.el.getroottree():
                return False
        except AttributeError:
            return False
        else:
            return True

    def _write_highlighted(self):
        if not self.should_highlight():
            return

        responses_dirname = self.page.browser.responses_dirname
        html = lxml.html.tostring(self.el.getroottree().getroot())

        fn = os.path.join(responses_dirname, 'obj-%s.html' % self._random_id)
        with open(fn, 'w') as fd:
            fd.write(html)
        self.logger.debug('highlighted object to %s', fn)

    def __call__(self, obj=None):
        if obj is not None:
            self.obj = obj

        for obj in self:
            return obj

    def __iter__(self):
        if self.condition is not None and not self.condition():
            return

        highlight = False
        try:
            if self.should_highlight():
                self.saved_attrib[self.el] = dict(self.el.attrib)
                self.el.attrib['style'] = 'color: white !important; background: orange !important;'

            try:
                if self.obj is None:
                    self.obj = self.build_object()
                self.parse(self.el)
                self.handle_loaders()
                for attr in self._attrs:
                    self.handle_attr(attr, getattr(self, 'obj_%s' % attr))
            except SkipItem:
                return

            if self.validate is not None and not self.validate(self.obj):
                return

            highlight = True
        finally:
            if highlight:
                self._write_highlighted()
            self._restore_attrib()

        yield self.obj

    def handle_attr(self, key, func):
        try:
            value = self.use_selector(func, key=key)
        except SkipItem as e:
            # Help debugging as tracebacks do not give us the key
            self.logger.debug("Attribute %s raises a %r", key, e)
            raise
        except Exception as e:
            # If we are here, we have probably a real parsing issue
            self.logger.warning('Attribute %s (in %s:%s) raises %s', key, self._class_file, self._class_line, repr(e))
            if not self.skip_optional_fields_errors or key not in self.obj._fields or self.obj._fields[key].mandatory:
                raise
            else:
                value = FetchError
        logger = getLogger('b2filters')
        logger.log(DEBUG_FILTERS, "%s.%s = %r" % (self._random_id, key, value))
        setattr(self.obj, key, value)


class TableElement(ListElement):
    head_xpath = None
    cleaner = CleanText

    def __init__(self, *args, **kwargs):
        super(TableElement, self).__init__(*args, **kwargs)

        self._cols = {}

        columns = {}
        for attrname in dir(self):
            m = re.match('col_(.*)', attrname)
            if m:
                cols = getattr(self, attrname)
                if not isinstance(cols, (list,tuple)):
                    cols = [cols]
                columns[m.group(1)] = [s.lower() if isinstance(s, (str, unicode)) else s for s in cols]

        colnum = 0
        for el in self.el.xpath(self.head_xpath):
            title = self.cleaner.clean(el)
            for name, titles in columns.items():
                if name in self._cols:
                    continue
                if title.lower() in [s for s in titles if isinstance(s, (str, unicode))] or \
                   any(map(lambda x: x.match(title), [s for s in titles if isinstance(s, type(re.compile('')))])):
                    self._cols[name] = colnum
            try:
                colnum += int(el.attrib.get('colspan', 1))
            except (ValueError, AttributeError):
                colnum += 1

    def get_colnum(self, name):
        return self._cols.get(name, None)


class DictElement(ListElement):
    def find_elements(self):
        if self.item_xpath is None:
            selector = []

        elif isinstance(self.item_xpath, basestring):
            selector = self.item_xpath.split('/')

        else:
            selector = self.item_xpath

        bases = [self.el]
        for key in selector:
            if key == '*':
                bases = sum([el if isinstance(el, list) else list(el.values()) for el in bases], [])
            else:
                try:
                    bases = [el[int(key)] if isinstance(el, list) else el[key] for el in bases]
                except KeyError:
                    self.logger.error(selector)
                    raise

        for base in bases:
            for el in base:
                yield el


def magic_highlight(els, open_browser=True):
    """Open a web browser with the document open and the element highlighted"""

    import lxml.html
    import webbrowser
    import tempfile

    if not els:
        raise Exception('no elements to highlight')

    if not isinstance(els, (list, tuple)):
        els = [els]

    saved = {}
    for el in els:
        saved[el] = el.attrib.get('style', '')
        el.attrib['style'] = 'color: white !important; background: red !important;'

    html = lxml.html.tostring(el.xpath('/*')[0])
    for el in els:
        el.attrib['style'] = saved[el]

    _, fn = tempfile.mkstemp(dir='/tmp', prefix='monseigneur-highlight', suffix='.html')
    with open(fn, 'w') as fd:
        fd.write(html)

    print('Saved to %r' % fn)
    if open_browser:
        webbrowser.open('file://%s' % fn)
