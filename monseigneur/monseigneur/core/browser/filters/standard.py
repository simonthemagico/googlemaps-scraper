# -*- coding: utf-8 -*-

from __future__ import absolute_import

import datetime
import dateparser
import re
import unicodedata
from collections.abc import Iterator
from decimal import Decimal, InvalidOperation
from itertools import islice

from dateutil.parser import parse as parse_date

from monseigneur.monseigneur.core.browser.url import URL
from monseigneur.monseigneur.core.capabilities.base import Currency as BaseCurrency
from monseigneur.monseigneur.core.capabilities.base import empty
from monseigneur.monseigneur.core.tools.compat import basestring, long, parse_qs, unicode, urlparse

from .base import _NO_DEFAULT, Filter, FilterError, ItemNotFound, _Filter, debug

__all__ = ['FilterError', 'ColumnNotFound', 'RegexpError', 'FormatError',
           'Filter', 'Base', 'Env', 'TableCell', 'RawText',
           'CleanText', 'Lower', 'Upper', 'Capitalize', 'CleanDecimal',
           'Field', 'Regexp', 'Map', 'DateTime', 'Date', 'Time', 'CleanDate', 'DateGuesser',
           'Duration', 'MultiFilter', 'CombineDate', 'Format', 'Join', 'Type',
           'Eval', 'BrowserURL', 'Async', 'AsyncLoad',
           'QueryValue', 'Coalesce']


class ColumnNotFound(FilterError):
    pass


class RegexpError(FilterError):
    pass


class FormatError(FilterError):
    pass


class AsyncLoad(Filter):
    """Load a page asynchronously for later use.

    Often used in combination with :class:`Async` filter.
    """

    def __call__(self, item):
        link = self.select(self.selector, item)
        return item.page.browser.async_open(link) if link else None


class Async(Filter):
    """Selector that uses another page fetched earlier.

    Often used in combination with :class:`AsyncLoad` filter.
    Requires that the other page's URL is matched with a Page by the Browser.

    Example::

        class item(ItemElement):
            load_details = Field('url') & AsyncLoad

            obj_description = Async('details') & CleanText('//h3')
    """

    def __init__(self, name, selector=None):
        super(Async, self).__init__()
        self.selector = selector
        self.name = name

    def __and__(self, o):
        if isinstance(o, type) and issubclass(o, _Filter):
            o = o()
        self.selector = o
        return self

    def __call__(self, item):
        if item.loaders[self.name] is None:
            return None

        return self.select(self.selector, self.loaded_page(item).doc)

    def filter(self, *args):
        raise AttributeError()

    def loaded_page(self, item):
        result = item.loaders[self.name].result()
        assert result.page is not None, 'The loaded url %s hasn\'t been matched by an URL object' % result.url
        return result.page


class Base(Filter):
    """
    Change the base element used in filters.

    >>> Base(Env('header'), CleanText('./h1'))  # doctest: +SKIP
    """

    def __call__(self, item):
        base = self.select(self.base, item)
        return self.select(self.selector, base)

    def __init__(self, base, selector=None, default=_NO_DEFAULT):
        super(Base, self).__init__(selector, default)
        self.base = base


class Decode(Filter):
    """
    Filter that aims to decode urlencoded strings

    >>> Decode(Env('_id'))  # doctest: +ELLIPSIS
    <core.browser.filters.standard.Decode object at 0x...>
    >>> from .html import Link
    >>> Decode(Link('./a'))  # doctest: +ELLIPSIS
    <core.browser.filters.standard.Decode object at 0x...>
    """

    def __call__(self, item):
        self.encoding = item.page.ENCODING if item.page.ENCODING else 'utf-8'
        return self.filter(self.select(self.selector, item))

    @debug()
    def filter(self, txt):
        try:
            try:
                from urllib.parse import unquote
                txt = unquote(txt, self.encoding)
            except ImportError:
                from urllib import unquote
                txt = unquote(txt.encode('ascii')).decode(self.encoding)
        except (UnicodeDecodeError, UnicodeEncodeError):
            pass

        return txt


class Env(_Filter):
    """
    Filter to get environment value of the item.

    It is used for example to get page parameters, or when there is a parse()
    method on ItemElement.
    """

    def __init__(self, name, default=_NO_DEFAULT):
        super(Env, self).__init__(default)
        self.name = name

    def __call__(self, item):
        try:
            return item.env[self.name]
        except KeyError:
            return self.default_or_raise(ItemNotFound('Environment variable %s not found' % self.name))


