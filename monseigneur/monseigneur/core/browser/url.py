# -*- coding: utf-8 -*-

from functools import wraps
import re
import requests
import urllib

from monseigneur.monseigneur.core.tools.compat import basestring, unquote
from monseigneur.monseigneur.core.tools.regex_helper import normalize
from monseigneur.monseigneur.core.tools.misc import to_unicode


class UrlNotResolvable(Exception):
    """
    Raised when trying to locate on an URL instance which url pattern is not resolvable as a real url.
    """


class URL(object):
    """
    A description of an URL on the PagesBrowser website.

    It takes one or several regexps to match urls, and an optional Page
    class which is instancied by PagesBrowser.open if the page matches a regex.
    """
    _creation_counter = 0

    def __init__(self, *args):
        self.urls = []
        self.klass = None
        self.browser = None
        for arg in args:
            if isinstance(arg, basestring):
                self.urls.append(arg)
            if isinstance(arg, type):
                self.klass = arg

        self._creation_counter = URL._creation_counter
        URL._creation_counter += 1

    def is_here(self, **kwargs):
        """
        Returns True if the current page of browser matches this URL.
        If arguments are provided, and only then, they are checked against the arguments
        that were used to build the current page URL.
        """
        assert self.klass is not None, "You can use this method only if there is a Page class handler."

        if len(kwargs):
            params = self.match(self.build(**kwargs)).groupdict()
        else:
            params = None

        # XXX use unquote on current params values because if there are spaces
        # or special characters in them, it is encoded only in but not in kwargs.
        return self.browser.page and isinstance(self.browser.page, self.klass) \
            and (params is None or params == dict([(k,unquote(v)) for k,v in self.browser.page.params.items()]))

    def stay_or_go(self, params=None, data=None, json=None, method=None, headers=None, auth=None, allow_redirects=True, pause=0, **kwargs):
        """
        Request to go on this url only if we aren't already here.

        Arguments are optional parameters for url.

        >>> url = URL('http://exawple.org/(?P<pagename>).html')
        >>> url.stay_or_go(pagename='index')
        """

        if 'params' in kwargs:
            params = kwargs.pop('params')
        if 'data' in kwargs:
            data = kwargs.pop('data')
        if 'json' in kwargs:
            json = kwargs.pop('json')
        if 'method' in kwargs:
            json = kwargs.pop('method')
        if 'headers' in kwargs:
            headers = kwargs.pop('headers')
        if 'pause' in kwargs:
            pause = kwargs.pop('pause')
        if 'allow_redirects' in kwargs:
            allow_redirects = kwargs.pop('allow_redirects')

        if self.is_here(**kwargs):
            return self.browser.page

        return self.go(params=params, data=data, json=json, method=method, headers=headers, auth=auth,
                       allow_redirects=allow_redirects, pause=pause, **kwargs)

    def go(self, params=None, data=None, json=None, method=None, headers=None, auth=None, allow_redirects=True, pause=0, verify=True, referrer=None, **kwargs):
        """
        Request to go on this url.

        Arguments are optional parameters for url.

        >>> url = URL('http://exawple.org/(?P<pagename>).html')
        >>> url.stay_or_go(pagename='index')
        """
        r = self.browser.location(self.build(**kwargs), referrer=referrer, params=params, data=data, auth=auth, json=json, method=method, headers=headers or {}, allow_redirects=allow_redirects, pause=pause, verify=verify)
        return r.page or r

    def open(self, params=None, data=None, method=None, headers=None, is_async=False, callback=lambda response: response, **kwargs):
        """
        Request to open on this url.

        Arguments are optional parameters for url.

        :param data: POST data
        :type url: str or dict or None

        >>> url = URL('http://exawple.org/(?P<pagename>).html')
        >>> url.open(pagename='index')
        """
        r = self.browser.open(self.build(**kwargs), params=params, data=data, method=method, headers=headers or {}, is_async=is_async, callback=callback)

        if hasattr(r, 'page') and r.page:
            return r.page
        return r

    def build(self, **kwargs):
        """
        Build an url with the given arguments from URL's regexps.

        :param param: Query string parameters

        :rtype: :class:`str`
        :raises: :class:`UrlNotResolvable` if unable to resolve a correct url with the given arguments.
        """
        browser = kwargs.pop('browser', self.browser)
        params = kwargs.pop('params', None)
        patterns = []
        for url in self.urls:
            patterns += normalize(url)

        for pattern, _ in patterns:
            url = pattern
            # only use full-name substitutions, to allow % in URLs
            args = kwargs.copy()
            for key in list(args.keys()):  # need to use keys() because of pop()
                search = '%%(%s)s' % key
                if search in pattern:
                    url = url.replace(search, to_unicode(args.pop(key)))
            # if there are named substitutions left, ignore pattern
            if re.search(r'%\([A-z_]+\)s', url):
                continue
            # if not all args were used
            if len(args):
                continue

            url = browser.absurl(url, base=True)
            if params:
                p = requests.models.PreparedRequest()
                p.prepare_url(url, params)
                url = p.url
            return url

        raise UrlNotResolvable('Unable to resolve URL with %r. Available are %s' % (kwargs, ', '.join([pattern for pattern, _ in patterns])))

    def match(self, url, base=None):
        """
        Check if the given url match this object.
        """
        if base is None:
            assert self.browser is not None
            base = self.browser.BASEURL

        for regex in self.urls:
            if not re.match(r'^[\w\?]+://.*', regex):
                if base:
                    regex = base.rstrip('/') + '/?' + regex.lstrip('/')
                if not base:
                    regex = regex.lstrip('/')

                if not self.browser.DOWNGRADE:
                    regex = re.sub(r'https?', 'https?', regex)

                # Added by Sasha B.
                # if [] in url, automatically replaced by HTTP %5B%5D
                if any(w in regex for w in [r'\[', r'\]']):
                    url = re.sub(r'%5B', '[', url)
                    url = re.sub(r'%5D', ']', url)
                # if {} in url, automatically replaced by HTTP %5B%5D
                if any(w in regex for w in [r'\{', r'\}']):
                    url = re.sub(r'%7B', '{', url)
                    url = re.sub(r'%7D', '}', url)

            m = re.match(regex, url)
            if m:
                return m

    def handle(self, response):
        """
        Handle a HTTP response to get an instance of the klass if it matches.
        """
        if self.klass is None:
            return
        if response.request.method == 'HEAD':
            return

        m = self.match(str(response.url))

        if m:
            page = self.klass(self.browser, response, m.groupdict())
            if hasattr(page, 'is_here'):
                if callable(page.is_here):
                    if page.is_here():
                        return page
                else:
                    assert isinstance(page.is_here, basestring)
                    if page.doc.xpath(page.is_here):
                        return page
            else:
                return page

    def id2url(self, func):
        r"""
        Helper decorator to get an URL if the given first parameter is an ID.
        """

        @wraps(func)
        def inner(browser, id_or_url, *args, **kwargs):
            if re.match('^https?://.*', id_or_url):
                if not self.match(id_or_url, browser.BASEURL):
                    return
            else:
                id_or_url = self.build(id=id_or_url, browser=browser)

            return func(browser, id_or_url, *args, **kwargs)
        return inner


def normalize_url(url):
    """Normalize URL by lower-casing the domain and other fixes.

    Lower-cases the domain, removes the default port and a trailing dot.

    >>> normalize_url('http://EXAMPLE:80')
    'http://example'
    """
    def norm_domain(m):
        port = m.group(3) or ''
        if (port == ':80' and m.group(1) == 'http://') or (port == ':443' and m.group(1) == 'https://'):
            port = ''
        return '%s%s%s' % (m.group(1), m.group(2).lower(), port)

    return re.sub(r'(https?://)([^/]+?)\.?(:\d+)?(?=/|$)', norm_domain, url)
