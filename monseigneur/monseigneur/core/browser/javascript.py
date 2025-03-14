# -*- coding: utf-8 -*-

from __future__ import unicode_literals, absolute_import

import logging
import codecs
from contextlib import contextmanager
from copy import deepcopy
from glob import glob
import os
import base64
from typing import Literal
import zlib
import pickle
import hashlib
import tempfile
import sys
from xvfbwrapper import Xvfb

from monseigneur.core.tools.log import createColoredFormatter
from monseigneur.core.tools.decorators import retry

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    raise ImportError('Please install playwright')

from playwright.sync_api._generated import BrowserType, Response
from playwright._impl._api_types import TimeoutError, Error

from monseigneur.core.tools.compat import urljoin

from .url import URL

__all__ = (
    'PlaywrightBrowser'
)


class PageRequest(object):

    method: str = None
    headers: dict = {}
    data: str = None

class PageResponse(object):

    page = None
    encoding: str = 'utf-8'
    headers: dict = {}

    status_code: int = None
    url: str = None

    content: bytes = None
    text: str = None
    request: PageRequest = PageRequest()

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class PlaywrightBrowser(object):
    """Browser similar to PagesBrowser, but using Playwright.

    URLs instances can be used. The need_login decorator can be used too.

    Differences:
    - since JS code can be run anytime, the current `url` and `page` can change anytime
    - it's not possible to use `open()`, only `location()` can be used
    - many options are not implemented yet (like proxies) or cannot be implemented at all
    """

    __states__ = []

    """Browser states list for saving pickle"""

    DRIVER = 'webkit'

    """Playwright driver class"""

    HEADLESS = True

    """Run without any display"""

    DEFAULT_WAIT = 30000

    """Default wait time for `wait_*` methods"""

    WINDOW_SIZE = None

    """Rendering window size

    It can be useful for responsive websites which show or hide elements depending
    on the viewport size.

    (width, height)
    """

    SAVE_SCREENSHOTS = True

    """Save screenshots on logs directory"""

    SOURCE_MODE = False

    """Append view-source to urls"""

    DEFAULT_LOAD_STATE = 'domcontentloaded'

    """Default load state for location"""

    LOCALE = 'en-US'
    """Locale of the browser"""

    BASEURL = None

    DOWNLOAD = None

    DOWNGRADE = False

    MAX_SAVED_RESPONSES = (1 << 30)  # limit to 1GiB

    def __init__(self, logger=None, proxy=None, responses_dirname=None, backend=None):
        super(PlaywrightBrowser, self).__init__()
        self.responses_dirname = responses_dirname
        self.responses_count = 0
        self.backend = backend
        if logger is None:
            self.logger = logging.getLogger('browser')
            formatter = '%(asctime)s:%(levelname)s:%(name)s:%(filename)s:%(lineno)d:%(funcName)s %(message)s'
            sh = logging.StreamHandler(sys.stdout)
            #sh.setLevel(logging.DEBUG)
            sh.setFormatter(createColoredFormatter(sys.stdout, formatter))
            self.logger.addHandler(sh)
            self.logger.propagate = False
        else:
            self.logger = logger
        self.logger.setLevel(logging.DEBUG)
        self.proxy = proxy or {}

        self.driver = None          # webdriver
        self.browser = None         # browser context
        self.current_page = None    # current page

        self.implicit_timeout = 0
        self.last_page_hash = None
        self.vdisplay = Xvfb()

        self._setup()

        self._urls = []
        cls = type(self)
        for attr in dir(cls):
            val = getattr(cls, attr)
            if isinstance(val, URL):
                val = deepcopy(val)
                val.browser = self
                setattr(self, attr, val)
                self._urls.append(val)
        self._urls.sort(key=lambda u: u._creation_counter)

    def _build_browser(self) -> BrowserType:
        DRIVER_CLASSES = {
            'firefox': self.driver.firefox,
            'chromium': self.driver.chromium,
            'webkit': self.driver.webkit,
        }
        return DRIVER_CLASSES[self.DRIVER]

    def _parse_proxy(self, _proxy) -> dict:
        '''
            Format: lum-customer-c_f9eb8d89-zone-datacenter20000-ip-158.46.169.208:isjjehb6ctmp@zproxy.lum-superproxy.io:22225
        '''
        proxy = {}
        if 'http' in _proxy:
            proxy = _proxy['http']
        elif 'https' in _proxy:
            proxy = _proxy['https']

        if proxy:
            first, last = proxy.split('@')
            first = first.lstrip('http://').lstrip('https://')
            username = first.split(':')[0]
            password = first.split(':')[1]

            return {
                'server': 'http://' + last,
                'username': username,
                'password': password
            }

    def assign_proxy(self, proxy):
        proxy = self._parse_proxy(proxy)

        self.browser.close()
        self.driver.stop()

        self.logger.warning(proxy)

        self._setup(proxy)

    def _setup(self, PROXIES: dict = {}):
        if self.HEADLESS is False and not os.getenv("DISPLAY"):
            self.vdisplay.start()

        self.driver = sync_playwright().start()

        capa = self._build_browser()
        options = {'persistentContext': False}

        if self.DRIVER == 'firefox':
            if self.responses_dirname and not os.path.isdir(self.responses_dirname):
                os.makedirs(self.responses_dirname)

            if self.DOWNLOAD:
                mime_types = "application/pdf,text/csv"
                options['firefoxUserPrefs'] = {
                    'browser.download.folderList': 2,
                    'browser.download.manager.showWhenStarting': False,
                    'browser.download.dir': '/tmp',
                    'browser.helperApps.neverAsk.saveToDisk': mime_types,
                    'plugin.disable_full_page_plugin_for_types': mime_types,
                    'pdfjs.disabled': True,
                    'browser.download.manager.closeWhenDone': True
                }
            if self.responses_dirname:
                options['persistentContext'] = True
        elif self.DRIVER == 'chromium':
            options['args'] = [
                '--blink-settings=imagesEnabled=false'
            ]
        elif self.DRIVER == 'webkit':
            if self.responses_dirname:
                if not os.path.isdir(self.responses_dirname):
                    os.makedirs(self.responses_dirname)

            if self.responses_dirname:
                options['persistentContext'] = True
        else:
            raise NotImplementedError()

        if PROXIES:
            options['proxy'] = PROXIES

        if self.WINDOW_SIZE:
            (width, height) = self.WINDOW_SIZE
            options['screen'] = {
                'width': width,
                'height': height
            }

        options['headless'] = self.HEADLESS

        if not self.responses_dirname:
            self.responses_dirname = tempfile.mkdtemp(prefix='monseigneur_session_')
            self.logger.info("responses dirname is %s" % (self.responses_dirname))

        if options['persistentContext'] == True:
            del options['persistentContext']
            options['user_data_dir'] = self.responses_dirname
            options['record_har_path'] = self.responses_dirname + "/logs.har"
            options['locale'] = self.LOCALE
            self.browser = capa.launch_persistent_context(**options)
            self.current_page = self.browser.pages[0]
        else:
            del options['persistentContext']
            browser = capa.launch(**options)
            self.browser = browser.new_context(record_har_path=self.responses_dirname+"/log.har", locale=self.LOCALE)
            self.current_page = self.browser.new_page()

        self.browser.set_default_timeout(self.DEFAULT_WAIT)
        self.browser.set_default_navigation_timeout(self.DEFAULT_WAIT)

    ### de initialize browser
    def deinit(self):
        pass
        # if self.browser:
        #    self.browser.close()
        # if self.driver:
        #    self.driver.stop()

    @property
    def url(self):
        return self.current_page.url

    @property
    def page(self):
        def do_on_load(page):
            if hasattr(page, 'on_load'):
                page.on_load()

        for val in self._urls:
            if not val.match(self.url):
                continue

            page = val.klass(self, response=self.response)
            with self.implicit_wait(0):
                try:
                    self.logger.debug('Handle %s with %s' % (self.url, type(page).__name__))
                    page.doc = page.build_doc(self.current_page.content().encode())
                    self.save_response_if_changed()
                    do_on_load(page)
                    return page
                except Exception as e:
                    print(e)

        self.logger.debug('Unable to handle %s', self.url)

    @property
    def pages(self):
        return self.browser.pages

    def new_page(self):
        return self.browser.new_page()

    def switch_to_page(self, no: int = 1):
        self.current_page = self.browser.pages[no]
        self.logger.debug("switched to page %d" % (no))

    def open(self, url, state=None, *args, **kwargs):
        """Opens url in a new page"""
        self.current_page = self.browser.new_page()
        self.logger.debug("new page created")
        return self.location(url, state=state)

    def _build_response(self, _response: Response):
        response = PageResponse()
        response.url = self.current_page.url
        response.content = self.current_page.content().encode()
        response.encoding = 'utf-8'
        response.headers = _response.headers
        response.status_code = _response.status
        response.request.headers = _response.request.headers
        response.request.data = _response.request.post_data
        response.text = self.current_page.content()
        return response

    @retry(TimeoutError, tries=3, delay=2, backoff=1)
    @retry(Error, tries=3, delay=5, backoff=1)
    def location(self, url, state=None, timeout=None, *args, **kwargs):
        """Change current url of the browser.

        Warning: unlike other requests-based monseigneur browsers, this function does not block
        until the page is loaded, it's completely asynchronous.
        To use the new page content, it's necessary to wait, either implicitly (e.g. with
        context manager :any:`implicit_wait`) or explicitly (e.g. using method
        :any:`wait_until`)
        """
        self.logger.debug('opening %r', url)
        if self.SOURCE_MODE:
            url = 'view-source:' + url
        response = self.current_page.goto(url, wait_until = state or self.DEFAULT_LOAD_STATE, timeout = timeout or self.DEFAULT_WAIT)
        if response:
            self.response = self._build_response(response)
            self.response.page = self.page
            return self.response

    def export_session(self):
        cookies = [cookie.copy() for cookie in self.browser.cookies()]
        for cookie in cookies:
            cookie['expirationDate'] = cookie.pop('expiry', None)

        ret = {
            'url': self.url,
            'cookies': cookies,
        }
        return ret

    def save_response_if_changed(self):
        hash = hashlib.md5(self.current_page.content().encode('utf-8')).hexdigest()
        if self.last_page_hash != hash:
            self.save_response()
            self.last_page_hash = hash
            return True

        self.last_page_hash = hash
        return False

    def save_response(self):
        if self.responses_dirname:
            if not os.path.isdir(self.responses_dirname):
                os.makedirs(self.responses_dirname)

            total = sum(os.path.getsize(f) for f in glob('%s/*' % self.responses_dirname))
            if self.MAX_SAVED_RESPONSES is not None and total >= self.MAX_SAVED_RESPONSES:
                self.logger.info('quota reached, not saving responses')
                return

            self.responses_count += 1
            path = '%s/%02d.html' % (self.responses_dirname, self.responses_count)
            with codecs.open(path, 'w', encoding='utf-8') as fd:
                fd.write(self.current_page.content())
            self.logger.info('Response saved to %s', path)
            if self.SAVE_SCREENSHOTS:
                ss_path = path.replace(".html", ".png")
                self.current_page.screenshot(path=ss_path)
                self.logger.info('Screenshot saved to %s', ss_path)

    def absurl(self, uri, base=None):
        # FIXME this is copy-pasta from DomainBrowser
        if not base:
            base = self.url
        if base is None or base is True:
            base = self.BASEURL
        return urljoin(base, uri)

    def get_item(self, xpath):
        try:
            return self.current_page.wait_for_selector('xpath={}'.format(xpath), timeout=500)
        except TimeoutError:
            return None

    ### a few selenium wrappers
    def wait_xpath(self, xpath, state='visible', timeout=30000, tries=1):
        while tries:
            try:
                return self.current_page.wait_for_selector('xpath=%s' % (xpath), state=state, timeout=timeout)
            except TimeoutError:
                None
            tries -= 1

    def wait_selector(self, selector, state='visible', timeout=30000):
        return self.current_page.wait_for_selector('%s' % (selector), state=state, timeout=timeout)

    def wait_xpath_visible(self, xpath, timeout=30000):
        return self.current_page.wait_for_selector('xpath=%s' % (xpath), timeout=timeout, state='visible')

    def wait_xpath_clickable(self, xpath, timeout=30000):
        raise NotImplementedError

    def wait_for_state(self, state: Literal['domcontentloaded', 'load', 'networkidle'], timeout: int = 30000):
        return self.current_page.wait_for_load_state(state, timeout=timeout)

    def wait_until(self, condition, timeout=30000):
        '''Not useful in playwright'''
        raise NotImplementedError

    def is_element_present(self, xpath) -> bool:
        try:
            self.current_page.wait_for_selector('xpath=%s' % (xpath), state='attached', timeout=500)
            return True
        except TimeoutError:
            return False

    def is_element_present_js(self, selector) -> bool:
        return self.current_page.evaluate('document.querySelectorAll("%s").length' % selector)

    def click(self, xpath, click_count=1, timeout=30000):
        self.current_page.click('xpath=%s' % (xpath), click_count=click_count, timeout=timeout)

    def implicitly_wait(self, timeout):
        """Set implicit wait time

        When querying anything in DOM in Selenium, like evaluating XPath, if not found,
        Selenium will wait in a blocking manner until it is found or until the
        implicit wait timeouts.
        By default, it is 0, so if an XPath is not found, it fails immediately.

        :param timeout: new implicit wait time in seconds
        """
        self.implicit_timeout = timeout
        self.current_page.set_default_timeout(timeout)

    @contextmanager
    def implicit_wait(self, timeout):
        """Context manager to change implicit wait time and restore it

        Example::

            with browser.implicit_wait(10):
                # Within this block, the implicit wait will be set to 10 seconds
                # and be restored at the end of block.
                # If the link is not found immediately, it will be periodically
                # retried until found (for max 10 seconds).
                el = self.find_element_link_text("Show list")
                el.click()
        """

        old = self.implicit_timeout
        try:
            self.current_page.set_default_timeout(timeout)
            yield
        finally:
            self.current_page.set_default_timeout(old)

    @contextmanager
    def in_frame(self, selector):
        """Context manager to execute a block inside a frame and restore main page after.

        In selenium, to operate on a frame's content, one needs to switch to the frame before
        and return to main page after.

        :param selector: selector to match the frame

        Example::

            with self.in_frame(xpath_locator('//frame[@id="foo"]')):
                el = self.find_element_by_xpath('//a[@id="bar"]')
                el.click()
        """

        frame = self.current_page.frame_locator(selector)
        yield frame

    def get_storage(self):
        """Get localStorage content for current domain.

        As for cookies, this method only manipulates data for current domain.
        It's not possible to get all localStorage content. To get localStorage
        for multiple domains, the browser must change the url to each domain
        and call get_storage each time after.
        To do so, it's wise to choose a neutral URL (like an image file or JS file)
        to avoid the target page itself changing the cookies.
        """
        ret = self.current_page.evaluate('''() => {
            let d = {};
            for (var i = 0; i < window.localStorage.length; i++){
                let k = window.localStorage.key(i);
                d[k] = window.localStorage.getItem(k);
            }
            return d;
        }''')
        return ret

    def update_storage(self, d):
        """Update local storage content for current domain.

        It has the same restrictions as `get_storage`.
        """

        for k, v in d.items():
            self.current_page.evaluate('''() => {
                window.localStorage.setItem('%s', '%s')
            }''' % (k, v))

    def clear_storage(self):
        """Clear local storage."""

        self.current_page.evaluate('() => window.localStorage.clear()')

    def scroll_to_bottom(self):
        """Scroll to bottom of the page."""

        self.current_page.evaluate("window.scrollTo(0, document.body.scrollHeight);")

    def scroll_to_top(self):
        """Scroll to top of the page."""

        self.current_page.evaluate("window.scrollTo(0, 0);")

    def scroll_to_element(self, element, behavior='smooth'):
        """Scroll to element."""

        view_port_height = "var viewPortHeight = Math.max(document.documentElement.clientHeight, window.innerHeight || 0);"
        element_top = "var elementTop = arguments[0].getBoundingClientRect().top;"
        js_function = "window.scrollBy(0, elementTop-(viewPortHeight/2));"
        scroll_into_middle = view_port_height + element_top + js_function
        self.current_page.evaluate(scroll_into_middle, element)

    def load_state(self, state):
        if 'cookies' in state:
            assert hasattr(self, "browser")
            cookies = pickle.loads(zlib.decompress(base64.b64decode(state['cookies'])))
            self.browser.add_cookies(cookies)
        for attrname in self.__states__:
            if attrname in state:
                setattr(self, attrname, state[attrname])

    def dump_state(self):
        state = dict()
        state['cookies'] = base64.b64encode(zlib.compress(pickle.dumps(self.export_session()['cookies'], -1)))
        for attrname in self.__states__:
            try:
                state[attrname] = getattr(self, attrname)
            except AttributeError:
                pass
        self.logger.info('Stored cookies into storage')
        return state

    def dump_pickle(self, state, path):
        with open(path, "wb") as pickle_out:
            pickle.dump(state, pickle_out)
        self.logger.info('State dumped into pickle')


class SubSeleniumMixin(object):
    """Mixin to have a Selenium browser for performing login."""

    SELENIUM_BROWSER = None

    """Class of Selenium browser to use for the login"""

    __states__ = ('selenium_state',)

    selenium_state = None

    def create_selenium_browser(self):
        dirname = self.responses_dirname
        if dirname:
            dirname += '/selenium'

        return self.SELENIUM_BROWSER(self.config, logger=self.logger, responses_dirname=dirname, proxy=self.PROXIES)

    def do_login(self):
        sub_browser = self.create_selenium_browser()
        try:
            if self.selenium_state and hasattr(sub_browser, 'load_state'):
                sub_browser.load_state(self.selenium_state)
            sub_browser.do_login()
            self.load_selenium_session(sub_browser)
        finally:
            try:
                if hasattr(sub_browser, 'dump_state'):
                    self.selenium_state = sub_browser.dump_state()
            finally:
                sub_browser.deinit()

    def load_selenium_session(self, selenium):
        d = selenium.export_session()
        for cookie in d['cookies']:
            self.session.cookies.set(cookie['name'], cookie['value'], domain=cookie['domain'])

        if hasattr(self, 'locate_browser'):
            self.locate_browser(d)