class TableCell(_Filter):
    """
    Used with TableElement, gets the cell element from its name.

    For example:

    >>> from alchemy.modules.seloger.tables import Agency
    >>> from core.browser.elements import TableElement, ItemElement
    >>> class table(TableElement):
    ...     head_xpath = '//table/thead/th'
    ...     item_xpath = '//table/tbody/tr'
    ...     col_date =    u'Date'
    ...     col_label =   [u'Name', u'Label']
    ...     class item(ItemElement):
    ...         klass = Agency
    ...         obj_date = Date(TableCell('date'))
    ...         obj_label = CleanText(TableCell('label'))
    ...

    The 'colspan' variable enables the handling of table tags that have
    a "colspan" attribute that modify the width of the column:
    for example <td colspan="2"> will occupy two columns instead of one,
    creating a column shift for all the next columns that must be taken
    in consideration when trying to match columns values with column heads.
    """

    def __init__(self, *names, **kwargs):
        support_th = kwargs.pop('support_th', False)
        self.colspan = kwargs.pop('colspan', False)
        super(TableCell, self).__init__(**kwargs)
        self.names = names

        if support_th:
            self.td = '(./th | ./td)[%s]'
        else:
            self.td = './td[%s]'

    """
    The two methods below are used to verify that modifying TableCell
    to handle colspans does not modify the class behavior in monseigneur modules.
    The "assert" should crash if a module does not return the same results
    with and without handling colspans.
    """

    def call_without_colspan(self, item):
        # Former behavior without handling colspans > 1
        for name in self.names:
            idx = item.parent.get_colnum(name)
            if idx is not None:
                ret = item.xpath(self.td % (idx + 1))
                for el in ret:
                    self.highlight_el(el, item)
                return ret
        return self.default_or_raise(ColumnNotFound('Unable to find column %s' % ' or '.join(self.names)))

    def call_with_colspan(self, item):
        # New behavior, handling colspans > 1
        for name in self.names:
            col_idx = item.parent.get_colnum(name)
            if col_idx is not None:
                current_col = 0
                for td_idx in range(col_idx + 1):
                    ret = item.xpath(self.td % (td_idx + 1))
                    if col_idx <= current_col:
                        for el in ret:
                            self.highlight_el(el, item)
                        return ret

                    if not ret:
                        # There might no be no TD at all
                        # ColumnNotFound seems for case when corresponding header is not found
                        # Thus for compat return empty
                        return []

                    current_col += int(ret[0].attrib.get('colspan', 1))

        return self.default_or_raise(ColumnNotFound('Unable to find column %s' % ' or '.join(self.names)))

    def __call__(self, item):
        if self.colspan:
            return self.call_with_colspan(item)

        ret_without_colspan = self.call_without_colspan(item)
        ret_with_colspan = self.call_with_colspan(item)
        assert ret_without_colspan == ret_with_colspan, 'Different behavior with and without colspan in TableCell'
        return ret_with_colspan


class RawText(Filter):
    """Get raw text from an element.

    Unlike :class:`CleanText`, whitespace is kept as is.
    """

    def __init__(self, selector=None, children=False, default=_NO_DEFAULT):
        """
        :param children: whether to get text from children elements of the select elements
        :type children: bool
        """

        super(RawText, self).__init__(selector, default=default)
        self.children = children

    @debug()
    def filter(self, el):
        if isinstance(el, (tuple, list)):
            return u' '.join([self.filter(e) for e in el])

        if self.children:
            text = el.text_content()
        else:
            text = el.text

        if text is None:
            result = self.default
        else:
            result = unicode(text)

        return result


