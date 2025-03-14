# -*- coding: utf-8 -*-

from __future__ import unicode_literals, absolute_import

import codecs
from collections import OrderedDict
from contextlib import contextmanager
from copy import deepcopy
from glob import glob
import os
import base64
import zlib
import pickle
import hashlib
from tempfile import NamedTemporaryFile
import time

try:
    from selenium import webdriver
except ImportError:
    raise ImportError('Please install python-selenium')

from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.common.proxy import Proxy, ProxyType
from selenium.common.exceptions import (
    NoSuchElementException, TimeoutException, NoSuchFrameException,
)
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.firefox_profile import FirefoxProfile
from selenium.webdriver.remote.command import Command
from monseigneur.core.tools.log import getLogger
from monseigneur.core.tools.compat import urljoin
from url_normalize import url_normalize

from .pages import HTMLPage as BaseHTMLPage
from .url import URL


__all__ = (
    'SeleniumBrowser', 'SeleniumPage', 'HTMLPage',
    'CustomCondition', 'AnyCondition', 'AllCondition', 'NotCondition',
    'IsHereCondition', 'VisibleXPath', 'ClickableXPath', 'ClickableLinkText',
    'HasTextCondition', 'WrapException',
    'xpath_locator', 'link_locator', 'ElementWrapper',
)


class CustomCondition(object):
    """Abstract condition class

    In Selenium, waiting is done on callable objects named "conditions".
    Basically, a condition is a function predicate returning True if some condition is met.

    The builtin selenium conditions are in :any:`selenium.webdriver.support.expected_conditions`.

    This class exists to differentiate normal methods from condition objects when calling :any:`SeleniumPage.is_here`.

    See https://seleniumhq.github.io/selenium/docs/api/py/webdriver_support/selenium.webdriver.support.expected_conditions.html
    When using `selenium.webdriver.support.expected_conditions`, it's better to
    wrap them using :any:`WrapException`.
    """

    def __call__(self, driver):
        raise NotImplementedError()


class WrapException(CustomCondition):
    """Wrap Selenium's builtin `expected_conditions` to catch exceptions.

    Selenium's builtin `expected_conditions` return True when a condition is met
    but might throw exceptions when it's not met, which might not be desirable.

    `WrapException` wraps such `expected_conditions` to catch those exception
    and simply return False when such exception is thrown.
    """
    def __init__(self, condition):
        self.condition = condition

    def __call__(self, driver):
        try:
            return self.condition(driver)
        except NoSuchElementException:
            return False


class AnyCondition(CustomCondition):
    """Condition that is true if any of several conditions is true.
    """

    def __init__(self, *conditions):
        self.conditions = tuple(WrapException(cb) for cb in conditions)

    def __call__(self, driver):
        return any(cb(driver) for cb in self.conditions)


class AllCondition(CustomCondition):
    """Condition that is true if all of several conditions are true.
    """

    def __init__(self, *conditions):
        self.conditions = tuple(WrapException(cb) for cb in conditions)

    def __call__(self, driver):
        return all(cb(driver) for cb in self.conditions)


class NotCondition(CustomCondition):
    """Condition that tests the inverse of another condition."""

    def __init__(self, condition):
        self.condition = WrapException(condition)

    def __call__(self, driver):
        return not self.condition(driver)


class IsHereCondition(CustomCondition):
    """Condition that is true if a page "is here".

    This condition is to be passed to `SeleniumBrowser.wait_until`.
    It mustn't be used in a `SeleniumPage.is_here` definition.
    """
    def __init__(self, urlobj):
        assert isinstance(urlobj, URL)
        self.urlobj = urlobj

    def __call__(self, driver):
        return self.urlobj.is_here()


class WithinFrame(CustomCondition):
    """Check a condition inside a frame.

    In Selenium, frames are separated from each other and from the main page.
    This class wraps a condition to execute it within a frame.
    """

    def __init__(self, selector, condition):
        self.selector = selector
        self.condition = condition

    def __call__(self, driver):
        try:
            driver.switch_to.frame(self.selector)
        except NoSuchFrameException:
            return False

        try:
            return self.condition(driver)
        finally:
            driver.switch_to.default_content()


