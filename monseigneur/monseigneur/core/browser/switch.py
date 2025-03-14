# -*- coding: utf-8 -*-

from functools import wraps


class SiteSwitch(Exception):
    """Exception to raise to switch to another Browser."""

    def __init__(self, name):
        """
        :param name: key of the `SwitchingBrowser.BROWSERS` dict to indicate
                     the new browser class to use
        :type name: str
        """
        super(SiteSwitch, self).__init__('Switching to site %s' % name)
        self.name = name


class SwitchingBrowser(object):
    """Proxy browser to use multiple (exclusive) browsers.

    When some sites have mutually exclusive sub-sites, it may be better to
    split a browser in multiple browsers. If it's not possible to know in
    advance what browser should be used, the SwitchingBrowser can help.

    Multiple browsers should be configured in the `BROWSERS` attribute as
    a dict. When first used, SwitchingBrowser will instanciate the browser
    class with the `'main'` key and proxy all method calls to it.
    If that browser raises :class:`SiteSwitch` exception, another browser
    (associated to the exception key parameter) will be instanciated and will
    be used to retry the call which failed.
    """

    BROWSERS = None

    """dict association keys to browser classes.

    It should contain a `'main'` key for the first browser class to use.
    """

    KEEP_SESSION = False

    """Whether to pass the :class:`requests.session.Session` between browsers.
    """

    def __init__(self, *args, **kwargs):
        super(SwitchingBrowser, self).__init__()
        self._browser_args = args
        self._browser_kwargs = kwargs
        self._browser = None

        self.set_browser('main')

    def set_browser(self, name):
        klass = self.BROWSERS[name]
        obj = klass(*self._browser_args, **self._browser_kwargs)
        if self._browser is not None:
            if self.KEEP_SESSION:
                obj.session = self._browser.session
            else:
                self._browser.session.close()

        self._browser = obj
        self._browser.logger.info('using %r browser', name)

    def __getattr__(self, attr):
        val = getattr(self._browser, attr)
        if not callable(val):
            return val

        @wraps(val)
        def wrapper(*args, **kwargs):
            try:
                return val(*args, **kwargs)
            except SiteSwitch as e:
                self.set_browser(e.name)
                val2 = getattr(self._browser, attr)
                return val2(*args, **kwargs)

        return wrapper