class CleanText(Filter):
    """
    Get a cleaned text from an element.

    It first replaces all tabs and multiple spaces
    (including newlines if ``newlines`` is True)
    to one space and strips the result string.

    The result is coerced into unicode, and optionally normalized
    according to the ``normalize`` argument.

    Then it replaces all symbols given in the ``symbols`` argument.

    >>> CleanText().filter('coucou ') == u'coucou'
    True
    >>> CleanText().filter(u'coucou\xa0coucou') == u'coucou coucou'
    True
    >>> CleanText(newlines=True).filter(u'coucou\\r\\n coucou ') == u'coucou coucou'
    True
    >>> CleanText(newlines=False).filter(u'coucou\\r\\n coucou ') == u'coucou\\ncoucou'
    True
    """

    def __init__(self, selector=None, symbols='', replace=[], children=True, newlines=True, normalize='NFC', **kwargs):
        """
        :param symbols: list of strings to remove from text
        :type symbols: list
        :param replace: optional pairs of text replacements to perform
        :type replace: list[tuple[str, str]]
        :param children: whether to get text from children elements of the select elements
        :type children: bool
        :param newlines: if True, newlines will be converted to space too
        :type newlines: bool
        :param normalize: Unicode normalization to perform
        :type normalize: str or None
        """

        super(CleanText, self).__init__(selector, **kwargs)
        self.symbols = symbols
        self.toreplace = replace
        self.children = children
        self.newlines = newlines
        self.normalize = normalize

    @debug()
    def filter(self, txt):
        if isinstance(txt, (tuple, list)):
            txt = u' '.join([self.clean(item, children=self.children) for item in txt])

        txt = self.clean(txt, self.children, self.newlines, self.normalize)
        txt = self.remove(txt, self.symbols)
        txt = self.replace(txt, self.toreplace)
        # ensure it didn't become str by mistake
        return unicode(txt)

    @classmethod
    def clean(cls, txt, children=True, newlines=True, normalize='NFC'):
        if not isinstance(txt, basestring):
            if children:
                txt = [t.strip() for t in txt.itertext()]
            else:
                txt = [t.strip() for t in txt.xpath('./text()')]
            txt = u' '.join(txt)  # 'foo   bar'
        if newlines:
            txt = re.compile(r'\s+', flags=re.UNICODE).sub(' ', txt)  # 'foo bar'
        else:
            # normalize newlines and clean what is inside
            txt = '\n'.join([cls.clean(l) for l in txt.splitlines()])
        txt = txt.strip()
        # lxml under Python 2 returns str instead of unicode if it is pure ASCII
        txt = unicode(txt)
        # normalize to a standard Unicode form
        if normalize:
            txt = unicodedata.normalize(normalize, txt)
        return txt

    @classmethod
    def remove(cls, txt, symbols):
        for symbol in symbols:
            txt = txt.replace(symbol, '')
        return txt.strip()

    @classmethod
    def replace(cls, txt, replace):
        for before, after in replace:
            txt = txt.replace(before, after)
        return txt


class Lower(CleanText):
    """Extract text with :class:`CleanText` and convert to lower-case."""

    @debug()
    def filter(self, txt):
        txt = super(Lower, self).filter(txt)
        return txt.lower()


class Upper(CleanText):
    """Extract text with :class:`CleanText` and convert to upper-case."""

    @debug()
    def filter(self, txt):
        txt = super(Upper, self).filter(txt)
        return txt.upper()


class Capitalize(CleanText):
    """Extract text with :class:`CleanText` and capitalize it."""

    @debug()
    def filter(self, txt):
        txt = super(Capitalize, self).filter(txt)
        return txt.title()


class Title(CleanText):
    """Extract text with :class:`CleanText` and apply title() to it."""
    @debug()
    def filter(self, txt):
        txt = super(Title, self).filter(txt)
        return txt.title()


class Currency(CleanText):
    @debug()
    def filter(self, txt):
        txt = super(Currency, self).filter(txt)
        return BaseCurrency.get_currency(txt)


class NumberFormatError(FormatError, InvalidOperation):
    pass