class StablePageCondition(CustomCondition):
    """
    Warning: this condition will not work if a site has a carousel or something
    like this that constantly changes the DOM.
    """

    purge_times = 10

    def __init__(self, waiting=3):
        self.elements = OrderedDict()
        self.waiting = waiting

    def _purge(self):
        now = time.time()

        for k in list(self.elements):
            if now - self.elements[k][0] > self.purge_times * self.waiting:
                del self.elements[k]

    def __call__(self, driver):
        self._purge()

        hashed = hashlib.md5(driver.page_source.encode('utf-8')).hexdigest()
        now = time.time()
        page_id = driver.find_element_by_xpath('/*').id

        if page_id not in self.elements or self.elements[page_id][1] != hashed:
            self.elements[page_id] = (now, hashed)
            return False
        elif now - self.elements[page_id][0] < self.waiting:
            return False
        return True


def VisibleXPath(xpath):
    """Wraps `visibility_of_element_located`"""
    return WrapException(EC.visibility_of_element_located(xpath_locator(xpath)))


def ClickableXPath(xpath):
    """Wraps `element_to_be_clickable`"""
    return WrapException(EC.element_to_be_clickable(xpath_locator(xpath)))


def ClickableLinkText(text, partial=False):
    """Wraps `element_to_be_clickable`"""
    return WrapException(EC.element_to_be_clickable(link_locator(text, partial)))


def HasTextCondition(xpath):
    """Condition to ensure some xpath is visible and contains non-empty text."""

    xpath = '(%s)[normalize-space(text())!=""]' % xpath
    return VisibleXPath(xpath)


def xpath_locator(xpath):
    """Creates an XPath locator from a string

    Most Selenium functions don't accept XPaths directly but "locators".
    Locators can be XPath, CSS selectors.
    """
    return (By.XPATH, xpath)


def link_locator(text, partial=False):
    """Creates an link text locator locator from a string

    Most Selenium functions don't accept XPaths directly but "locators".

    Warning: if searched text is not directly in <a> but in one of its children,
    some webdrivers might not find the link.
    """
    if partial:
        return (By.PARTIAL_LINK_TEXT, text)
    else:
        return (By.LINK_TEXT, text)


class ElementWrapper(object):
    """Wrapper to Selenium element to ressemble lxml.

    Some differences:
    - only a subset of lxml's Element class are available
    - cannot access XPath "text()", only Elements

    See https://seleniumhq.github.io/selenium/docs/api/py/webdriver_remote/selenium.webdriver.remote.webelement.html
    """
    def __init__(self, wrapped):
        self.wrapped = wrapped

    def xpath(self, xpath):
        """Returns a list of elements matching `xpath`.

        Since it uses `find_elements_by_xpath`, it does not raise
        `NoSuchElementException` or `TimeoutException`.
        """
        return [ElementWrapper(sel) for sel in self.wrapped.find_elements_by_xpath(xpath)]

    def text_content(self):
        return self.wrapped.text

    @property
    def text(self):
        # Selenium can only fetch text recursively.
        # Could be implemented by injecting JS though.
        raise NotImplementedError()

    def itertext(self):
        return [self.wrapped.text]

    def __getattr__(self, attr):
        return getattr(self.wrapped, attr)

    @property
    class attrib(object):
        def __init__(self, el):
            self.el = el

        def __getitem__(self, k):
            v = self.el.get_attribute(k)
            if v is None:
                raise KeyError('Attribute %r was not found' % k)
            return v

        def get(self, k, default=None):
            v = self.el.get_attribute(k)
            if v is None:
                return default
            return v


class SeleniumPage(object):
    """Page to use in a SeleniumBrowser

    Differences with regular Pages:
    - cannot access raw HTML text
    """

    logged = False

    def __init__(self, browser):
        super(SeleniumPage, self).__init__()
        self.params = {}
        self.browser = browser
        self.driver = browser.driver
        self.logger = getLogger(self.__class__.__name__.lower(), browser.logger)

    @property
    def doc(self):
        return ElementWrapper(self.browser.driver.find_element_by_xpath('/*'))

    def is_here(self):
        """Method to determine if the browser is on this page and the page is ready.

        Use XPath and page content to determine if we are on this page.
        Make sure the page is "ready" for the usage we want. For example, if there's
        a splash screen in front the page, preventing click, it should return False.

        `is_here` can be a method or a :any:`CustomCondition` instance.
        """
        return True

    # TODO get_form


