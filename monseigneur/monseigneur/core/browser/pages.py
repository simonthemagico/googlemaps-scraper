# -*- coding: utf-8 -*-

from __future__ import absolute_import

from collections import OrderedDict
from functools import wraps
import warnings
from io import BytesIO, StringIO
import codecs
from cgi import parse_header
from functools import reduce
import re
import sys

import requests

from monseigneur.monseigneur.core.exceptions import ParseError, ModuleInstallError
from monseigneur.monseigneur.core.tools.compat import basestring, unicode, urljoin
from monseigneur.monseigneur.core.tools.log import getLogger
from monseigneur.monseigneur.core.tools.pdf import decompress_pdf
from .exceptions import LoggedOut


def pagination(func):
    r"""
    This helper decorator can be used to handle pagination pages easily.

    When the called function raises an exception :class:`NextPage`, it goes on
    the wanted page and recall the function.

    :class:`NextPage` constructor can take an url or a Request object.

    >>> class Page(HTMLPage):
    ...     @pagination
    ...     def iter_values(self):
    ...         for el in self.doc.xpath('//li'):
    ...             yield el.text
    ...         for next in self.doc.xpath('//a'):
    ...             raise NextPage(next.attrib['href'])
    ...
    >>> from .browsers import PagesBrowser
    >>> from .url import URL
    >>> class Browser(PagesBrowser):
    ...     BASEURL = 'https://people.symlink.me'
    ...     list = URL('/~rom1/projects/core/list-(?P<pagenum>\d+).html', Page)
    ...
    >>> b = Browser()
    >>> b.list.go(pagenum=1) # doctest: +ELLIPSIS
    <core.browser.pages.Page object at 0x...>
    >>> list(b.page.iter_values())
    ['One', 'Two', 'Three', 'Four']
    """

    @wraps(func)
    def inner(page, *args, **kwargs):
        while True:
            try:
                for r in func(page, *args, **kwargs):
                    yield r
            except NextPage as e:
                if isinstance(e.request, Page):
                    page = e.request
                else:
                    result = page.browser.location(e.request)
                    page = result.page
            else:
                return

    return inner


class NextPage(Exception):
    """
    Exception used for example in a Page to tell PagesBrowser.pagination to
    go on the next page.

    See :meth:`PagesBrowser.pagination` or decorator :func:`pagination`.
    """

    def __init__(self, request):
        super(NextPage, self).__init__()
        self.request = request


class Page(object):
    """
    Represents a page.

    Encoding can be forced by setting the :attr:`ENCODING` class-wide
    attribute, or by passing an `encoding` keyword argument, which overrides
    :attr:`ENCODING`. Finally, it can be manually changed by assigning a new
    value to :attr:`encoding` instance attribute. A unicode version of the
    response content is accessible in :attr:`text`, decoded with specified
    :attr:`encoding`.

    :param browser: browser used to go on the page
    :type browser: :class:`core.browser.browsers.Browser`
    :param response: response object
    :type response: :class:`Response`
    :param params: optional dictionary containing parameters given to the page (see :class:`core.browser.url.URL`)
    :type params: :class:`dict`
    :param encoding: optional parameter to force the encoding of the page, overrides :attr:`ENCODING`
    :type encoding: :class:`basestring`

    """

    ENCODING = None
    """
    Force a page encoding.
    It is recommended to use None for autodetection.
    """

    logged = False
    """
    If True, the page is in a restricted area of the website. Useful with
    :class:`LoginBrowser` and the :func:`need_login` decorator.
    """

    def __init__(self, browser, response, params=None, encoding=None):
        self.browser = browser
        self.logger = getLogger(self.__class__.__name__.lower(), browser.logger)
        self.response = response
        self.url = self.response.url
        self.params = params

        # Setup encoding and build document
        self.forced_encoding = encoding or self.ENCODING
        if self.forced_encoding:
            self.response.encoding = self.forced_encoding
        self.doc = self.build_doc(self.data)

        # Last chance to change encoding, according to :meth:`detect_encoding`,
        # which can be used to detect a document-level encoding declaration
        if not self.forced_encoding:
            encoding = self.detect_encoding()
            if encoding and encoding != self.encoding:
                self.response.encoding = encoding
                self.doc = self.build_doc(self.data)

    # Encoding issues are delegated to Response instance, implemented by
    # requests module.

    @property
    def encoding(self):
        return self.response.encoding

    @encoding.setter
    def encoding(self, value):
        self.forced_encoding = True
        self.response.encoding = value

    @property
    def content(self):
        """
        Raw content from response.
        """
        return self.response.content

    @property
    def text(self):
        """
        Content of the response, in unicode, decoded with :attr:`encoding`.
        """
        return self.response.text

    @property
    def data(self):
        """
        Data passed to :meth:`build_doc`.
        """
        return self.content

    def on_load(self):
        """
        Event called when browser loads this page.
        """

    def on_leave(self):
        """
        Event called when browser leaves this page.
        """

    def build_doc(self, content):
        """
        Abstract method to be implemented by subclasses to build structured
        data (HTML, Json, CSV...) from :attr:`data` property. It also can be
        overriden in modules pages to preprocess or postprocess data. It must
        return an object -- that will be assigned to :attr:`doc`.
        """
        raise NotImplementedError()

    def detect_encoding(self):
        """
        Override this method to implement detection of document-level encoding
        declaration, if any (eg. html5's <meta charset="some-charset">).
        """
        return None

    def absurl(self, url):
        """
        Get an absolute URL from an a partial URL, relative to the Page URL
        """
        return urljoin(self.url, url)