class CleanDecimal(CleanText):
    """
    Get a cleaned Decimal value from an element.

    `replace_dots` is False by default. A dot is interpreted as a decimal separator.

    If `replace_dots` is set to True, we remove all the dots. The ',' is used as decimal
    separator (often useful for French values)

    If `replace_dots` is a tuple, the first element will be used as the thousands separator,
    and the second as the decimal separator.

    See http://en.wikipedia.org/wiki/Thousands_separator#Examples_of_use

    For example, for the UK style (as in 1,234,567.89):

    >>> CleanDecimal('./td[1]', replace_dots=(',', '.'))  # doctest: +SKIP
    """

    def __init__(self, selector=None, replace_dots=False, sign=None, legacy=True, default=_NO_DEFAULT):
        """
        :param sign: function accepting the text as param and returning the sign
        """

        super(CleanDecimal, self).__init__(selector, default=default)
        self.replace_dots = replace_dots
        self.sign = sign
        self.legacy = legacy
        if not legacy:
            thousands_sep, decimal_sep = self.replace_dots
            self.matching = re.compile(r'([+-]?)\s*(\d[\d%s%s]*|%s\d+)' % tuple(map(re.escape, (thousands_sep, decimal_sep, decimal_sep))))
            self.thousand_check = re.compile(r'^[+-]?\d{1,3}(%s\d{3})*(%s\d*)?$' % tuple(map(re.escape, (thousands_sep, decimal_sep))))

    @debug()
    def filter(self, text):
        if type(text) in (float, int, long):
            text = str(text)

        if empty(text):
            return self.default_or_raise(FormatError('Unable to parse %r' % text))

        original_text = text = super(CleanDecimal, self).filter(text)

        if self.legacy:
            if self.replace_dots:
                if type(self.replace_dots) is tuple:
                    thousands_sep, decimal_sep = self.replace_dots
                else:
                    thousands_sep, decimal_sep = '.', ','
                text = text.replace(thousands_sep, '').replace(decimal_sep, '.')

            text = re.sub(r'[^\d\-\.]', '', text)
        else:
            thousands_sep, decimal_sep = self.replace_dots

            matches = self.matching.findall(text)
            if not matches:
                return self.default_or_raise(NumberFormatError('There is no number to parse'))
            elif len(matches) > 1:
                return self.default_or_raise(NumberFormatError('There should be exactly one number to parse'))

            text = '%s%s' % (matches[0][0], matches[0][1].strip())

            if thousands_sep and thousands_sep in text and not self.thousand_check.match(text):
                return self.default_or_raise(NumberFormatError('Thousands separator is misplaced in %r' % text))

            text = text.replace(thousands_sep, '').replace(decimal_sep, '.')

        try:
            v = Decimal(text)
            if self.sign:
                v *= self.sign(original_text)
            return v
        except InvalidOperation as e:
            return self.default_or_raise(NumberFormatError(e))

    @classmethod
    def US(cls, *args, **kwargs):
        kwargs['legacy'] = False
        kwargs['replace_dots'] = (',', '.')
        return cls(*args, **kwargs)

    @classmethod
    def French(cls, *args, **kwargs):
        kwargs['legacy'] = False
        kwargs['replace_dots'] = (' ', ',')
        return cls(*args, **kwargs)

    @classmethod
    def SI(cls, *args, **kwargs):
        kwargs['legacy'] = False
        kwargs['replace_dots'] = (' ', '.')
        return cls(*args, **kwargs)


class Slugify(Filter):
    @debug()
    def filter(self, label):
        label = re.sub(r'[^A-Za-z0-9]', ' ', label.lower()).strip()
        label = re.sub(r'\s+', '-', label)
        return label


class Type(Filter):
    """
    Get a cleaned value of any type from an element text.
    The type_func can be any callable (class, function, etc.).
    By default an empty string will not be parsed but it can be changed
    by specifying minlen=False. Otherwise, a minimal length can be specified.

    >>> Type(CleanText('./td[1]'), type=int)  # doctest: +SKIP

    >>> Type(type=int).filter(42)
    42
    >>> Type(type=int).filter('42')
    42
    >>> Type(type=int, default='NaN').filter('')
    'NaN'
    >>> Type(type=list, minlen=False, default=list('ab')).filter('')
    []
    >>> Type(type=list, minlen=0, default=list('ab')).filter('')
    ['a', 'b']
    """

    def __init__(self, selector=None, type=None, minlen=0, default=_NO_DEFAULT):
        super(Type, self).__init__(selector, default=default)
        self.type_func = type
        self.minlen = minlen

    @debug()
    def filter(self, txt):
        if isinstance(txt, self.type_func):
            return txt
        if empty(txt):
            return self.default_or_raise(FormatError('Unable to parse %r' % txt))
        if self.minlen is not False and len(txt) <= self.minlen:
            return self.default_or_raise(FormatError('Unable to parse %r' % txt))
        try:
            return self.type_func(txt)
        except ValueError as e:
            return self.default_or_raise(FormatError('Unable to parse %r: %s' % (txt, e)))


class Field(_Filter):
    """
    Get the attribute of object.

    Example::

        obj_foo = CleanText('//h1')
        obj_bar = Field('foo')

    will make "bar" field equal to "foo" field.
    """

    def __init__(self, name):
        super(Field, self).__init__()
        self.name = name

    def __call__(self, item):
        return item.use_selector(getattr(item, 'obj_%s' % self.name), key=self._key)


# Based on nth from https://docs.python.org/2/library/itertools.html
def nth(iterable, n, default=None):
    "Returns the nth item or a default value, n can be negative, or '*' for all"
    if n == '*':
        return iterable
    if n < 0:
        iterable = reversed(list(iterable))
        n = abs(n) - 1
    return next(islice(iterable, n, None), default)


def ordinal(n):
    "To have some readable debug information: '*' => all, 0 => 1st, 1 => 2nd..."
    if n == '*':
        return 'all'
    i = abs(n)
    n = n - 1 if n < 0 else n + 1
    return str(n) + ('th' if i > 2 else ['st', 'nd', 'rd'][i])