class HTMLPage(BaseHTMLPage):
    ENCODING = 'utf-8'

    def __init__(self, browser):
        fake = FakeResponse(
            url=browser.url,
            text=browser.page_source,
            content=browser.page_source.encode('utf-8'),
            encoding = 'utf-8',
        )

        super(HTMLPage, self).__init__(browser, fake, encoding='utf-8')
        self.driver = browser.driver


OPTIONS_CLASSES = {
    webdriver.Firefox: webdriver.FirefoxOptions,
    webdriver.Chrome: webdriver.ChromeOptions,
    webdriver.PhantomJS: webdriver.ChromeOptions, # unused, put dummy thing
}


CAPA_CLASSES = {
    webdriver.Firefox: DesiredCapabilities.FIREFOX,
    webdriver.Chrome: DesiredCapabilities.CHROME,
    webdriver.PhantomJS: DesiredCapabilities.PHANTOMJS,
}


class DirFirefoxProfile(FirefoxProfile):
    def __init__(self, custom_dir):
        self._monseigneur_dir = custom_dir
        super(DirFirefoxProfile, self).__init__()

    def _create_tempfolder(self):
        if self._monseigneur_dir:
            return self._monseigneur_dir
        return super(DirFirefoxProfile, self)._create_tempfolder()


class FakeResponse(object):
    page = None

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class SeleniumBrowser(object):
    """Browser similar to PagesBrowser, but using Selenium.

    URLs instances can be used. The need_login decorator can be used too.

    Differences:
    - since JS code can be run anytime, the current `url` and `page` can change anytime
    - it's not possible to use `open()`, only `location()` can be used
    - many options are not implemented yet (like proxies) or cannot be implemented at all
    """

    DRIVER = webdriver.Firefox

    """Selenium driver class"""

    HEADLESS = True

    """Run without any display"""

    DEFAULT_WAIT = 10

    """Default wait time for `wait_*` methods"""

    WINDOW_SIZE = None

    """Rendering window size

    It can be useful for responsive websites which show or hide elements depending
    on the viewport size.
    """

    DOWNGRADE = None

    BASEURL = None

    DOWNLOAD = None

    MAX_SAVED_RESPONSES = (1 << 30)  # limit to 1GiB

    def __init__(self, logger=None, proxy=None, responses_dirname=None, backend=None):
        super(SeleniumBrowser, self).__init__()
        self.responses_dirname = responses_dirname
        self.responses_count = 0
        self.backend = backend
        self.logger = getLogger('browser', logger)
        self.proxy = proxy or {}

        self.implicit_timeout = 0
        self.last_page_hash = None

        self._setup_driver()

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

    def _build_options(self):
        return OPTIONS_CLASSES[self.DRIVER]()

    def _build_capabilities(self):
        return CAPA_CLASSES[self.DRIVER].copy()

    def _setup_driver(self):
        proxy = Proxy()
        proxy.proxy_type = ProxyType.DIRECT
        if 'http' in self.proxy:
            proxy.http_proxy = self.proxy['http']
        if 'https' in self.proxy:
            proxy.ssl_proxy = self.proxy['https']

        capa = self._build_capabilities()
        proxy.add_to_capabilities(capa)

        options = self._build_options()
        # TODO some browsers don't need headless
        # TODO handle different proxy setting?
        options.set_headless(self.HEADLESS)

        if self.DRIVER is webdriver.Firefox:
            if self.responses_dirname and not os.path.isdir(self.responses_dirname):
                os.makedirs(self.responses_dirname)

            options.profile = DirFirefoxProfile(self.responses_dirname)
            if self.DOWNLOAD:
                mime_types = "application/pdf,text/csv"
                options.profile.set_preference("browser.download.folderList", 2)
                options.profile.set_preference("browser.download.manager.showWhenStarting", False)
                options.profile.set_preference("browser.download.dir", "/tmp")
                options.profile.set_preference("browser.helperApps.neverAsk.saveToDisk", mime_types)
                options.profile.set_preference("plugin.disable_full_page_plugin_for_types", mime_types)
                options.profile.set_preference("pdfjs.disabled", True)
                options.profile.set_preference("browser.download.manager.closeWhenDone", True)
            if self.responses_dirname:
                capa['profile'] = self.responses_dirname
            self.driver = self.DRIVER(options=options, capabilities=capa)
        elif self.DRIVER is webdriver.Chrome:
            self.driver = self.DRIVER(options=options, desired_capabilities=capa)
        elif self.DRIVER is webdriver.PhantomJS:
            if self.responses_dirname:
                if not os.path.isdir(self.responses_dirname):
                    os.makedirs(self.responses_dirname)
                log_path = os.path.join(self.responses_dirname, 'selenium.log')
            else:
                log_path = NamedTemporaryFile(prefix='monseigneur_selenium_', suffix='.log', delete=False).name

            self.driver = self.DRIVER(desired_capabilities=capa, service_log_path=log_path)
        else:
            raise NotImplementedError()

        if self.WINDOW_SIZE:
            self.driver.set_window_size(*self.WINDOW_SIZE)

    ### Browser
    def deinit(self):
        if self.driver:
            self.driver.quit()

    @property
    def url(self):
        return self.driver.current_url

    @property
    def page(self):
        def do_on_load(page):
            if hasattr(page, 'on_load'):
                page.on_load()

        for val in self._urls:
            if not val.match(self.url):
                continue

            page = val.klass(self)
            with self.implicit_wait(0):
                try:
                    if isinstance(page.is_here, CustomCondition):
                        if page.is_here(self.driver):
                            self.logger.debug('Handle %s with %s', self.url, type(page).__name__)
                            self.save_response_if_changed()
                            do_on_load(page)
                            return page
                    elif page.is_here():
                        self.logger.debug('Handle %s with %s', self.url, type(page).__name__)
                        self.save_response_if_changed()
                        do_on_load(page)
                        return page
                except NoSuchElementException:
                    pass

        self.logger.debug('Unable to handle %s', self.url)

    def open(self, *args, **kwargs):
        # TODO maybe implement with a new window?
        raise NotImplementedError()

    def location(self, url, data=None, headers=None, params=None, method=None, json=None):
        """Change current url of the browser.

        Warning: unlike other requests-based monseigneur browsers, this function does not block
        until the page is loaded, it's completely asynchronous.
        To use the new page content, it's necessary to wait, either implicitly (e.g. with
        context manager :any:`implicit_wait`) or explicitly (e.g. using method
        :any:`wait_until`)
        """
        assert method is None
        assert params is None
        assert data is None
        assert json is None
        assert not headers
        self.logger.debug('opening %r', url)
        self.driver.get(url)

        try:
            WebDriverWait(self.driver, 1).until(EC.url_changes(self.url))
        except TimeoutException:
            pass
        return FakeResponse(page=self.page)

    def export_session(self):
        cookies = [cookie.copy() for cookie in self.driver.get_cookies()]
        for cookie in cookies:
            cookie['expirationDate'] = cookie.pop('expiry', None)

        ret = {
            'url': self.url,
            'cookies': cookies,
        }
        return ret

    def save_response_if_changed(self):
        hash = hashlib.md5(self.driver.page_source.encode('utf-8')).hexdigest()
        if self.last_page_hash != hash:
            self.save_response()

        self.last_page_hash = hash

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
                fd.write(self.driver.page_source)
            self.logger.info('Response saved to %s', path)

    def absurl(self, uri, base=None):
        # FIXME this is copy-pasta from DomainBrowser
        if not base:
            base = self.url
        if base is None or base is True:
            base = self.BASEURL
        return urljoin(base, uri)

    ### a few selenium wrappers
    def wait_xpath(self, xpath, timeout=None):
        self.wait_until(EC.element_to_be_clickable((By.XPATH, xpath)), timeout)

    def wait_xpath_visible(self, xpath, timeout=None):
        self.wait_until(EC.visibility_of_element_located(xpath_locator(xpath)), timeout)

    def wait_xpath_clickable(self, xpath, timeout=None):
        self.wait_until(EC.element_to_be_clickable(xpath_locator(xpath)), timeout)

    def wait_until_is_here(self, urlobj, timeout=None):
        self.wait_until(IsHereCondition(urlobj), timeout)

    def wait_until(self, condition, timeout=None):
        """Wait until some condition object is met

        Wraps WebDriverWait.
        See https://seleniumhq.github.io/selenium/docs/api/py/webdriver_support/selenium.webdriver.support.wait.html

        See :any:`CustomCondition`.

        :param timeout: wait time in seconds (else DEFAULT_WAIT if None)
        """
        if timeout is None:
            timeout = self.DEFAULT_WAIT

        try:
            WebDriverWait(self.driver, timeout).until(condition)
        except (NoSuchElementException, TimeoutException):
            if self.responses_dirname:
                self.driver.get_screenshot_as_file('%s/%02d.png' % (self.responses_dirname, self.responses_count))
            self.save_response()
            raise

    def implicitly_wait(self, timeout):
        """Set implicit wait time

        When querying anything in DOM in Selenium, like evaluating XPath, if not found,
        Selenium will wait in a blocking manner until it is found or until the
        implicit wait timeouts.
        By default, it is 0, so if an XPath is not found, it fails immediately.

        :param timeout: new implicit wait time in seconds
        """
        self.implicit_timeout = timeout
        self.driver.implicitly_wait(timeout)

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
            self.driver.implicitly_wait(timeout)
            yield
        finally:
            self.driver.implicitly_wait(old)

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

        self.driver.switch_to.frame(selector)
        try:
            yield
        finally:
            self.driver.switch_to.default_content()

    def get_storage(self):
        """Get localStorage content for current domain.

        As for cookies, this method only manipulates data for current domain.
        It's not possible to get all localStorage content. To get localStorage
        for multiple domains, the browser must change the url to each domain
        and call get_storage each time after.
        To do so, it's wise to choose a neutral URL (like an image file or JS file)
        to avoid the target page itself changing the cookies.
        """
        response = self.driver.execute(Command.GET_LOCAL_STORAGE_KEYS)

        ret = {}
        for k in response['value']:
            response = self.driver.execute(Command.GET_LOCAL_STORAGE_ITEM, {'key': k})
            ret[k] = response['value']
        return ret

    def update_storage(self, d):
        """Update local storage content for current domain.

        It has the same restrictions as `get_storage`.
        """

        for k, v in d.items():
            self.driver.execute(Command.SET_LOCAL_STORAGE_ITEM, {'key': k, 'value': v})

    def clear_storage(self):
        """Clear local storage."""

        self.driver.execute(Command.CLEAR_LOCAL_STORAGE)

    def scroll_to_bottom(self):
        """Scroll to bottom of the page."""

        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

    def scroll_to_top(self):
        """Scroll to top of the page."""

        self.driver.execute_script("window.scrollTo(0, 0);")

    def scroll_to_element(self, element, behavior='smooth'):
        """Scroll to element."""

        view_port_height = "var viewPortHeight = Math.max(document.documentElement.clientHeight, window.innerHeight || 0);"
        element_top = "var elementTop = arguments[0].getBoundingClientRect().top;"
        js_function = "window.scrollBy(0, elementTop-(viewPortHeight/2));"
        scroll_into_middle = view_port_height + element_top + js_function
        self.driver.execute_script(scroll_into_middle, element)

    def load_state(self, state):
        if 'expire' in state and parser.parse(state['expire']) < datetime.now():
            return self.logger.info('State expired, not reloading it from storage')
        if 'cookies' in state:
            assert hasattr(self, "driver")
            cookies = pickle.loads(zlib.decompress(base64.b64decode(state['cookies'])))
            for cookie in cookies:
                domain = cookie['domain']
                if domain.lstrip('.') not in self.driver.current_url:
                    # Added by Sasha B. due to Selenium restriction
                    self.logger.warning('Now going to %s to add cookie on Selenium' % domain)
                    self.location(url_normalize(domain))
                    for i in range(2):
                        self.logger.warning(i)
                        time.sleep(0.5)
                self.driver.add_cookie(cookie)
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