class FormNotFound(Exception):
    """
    Raised when :meth:`HTMLPage.get_form` can't find a form.
    """


class FormSubmitWarning(UserWarning):
    """
    A form has more than one submit element selected, and will likely
    generate an invalid request.
    """


class Form(OrderedDict):
    """
    Represents a form of an HTML page.

    It is used as a dict with pre-filled values from HTML. You can set new
    values as strings by setting an item value.

    It is recommended to not use this class by yourself, but call
    :meth:`HTMLPage.get_form`.

    :param page: the page where the form is located
    :type page: :class:`Page`
    :param el: the form element on the page
    :param submit_el: allows you to only consider one submit button (which is
                      what browsers do). If set to None, it takes all of them,
                      and if set to False, it takes none.
    """

    def __init__(self, page, el, submit_el=None):
        super(Form, self).__init__()
        self.page = page
        self.el = el
        self.submit_el = submit_el
        self.method = el.attrib.get('method', 'GET')
        self.url = el.attrib.get('action', page.url)
        self.name = el.attrib.get('name', '')
        self.req = None
        submits = 0

        # Find all elements of the form that will be useful to create the request
        # Added by Sasha B. .//button
        for inp in el.xpath('.//input | .//select | .//textarea | .//button'):
            # Step 1: Ignore some elements
            try:
                name = inp.attrib['name']
            except KeyError:
                continue

            # Ignore checkboxes and radios that are not selected
            # as they are just not present in the request instead of being empty
            # values.
            try:
                if inp.attrib['type'] in ('checkbox', 'radio') and 'checked' not in inp.attrib:
                    continue
            except KeyError:
                pass

            # Either filter the submit buttons, or count how many we have found
            try:
                if inp.attrib['type'] == 'submit':
                    # If we chose a submit button, ignore all others
                    if self.submit_el is not None and inp is not self.submit_el:
                        continue
                    else:
                        # Register that we have found a submit button, and that it will
                        # be used
                        submits += 1
            except KeyError:
                pass

            # Step 2: Extract the key-value pair from the remaining elements
            if inp.tag == 'select':
                options = inp.xpath('.//option[@selected]')
                if len(options) == 0:
                    options = inp.xpath('.//option')
                if len(options) == 0:
                    value = u''
                else:
                    value = options[0].attrib.get('value', options[0].text or u'')
            else:
                value = inp.attrib.get('value', inp.text or u'')
            # TODO check if value already exists, emit warning
            self[name] = value

        # Sanity checks
        if submits > 1:
            warnings.warn('Form has more than one submit input, you should chose the correct one', FormSubmitWarning, stacklevel=3)
        if self.submit_el is not None and self.submit_el is not False and submits == 0:
            warnings.warn('Form had a submit element provided, but it was not found', FormSubmitWarning, stacklevel=3)

    @property
    def request(self):
        """
        Get the Request object from the form.
        """
        if self.req is None:
            if self.method.lower() == 'get':
                self.req = requests.Request(self.method, self.url, params=self)
            else:
                self.req = requests.Request(self.method, self.url, data=self)
            self.req.headers.setdefault('Referer', self.page.url)
        return self.req

    def submit(self, **kwargs):
        """
        Submit the form and tell browser to be located to the new page.

        :param data_encoding: force encoding used to submit form data (defaults to the current page encoding)
        :type data_encoding: :class:`basestring`
        """
        kwargs.setdefault('data_encoding', self.page.encoding)
        return self.page.browser.location(self.request, **kwargs)