class Regexp(Filter):
    r"""
    Apply a regex.

    >>> from lxml.html import etree
    >>> doc = etree.fromstring('<html><body><p>Date: <span>13/08/1988</span></p></body></html>')
    >>> Regexp(CleanText('//p'), r'Date: (\d+)/(\d+)/(\d+)', '\\3-\\2-\\1')(doc) == u'1988-08-13'
    True

    >>> (Regexp(CleanText('//body'), r'(\d+)', nth=1))(doc) == u'08'
    True
    >>> (Regexp(CleanText('//body'), r'(\d+)', nth=-1))(doc) == u'1988'
    True
    >>> (Regexp(CleanText('//body'), r'(\d+)', template='[\\1]', nth='*'))(doc) == [u'[13]', u'[08]', u'[1988]']
    True
    >>> (Regexp(CleanText('//body'), r'Date:.*'))(doc) == u'Date: 13/08/1988'
    True
    >>> (Regexp(CleanText('//body'), r'^(?!Date:).*', default=None))(doc)
    >>>
    """

    def __init__(self, selector=None, pattern=None, template=None, nth=0, flags=0, default=_NO_DEFAULT):
        super(Regexp, self).__init__(selector, default=default)
        assert pattern is not None
        self.pattern = pattern
        self._regex = re.compile(pattern, flags)
        self.template = template
        self.nth = nth

    def expand(self, m):
        if self.template is None:
            try:
                return next(g for g in m.groups() if g is not None)
            except StopIteration:
                return m.string
        return self.template(m) if callable(self.template) else m.expand(self.template)

    @debug()
    def filter(self, txt):
        """
        :raises: :class:`RegexpError` if `pattern` was not found
        """

        if isinstance(txt, (tuple, list)):
            txt = u' '.join([t.strip() for t in txt.itertext()])

        m = self._regex.search(txt) if self.nth == 0 else \
            nth(self._regex.finditer(txt), self.nth)
        if not m:
            msg = 'Unable to find %s %s in %r' % (ordinal(self.nth), self.pattern, txt)
            return self.default_or_raise(RegexpError(msg))

        if isinstance(m, Iterator):
            return list(map(self.expand, m))

        return self.expand(m)


class Map(Filter):
    """Map selected value to another value using a dict.

    Example::

        TYPES = {
            'Concert': CATEGORIES.CONCERT,
            'Cinéma': CATEGORIES.CINE,
        }

        obj_type = Map(CleanText('./li'), TYPES)
    """

    def __init__(self, selector, map_dict, default=_NO_DEFAULT):
        """
        :param selector: key from `map_dict` to use
        """

        super(Map, self).__init__(selector, default=default)
        self.map_dict = map_dict

    @debug()
    def filter(self, txt):
        """
        :raises: :class:`ItemNotFound` if key does not exist in dict
        """

        try:
            return self.map_dict[txt]
        except KeyError:
            return self.default_or_raise(ItemNotFound('Unable to handle %r on %r' % (txt, self.map_dict)))


class DateTime(Filter):
    """Parse date and time."""

    def __init__(self, selector=None, default=_NO_DEFAULT, dayfirst=False, translations=None,
                 parse_func=parse_date, fuzzy=False):
        """
        :param dayfirst: if True, the day is be the first element in the string to parse
        :type dayfirst: bool
        :param parse_func: the function to use for parsing the datetime
        :param translations: string replacements from site locale to English
        :type translations: list[tuple[str, str]]
        """

        super(DateTime, self).__init__(selector, default=default)
        self.dayfirst = dayfirst
        self.translations = translations
        self.parse_func = parse_func
        self.fuzzy = fuzzy

    @debug()
    def filter(self, txt):
        if empty(txt) or txt == '':
            return self.default_or_raise(FormatError('Unable to parse %r' % txt))
        try:
            if self.translations:
                for search, repl in self.translations:
                    txt = search.sub(repl, txt)
            return self.parse_func(txt, dayfirst=self.dayfirst, fuzzy=self.fuzzy)
        except (ValueError, TypeError) as e:
            return self.default_or_raise(FormatError('Unable to parse %r: %s' % (txt, e)))


class Date(DateTime):
    """Parse date."""

    def __init__(self, selector=None, default=_NO_DEFAULT, dayfirst=False, translations=None,
                 parse_func=parse_date, fuzzy=False):
        super(Date, self).__init__(selector, default=default, dayfirst=dayfirst, translations=translations,
                                   parse_func=parse_func, fuzzy=fuzzy)

    @debug()
    def filter(self, txt):
        datetime = super(Date, self).filter(txt)
        if hasattr(datetime, 'date'):
            return datetime.date()
        else:
            return datetime


class CleanDate(CleanText):
    """
    Get a cleaned Datetime value from a string.

    >>> CleanDate('./td[1]')
    """

    def __init__(self, selector=None, date_formats=None, languages=None, locales=None, region=None, settings=None, default=_NO_DEFAULT):
        """Parse date and time from given date string.

        :param date_string:
            A string representing date and/or time in a recognizably valid format.
        :type date_string: str|unicode

        :param date_formats:
            A list of format strings using directives as given
            `here <https://docs.python.org/2/library/datetime.html#strftime-and-strptime-behavior>`_.
            The parser applies formats one by one, taking into account the detected languages/locales.
        :type date_formats: list

        :param languages:
            A list of language codes, e.g. ['en', 'es', 'zh-Hant'].
            If locales are not given, languages and region are used to construct locales for translation.
        :type languages: list

        :param locales:
            A list of locale codes, e.g. ['fr-PF', 'qu-EC', 'af-NA'].
            The parser uses locales to translate date string.
        :type locales: list

        :param region:
            A region code, e.g. 'IN', '001', 'NE'.
            If locales are not given, languages and region are used to construct locales for translation.
        :type region: str|unicode

        :param settings:
            Configure customized behavior using settings defined in :mod:`dateparser.conf.Settings`.
        :type settings: dict

        :return: Returns :class:`datetime <datetime.datetime>` representing parsed date if successful, else returns None
        :rtype: :class:`datetime <datetime.datetime>`.
        :raises: ValueError - Unknown Language
        """

        super(CleanDate, self).__init__(selector, default=default)
        self.date_formats = date_formats
        self.languages = languages
        self.locales = locales
        self.region = region
        self.settings = settings

    @debug()
    def filter(self, text):
        if type(text) in (float, int, datetime.datetime, long):
            text = str(text)

        if empty(text):
            return self.default_or_raise(FormatError('Unable to parse %r' % text))

        text = super(CleanDate, self).filter(text)

        try:
            d = dateparser.parse(date_string=text, date_formats=self.date_formats, languages=self.languages,
                                 locales=self.locales, region=self.region, settings=self.settings)
            if d and type(d) == datetime.datetime:
                return d

        except Exception as e:
            raise e

class DateGuesser(Filter):
    def __init__(self, selector, date_guesser, **kwargs):
        super(DateGuesser, self).__init__(selector)
        self.date_guesser = date_guesser
        self.kwargs = kwargs

    def __call__(self, item):
        values = self.select(self.selector, item)
        date_guesser = self.date_guesser
        # In case Env() is used to kive date_guesser.
        if isinstance(date_guesser, _Filter):
            date_guesser = self.select(date_guesser, item)

        if isinstance(values, basestring):
            values = re.split('[/-]', values)
        if len(values) == 2:
            day, month = map(int, values)
        else:
            raise FormatError('Unable to take (day, month) tuple from %r' % values)
        return date_guesser.guess_date(day, month, **self.kwargs)


class Time(Filter):
    """Parse time."""

    klass = datetime.time
    _regexp = re.compile(r'(?P<hh>\d+)[:h]?(?P<mm>\d+)([:m](?P<ss>\d+))?')
    kwargs = {'hour': 'hh', 'minute': 'mm', 'second': 'ss'}

    def __init__(self, selector=None, default=_NO_DEFAULT):
        super(Time, self).__init__(selector, default=default)

    @debug()
    def filter(self, txt):
        m = self._regexp.search(txt)
        if m:
            kwargs = {}
            for key, index in self.kwargs.items():
                kwargs[key] = int(m.groupdict()[index] or 0)
            return self.klass(**kwargs)

        return self.default_or_raise(FormatError('Unable to find time in %r' % txt))


class Duration(Time):
    """Parse a duration as timedelta."""

    klass = datetime.timedelta
    _regexp = re.compile(r'((?P<hh>\d+)[:;])?(?P<mm>\d+)[;:](?P<ss>\d+)')
    kwargs = {'hours': 'hh', 'minutes': 'mm', 'seconds': 'ss'}


class MultiFilter(Filter):
    def __init__(self, *args, **kwargs):
        default = kwargs.pop('default', _NO_DEFAULT)
        super(MultiFilter, self).__init__(args, default)

    def __call__(self, item):
        values = [self.select(selector, item) for selector in self.selector]
        return self.filter(tuple(values))

    def filter(self, values):
        raise NotImplementedError()