class CsvPage(Page):
    """
    Page which parses CSV files.
    """

    DIALECT = 'excel'
    """
    Dialect given to the :mod:`csv` module.
    """

    FMTPARAMS = {}
    """
    Parameters given to the :mod:`csv` module.
    """

    ENCODING = 'utf-8'
    """
    Encoding of the file.
    """

    NEWLINES_HACK = True
    """
    Convert all strange newlines to unix ones.
    """

    HEADER = None
    """
    If not None, will consider the line represented by this index as a header.
    This means the rows will be also available as dictionaries.
    """

    def build_doc(self, content):
        # We may need to temporarily convert content to utf-8 because csv
        # does not support Unicode.
        encoding = self.encoding
        if encoding == 'utf-16le':
            # If there is a BOM, decode('utf-16') will get rid of it
            content = content.decode('utf-16').encode('utf-8')
            encoding = 'utf-8'
        if self.NEWLINES_HACK:
            content = content.replace(b'\r\n', b'\n').replace(b'\r', b'\n')
        if sys.version_info.major > 2:
            return self.parse(StringIO(content.decode(encoding)))
        return self.parse(BytesIO(content), encoding)

    def parse(self, data, encoding=None):
        """
        Method called by the constructor of :class:`CsvPage` to parse the document.

        :param data: file stream
        :type data: :class:`BytesIO`
        :param encoding: if given, use it to decode cell strings
        :type encoding: :class:`str`
        """
        import csv
        reader = csv.reader(data, dialect=self.DIALECT, **self.FMTPARAMS)
        header = None
        drows = []
        rows = []
        for i, row in enumerate(reader):
            if self.HEADER and i+1 < self.HEADER:
                continue
            if sys.version_info.major > 2:
                row = [c.strip() for c in row]
            else:
                row = [c.strip() for c in self.decode_row(row, encoding)]
            if header is None and self.HEADER:
                header = row
            else:
                rows.append(row)
                if header:
                    drow = {}
                    for i, cell in enumerate(row):
                        drow[header[i]] = cell
                    drows.append(drow)
        return drows if header is not None else rows

    def decode_row(self, row, encoding):
        """
        Method called by :meth:`CsvPage.parse` to decode a row using the given encoding.
        """
        if encoding:
            return [unicode(cell, encoding) for cell in row]
        else:
            return row


class JsonPage(Page):
    """
    Json Page.

    Notes on JSON format:
    JSON must be UTF-8 encoded when used for open systems interchange (https://tools.ietf.org/html/rfc8259).
    So it can be safely assumed all JSON to be UTF-8. No Byte Order Mark is allowed.
    A little subtlety is that JSON Unicode surrogate escape sequence (used for characters > U+FFFF) are UTF-16 style, but that should be handled by libraries (some don't… Even if JSON is one of the simplest formats around…).
    """

    ENCODING = 'utf-8'

    @property
    def data(self):
        return self.response.text

    def get(self, path):
        try:
            return next(self.path(path))
        except StopIteration:
            return None

    def path(self, path, context=None):
        from monseigneur.monseigneur.core.tools.json import mini_jsonpath
        return mini_jsonpath(context or self.doc, path)

    def build_doc(self, text):
        from monseigneur.monseigneur.core.tools.json import json
        return json.loads(text)