class CombineDate(MultiFilter):
    """Combine separate Date and Time filters into a single datetime."""

    def __init__(self, date, time):
        """
        :type date: filter
        :type time: filter
        """
        super(CombineDate, self).__init__(date, time)

    @debug()
    def filter(self, values):
        return datetime.datetime.combine(values[0], values[1])


class Format(MultiFilter):
    """Combine multiple filters with string-format.

    Example::

        obj_title = Format('%s (%s)', CleanText('//h1'), CleanText('//h2'))

    will concatenate the text from all ``<h1>`` and all ``<h2>`` (but put
    the latter between parentheses).
    """

    def __init__(self, fmt, *args):
        """
        :param fmt: string format suitable for "%"-formatting
        :type fmt: str
        :param args: other filters to insert in `fmt` string.
                     There should be as many args as there are "%" in `fmt`.
        """
        super(Format, self).__init__(*args)
        self.fmt = fmt

    @debug()
    def filter(self, values):
        return self.fmt % values


class BrowserURL(MultiFilter):
    def __init__(self, url_name, **kwargs):
        super(BrowserURL, self).__init__(*kwargs.values())
        self.url_name = url_name
        self.keys = list(kwargs.keys())

    def __call__(self, item):
        values = super(BrowserURL, self).__call__(item)
        url = getattr(item.page.browser, self.url_name)
        assert isinstance(url, URL), "%s.%s must be an URL object" % (type(item.page.browser).__name__, self.url_name)
        return url.build(**dict(zip(self.keys, values)))

    @debug()
    def filter(self, values):
        return values


class Join(Filter):
    def __init__(self, pattern, selector=None, textCleaner=CleanText, newline=False, addBefore='', addAfter=''):
        super(Join, self).__init__(selector)
        self.pattern = pattern
        self.textCleaner = textCleaner
        self.newline = newline
        self.addBefore = addBefore
        self.addAfter = addAfter

    @debug()
    def filter(self, el):
        items = [self.textCleaner.clean(e) for e in el]
        items = [item for item in items if item]

        if self.newline:
            items = ['%s\r\n' % item for item in items]

        result = self.pattern.join(items)

        if self.addBefore:
            result = '%s%s' % (self.addBefore, result)

        if self.addAfter:
            result = '%s%s' % (result, self.addAfter)

        return result


class Eval(MultiFilter):
    """
    Evaluate a function with given 'deferred' arguments.

    >>> F = Field; Eval(lambda a, b, c: a * b + c, F('foo'), F('bar'), F('baz')) # doctest: +SKIP
    >>> Eval(lambda x, y: x * y + 1).filter([3, 7])
    22

    Example::

        obj_ratio = Eval(lambda x: x / 100, Env('percentage'))
    """

    def __init__(self, func, *args):
        """
        :param func: function to apply to all filters. The function should
                     accept as many args as there are filters passed to
                     Eval.
        """
        super(Eval, self).__init__(*args)
        self.func = func

    @debug()
    def filter(self, values):
        return self.func(*values)


class QueryValue(Filter):
    """
    Extract the value of a parameter from an URL with a query string.

    >>> from lxml.html import etree
    >>> from .html import Link
    >>> f = QueryValue(Link('//a'), 'id')
    >>> f(etree.fromstring('<html><body><a href="http://example.org/view?id=1234"></a></body></html>')) == u'1234'
    True
    """
    def __init__(self, selector, key, default=_NO_DEFAULT):
        super(QueryValue, self).__init__(selector, default=default)
        self.querykey = key

    @debug()
    def filter(self, url):
        qs = parse_qs(urlparse(url).query)
        if not qs.get(self.querykey):
            return self.default_or_raise(ItemNotFound('Key %s not found' % self.querykey))
        if len(qs[self.querykey]) > 1:
            raise FilterError('More than one value for key %s' % self.querykey)
        return qs[self.querykey][0]


class Coalesce(MultiFilter):
    """
    Returns the first value that is not falsy,
    or default if all values are falsy.
    """
    @debug()
    def filter(self, values):
        for value in values:
            if value:
                return value
        return self.default_or_raise(FilterError('All falsy and no default.'))