class XLSPage(Page):
    """
    XLS Page.
    """

    HEADER = None
    """
    If not None, will consider the line represented by this index as a header.
    """

    SHEET_INDEX = 0
    """
    Specify the index of the worksheet to use.
    """

    def build_doc(self, content):
        return self.parse(content)

    def parse(self, data):
        """
        Method called by the constructor of :class:`XLSPage` to parse the document.
        """
        import xlrd
        wb = xlrd.open_workbook(file_contents=data)
        sh = wb.sheet_by_index(self.SHEET_INDEX)

        header = None
        drows = []
        rows = []
        for i in range(sh.nrows):
            if self.HEADER and i + 1 < self.HEADER:
                continue
            row = sh.row_values(i)
            if header is None and self.HEADER:
                header = [s.replace('/', '') for s in row]
            else:
                rows.append(row)
                if header:
                    drow = {}
                    for i, cell in enumerate(sh.row_values(i)):
                        drow[header[i]] = cell
                    drows.append(drow)
        return drows if header is not None else rows


class XMLPage(Page):
    """
    XML Page.
    """

    def detect_encoding(self):
        import re
        m = re.search(br'<\?xml version="1.0" encoding="(.*)"\?>', self.data)
        if m:
            return m.group(1)

    def build_doc(self, content):
        import lxml.etree as etree
        parser = etree.XMLParser(encoding=self.encoding)
        return etree.parse(BytesIO(content), parser)


class RawPage(Page):
    """
    Raw page where the "doc" attribute is the content string.
    """

    def build_doc(self, content):
        return content