def test_CleanText():
    # This test works poorly under a doctest, or would be hard to read
    assert CleanText().filter(u' coucou  \n\théhé') == u'coucou héhé'
    assert CleanText().filter('coucou\xa0coucou') == CleanText().filter(u'coucou\xa0coucou') == u'coucou coucou'

    # Unicode normalization
    assert CleanText().filter(u'Éçã') == u'Éçã'
    assert CleanText(normalize='NFKC').filter(u'…') == u'...'
    assert CleanText().filter(u'…') == u'…'
    # Diacritical mark (dakuten)
    assert CleanText().filter(u'\u3053\u3099') == u'\u3054'
    assert CleanText(normalize='NFD').filter(u'\u3053\u3099') == u'\u3053\u3099'
    assert CleanText(normalize='NFD').filter(u'\u3054') == u'\u3053\u3099'
    assert CleanText(normalize=False).filter(u'\u3053\u3099') == u'\u3053\u3099'


def assert_raises(exc_class, func, *args, **kwargs):
    try:
        func(*args, **kwargs)
    except exc_class:
        pass
    else:
        assert False, 'did not raise %s' % exc_class


def test_CleanDecimal_strict():
    assert CleanDecimal.US().filter('123') == Decimal('123')
    assert CleanDecimal.US().filter('foo + 123 bar') == Decimal('123')
    assert CleanDecimal.US().filter('foo +123 bar') == Decimal('123')
    assert CleanDecimal.US().filter('foo 123.45 bar') == Decimal('123.45')
    assert CleanDecimal.US().filter('foo 12,345.67 bar') == Decimal('12345.67')
    assert CleanDecimal.US().filter('foo 123,456,789 bar') == Decimal('123456789')
    assert CleanDecimal.US().filter('foo - 123,456,789.1 bar') == Decimal('-123456789.1')
    assert CleanDecimal.US().filter('foo -123,456,789.1 bar') == Decimal('-123456789.1')
    assert_raises(NumberFormatError, CleanDecimal.US().filter, 'foo 12 345.67 bar')
    assert_raises(NumberFormatError, CleanDecimal.US().filter, 'foo 123 bar 456')
    assert_raises(NumberFormatError, CleanDecimal.US().filter, 'foo 123.456.789 bar')
    assert_raises(NumberFormatError, CleanDecimal.US().filter, 'foo 12,3456 bar')
    assert_raises(NumberFormatError, CleanDecimal.US().filter, 'foo 123-456 bar')

    assert CleanDecimal.French().filter('123') == Decimal('123')
    assert CleanDecimal.French().filter('foo + 123 bar') == Decimal('123')
    assert CleanDecimal.French().filter('foo +123 bar') == Decimal('123')
    assert CleanDecimal.French().filter('foo 123,45 bar') == Decimal('123.45')
    assert CleanDecimal.French().filter('foo 12 345,67 bar') == Decimal('12345.67')
    assert CleanDecimal.French().filter('foo - 123 456 789 bar') == Decimal('-123456789')
    assert CleanDecimal.French().filter('foo -123 456 789 bar') == Decimal('-123456789')
    assert_raises(NumberFormatError, CleanDecimal.French().filter, 'foo 123.45 bar')
    assert_raises(NumberFormatError, CleanDecimal.French().filter, 'foo 123 bar 456')
    assert_raises(NumberFormatError, CleanDecimal.French().filter, 'foo 123,456,789')
    assert_raises(NumberFormatError, CleanDecimal.French().filter, 'foo 12 3456 bar')
    assert_raises(NumberFormatError, CleanDecimal.French().filter, 'foo 123-456 bar')

    assert CleanDecimal.SI().filter('123') == Decimal('123')
    assert CleanDecimal.SI().filter('foo + 123 bar') == Decimal('123')
    assert CleanDecimal.SI().filter('foo +123 bar') == Decimal('123')
    assert CleanDecimal.SI().filter('foo 123.45 bar') == Decimal('123.45')
    assert CleanDecimal.SI().filter('foo 12 345.67 bar') == Decimal('12345.67')
    assert CleanDecimal.SI().filter('foo 123 456 789 bar') == Decimal('123456789')
    assert CleanDecimal.SI().filter('foo - 123 456 789 bar') == Decimal('-123456789')
    assert CleanDecimal.SI().filter('foo -123 456 789 bar') == Decimal('-123456789')
    assert_raises(NumberFormatError, CleanDecimal.SI().filter, 'foo 123,45 bar')
    assert_raises(NumberFormatError, CleanDecimal.SI().filter, 'foo 123 bar 456')
    assert_raises(NumberFormatError, CleanDecimal.SI().filter, 'foo 123,456,789')
    assert_raises(NumberFormatError, CleanDecimal.SI().filter, 'foo 12 3456 bar')
    assert_raises(NumberFormatError, CleanDecimal.SI().filter, 'foo 123-456 bar')