class HTMLPage(Page):
    """
    HTML page.

    :param browser: browser used to go on the page
    :type browser: :class:`core.browser.browsers.Browser`
    :param response: response object
    :type response: :class:`Response`
    :param params: optional dictionary containing parameters given to the page (see :class:`core.browser.url.URL`)
    :type params: :class:`dict`
    :param encoding: optional parameter to force the encoding of the page
    :type encoding: :class:`basestring`

    """

    FORM_CLASS = Form
    """
    The class to instanciate when using :meth:`HTMLPage.get_form`. Default to :class:`Form`.
    """

    REFRESH_MAX = None
    ALLOW_EMPTY_PAGE = False
    """
    When handling a "Refresh" meta header, the page considers it only if the sleep
    time in lesser than this value.

    Default value is None, means refreshes aren't handled.
    """

    def __init__(self, *args, **kwargs):
        import lxml.html as html
        ns = html.etree.FunctionNamespace(None)
        self.define_xpath_functions(ns)

        super(HTMLPage, self).__init__(*args, **kwargs)

    def on_load(self):
        # Default on_load handle "Refresh" meta tag.
        self.handle_refresh()

    def handle_refresh(self):
        if self.REFRESH_MAX is None:
            return

        for refresh in self.doc.xpath('//head/meta[lower-case(@http-equiv)="refresh"]'):
            m = self.browser.REFRESH_RE.match(refresh.get('content', ''))
            if not m:
                continue
            url = urljoin(self.url, m.groupdict().get('url', None))
            sleep = float(m.groupdict()['sleep'])

            if sleep <= self.REFRESH_MAX:
                self.logger.info('Redirecting to %s', url)
                self.browser.location(url)
                break
            else:
                self.logger.debug('Do not refresh to %s because %s > REFRESH_MAX(%s)' % (url, sleep, self.REFRESH_MAX))

    def define_xpath_functions(self, ns):
        """
        Define XPath functions on the given lxml function namespace.

        This method is called in constructor of :class:`HTMLPage` and can be
        overloaded by children classes to add extra functions.
        """
        ns['lower-case'] = lambda context, args: ' '.join([s.lower() for s in args])
        ns['replace'] = lambda context, args, old, new: ' '.join([s.replace(old, new) for s in args])

        def has_class(context, *classes):
            """
            This lxml extension allows to select by CSS class more easily

            >>> ns = html.etree.FunctionNamespace(None)
            >>> ns['has-class'] = has_class
            >>> root = html.etree.fromstring('''
            ... <a>
            ...     <b class="one first text">I</b>
            ...     <b class="two text">LOVE</b>
            ...     <b class="three text">CSS</b>
            ... </a>
            ... ''')

            >>> len(root.xpath('//b[has-class("text")]'))
            3
            >>> len(root.xpath('//b[has-class("one")]'))
            1
            >>> len(root.xpath('//b[has-class("text", "first")]'))
            1
            >>> len(root.xpath('//b[not(has-class("first"))]'))
            2
            >>> len(root.xpath('//b[has-class("not-exists")]'))
            0
            """
            expressions = ' and '.join(["contains(concat(' ', normalize-space(@class), ' '), ' {0} ')".format(c) for c in classes])
            xpath = 'self::*[@class and {0}]'.format(expressions)
            return bool(context.context_node.xpath(xpath))

        def starts_with(context, text, prefix):
            if not isinstance(text, list):
                text = [text]
            return any(t.startswith(prefix) for t in text)

        def ends_with(context, text, suffix):
            if not isinstance(text, list):
                text = [text]
            return any(t.endswith(suffix) for t in text)

        def matches(context, text, pattern):
            reobj = re.compile(pattern)
            if not isinstance(text, list):
                text = [text]
            return any(reobj.search(t) for t in text)

        def first_non_empty(context, *nodes_list):
            for nodes in nodes_list:
                if nodes:
                    return nodes
            return []

        ns['has-class'] = has_class
        ns['starts-with'] = starts_with
        ns['ends-with'] = ends_with
        ns['matches'] = matches
        ns['first-non-empty'] = first_non_empty

    def build_doc(self, content):
        """
        Method to build the lxml document from response and given encoding.
        """
        encoding = self.encoding
        if encoding == 'latin-1':
            encoding = 'latin1'
        if encoding:
            encoding = encoding.replace('ISO8859_', 'ISO8859-')
        import lxml.html as html
        parser = html.HTMLParser(encoding=encoding)
        return html.parse(BytesIO(content), parser)

    def detect_encoding(self):
        """
        Look for encoding in the document "http-equiv" and "charset" meta nodes.
        """
        encoding = self.encoding
        try:
            content_list = self.doc.xpath('//head/meta[lower-case(@http-equiv)="content-type"]/@content')
        except AssertionError as e:
            if self.ALLOW_EMPTY_PAGE:
                if str(e) == "ElementTree not initialized, missing root":
                    return self.encoding
                raise(e)
            else:
                raise(e)
        else:
            for content in content_list:
                # meta http-equiv=content-type content=...
                _, params = parse_header(content)
                if 'charset' in params:
                    encoding = params['charset'].strip("'\"")

            for charset in self.doc.xpath('//head/meta[@charset]/@charset'):
                # meta charset=...
                encoding = charset.lower()

            if encoding == 'iso-8859-1' or not encoding:
                encoding = 'windows-1252'
            try:
                codecs.lookup(encoding)
            except LookupError:
                encoding = 'windows-1252'

            return encoding

    def get_form(self, xpath='//form', name=None, id=None, nr=None,
                 submit=None):
        """
        Get a :class:`Form` object from a selector.
        The form will be analyzed and its parameters extracted.
        In the case there is more than one "submit" input, only one of
        them should be chosen to generate the request.

        :param xpath: xpath string to select forms
        :type xpath: :class:`str`
        :param name: if supplied, select a form with the given name
        :type name: :class:`str`
        :param nr: if supplied, take the n+1 th selected form
        :type nr: :class:`int`
        :param submit: if supplied, xpath string to select the submit \
            element from the form
        :type submit: :class:`str`
        :rtype: :class:`Form`
        :raises: :class:`FormNotFound` if no form is found
        """
        i = 0
        for el in self.doc.xpath(xpath):
            if name is not None and el.attrib.get('name', '') != name:
                continue
            if id is not None and el.attrib.get('id', '') != id:
                continue
            if nr is not None and i != nr:
                i += 1
                continue

            if isinstance(submit, basestring):
                submit_el = el.xpath(submit)[0]
            else:
                submit_el = submit

            return self.FORM_CLASS(self, el, submit_el)

        raise FormNotFound()


class PartialHTMLPage(HTMLPage):
    """
    HTML page for broken pages with multiple roots.

    This class should typically be used for requests which return only a part of
    a full document, to insert in another document. Such a sub-document can have
    multiple root tags, so this class is required in this case.
    """

    def build_doc(self, content):
        import lxml.etree

        if content.strip():
            # lxml raises a different error if content is whitespace-only
            try:
                return super(PartialHTMLPage, self).build_doc(content)
            except lxml.etree.XMLSyntaxError:
                pass

        content = b'<html>%s</html>' % content
        return super(PartialHTMLPage, self).build_doc(content)


class GWTPage(Page):
    """
    GWT page where the "doc" attribute is a list

    More info about GWT protcol here : https://goo.gl/GP5dv9
    """

    def build_doc(self, content):
        """
        Reponse starts with "//" followed by "OK" or "EX".
        2 last elements in list are protocol and flag.
        We need to read the list in reversed order.
        """

        assert content[2:4] == "OK"
        doc, array = [], []
        from ast import literal_eval
        for el in reversed(literal_eval(content[4:])[:-2]):
            # If we find an array, args after are indices or date
            if not array and isinstance(el, list):
                array = el
            elif array and isinstance(el, int) and len(array) >= el >= 1:
                doc.append(array[el - 1])
            elif array and isinstance(el, basestring):
                doc.append(self.get_date(el))
        return doc

    def get_date(self, data):
        """
        Get date from string
        """

        base = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_$"
        timestamp = sum(base.index(data[el]) * (len(base) ** (len(data) - el - 1)) for el in range(len(data)))
        from datetime import datetime
        return datetime.fromtimestamp(int(str(timestamp)[:10])).strftime('%d/%m/%Y')

    def get_elements(self, type="String"):
        """
        Get elements of specified type
        """

        strings = []
        for i, el in enumerate(self.doc):
            if i > 0 and ".%s" % type in self.doc[i - 1]:
                strings.append(el)
        return [string for string in strings if "java." not in string]


class PDFPage(Page):
    """
    Parse a PDF and write raw data in the "doc" attribute as a string.
    """
    def build_doc(self, content):
        try:
            doc = decompress_pdf(content)
        except OSError as e:
            raise ParseError(u'Make sure mupdf-tools is installed (%s)' % e)

        return doc


class LoggedPage(object):
    """
    A page that only logged users can reach. If we did not get a redirection
    for this page, we are sure that the login is still active.

    Do not use this class for page with mixed content (logged/anonymous) or for
    pages with a login form.
    """
    logged = True


class MixedContentPage(object):
    """
    A page that logged users and anonymous can reach.
    """
    def logged(self):
        """
        Function to define that identifies if logged/unlogged status
        :return: boolean
        """
        raise NotImplementedError()


class ChecksumPage(object):
    """
    Compute a checksum of raw content before parsing it.
    """
    import hashlib

    hashfunc = hashlib.md5
    checksum = None

    def build_doc(self, content):
        self.checksum = self.hashfunc(content).hexdigest()
        return super(ChecksumPage, self).build_doc(content)


class AbstractPageError(Exception):
    pass


class AbstractPage(Page):
    PARENT = None
    PARENT_URL = None
    BROWSER_ATTR = None

    def __new__(cls, browser, *args, **kwargs):
        backend = getattr(browser, 'core', None)
        if not backend:
            raise AbstractPageError("core is not defined in %s" % browser)

        if cls.PARENT is None:
            raise AbstractPageError("PARENT is not defined for page %s" % cls.__name__)

        if cls.PARENT_URL is None:
            raise AbstractPageError("PARENT_URL is not defined for page %s" % cls.__name__)

        try:
            parent_module = backend.load_or_install_module(cls.PARENT)
        except ModuleInstallError as err:
            raise ModuleInstallError('This module depends on %s module but %s\'s installation failed with: %s' % (cls.PARENT, cls.PARENT, err))

        if cls.BROWSER_ATTR is None:
            parent_browser = parent_module.klass.BROWSER
        else:
            parent_browser = reduce(getattr, cls.BROWSER_ATTR.split('.'), parent_module)

        parent = getattr(parent_browser, cls.PARENT_URL, None)
        if parent is None:
            raise AbstractPageError("cls.PARENT_URL is not defined in %s" % browser)

        cls.__bases__ = (parent.klass,)
        return object.__new__(cls)


class LoginPage(object):
    def on_load(self):
        if not self.browser.logging_in:
            raise LoggedOut()

        super(LoginPage, self).on_load()
