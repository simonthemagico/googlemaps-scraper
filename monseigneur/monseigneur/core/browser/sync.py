import os
import pickle
import time

from .browsers import LoginBrowser, StatesMixin
from .curl import PyCurlLogin, PyCurlMixin
from .url import URL
from .pages import JsonPage
from .filters.json import Dict
from .exceptions import LoggedOut
from ..tools.decorators import retry

from matrix.core.exceptions import PauseRunException
from matrix.core.run_done_reasons import OtpNeeded, WrongCredentials, TwofaRequired, CheckpointReached, CookiesExpired


class AccountSyncError(Exception):
    pass


class OtpNeededException(Exception):
    pass


class AccountSyncServerDown(Exception):
    pass



class SyncPage(JsonPage):

    def get_id(self):
        return Dict("id")(self.doc)

    def get_status(self):
        return Dict("status_text")(self.doc)

    def get_status_code(self):
        return Dict("status_code")(self.doc)

    def get_state(self):
        return self.doc


def logged(f):
    @retry(LoggedOut, tries=3, delay=2, backoff=0)
    def wrapped(self, *args, **kwargs):
        try:
            return f(self, *args, **kwargs)
        except LoggedOut as e:
            self.state = {}
            self.logged = False
            self.do_login()
            raise e

    return wrapped


class AccountSyncBrowser(LoginBrowser, StatesMixin):
    """
    A browser with works with AccountSync module
    """

    SYNC_USER = 'dropsync'
    SYNC_PASS = '!nSlEtbR0Tlo'
    SYNC_HOST = os.getenv("SYNC_HOST", "localhost")

    account_sync_create_task = URL(r"http://{}:8100/synchronize".format(SYNC_HOST), SyncPage)
    account_sync_get_task = URL(r"http://{}:8100/synchronize/(?P<task_id>.*)".format(SYNC_HOST), SyncPage)
    account_sync_get_state = URL(r"http://{}:8100/state/(?P<account_id>.*)".format(SYNC_HOST), SyncPage)

    def __init__(self, state={}, unique_id=None, user_id=None, cluster_id=None, increment_value=None, *args, **kwargs):
        assert unique_id
        assert user_id
        # assert cluster_id

        username = kwargs.pop("username", None)
        password = kwargs.pop("password", None)
        type = kwargs.pop("type", "the")

        super(AccountSyncBrowser, self).__init__(username=username, password=password, *args, **kwargs)
        self.type = type
        self.username = username
        self.state = state
        self.unique_id = unique_id
        self.user_id = user_id
        self.cluster_id = cluster_id
        self.__increment_value = increment_value

    def increment_value(self, attribute: str):
        if self.__increment_value:
            return self.__increment_value(attribute)
        raise NotImplementedError

    def do_login(self):
        '''
            do_login: login_wo_state also calls login_with_state at the end
        '''
        # logging into account
        type = "".join(x.title() for x in self.type.split("-")).replace("Sync","")
        if hasattr(self.logger, 'user'):
            self.logger.user("💬 Logging into {} account ({})".format(type, self.username))
        if self.state and self.state != {}:
            try:
                self.login_with_state()
            except AssertionError:
                self.login_wo_state()
        else:
            self.login_wo_state()

        self.logged = True

    def is_valid_token(self):
        raise NotImplementedError

    def login_with_state(self):
        assert self.state, "No state available"
        if not self.PROXIES:
            raise AccountSyncError("proxy required")

        state_dict = self.state
        if 'url' in state_dict:
            del state_dict['url']
        self.load_state(state_dict)
        assert self.is_valid_token()

        # successful login
        if hasattr(self.logger, 'user'):
            self.logger.user("💬 Logging successfully achieved!")

    # @retry(AssertionError, tries=3, delay=1, backoff=2)
    def login_wo_state(self):
        try:
            assert self.unique_id
            profile_path = '/home/matrix/mdev/account_sync_api/profiles/%s/state.pickle' % (self.unique_id)
            assert os.path.exists(profile_path)
            with open(profile_path, 'rb') as f:
                state = pickle.load(f)
            self.state = state
            self.login_with_state()
            return True
        except AssertionError:
            raise PauseRunException(CookiesExpired)

        self.session.cookies.clear()

        _PROXIES = self.PROXIES

        if not _PROXIES:
            raise AccountSyncError("proxy required")

        data = {
            "account": self.unique_id,
            "proxy_string": self.PROXIES.lstrip('http://') if type(self.PROXIES) == str else self.PROXIES.get("http").lstrip('http://'),
            "user_id": self.user_id,
            "cluster_id": self.cluster_id,
            "origin": "automation"
        }

        _PROXIES = self.PROXIES

        self.PROXIES = None

        self.account_sync_create_task.go(method="POST", json=data, auth=(self.SYNC_USER, self.SYNC_PASS), verify=False)
        assert self.account_sync_create_task.is_here()

        task_id = self.page.get_id()

        # sleep
        time.sleep(2)
        self.account_sync_get_task.go(task_id=task_id, auth=(self.SYNC_USER, self.SYNC_PASS))
        assert self.account_sync_get_task.is_here()

        status = self.page.get_status_code()

        # wait for max 10 minutes
        for _ in range(600):
            time.sleep(1)
            if status != 100:
                break
            try:
                self.account_sync_get_task.go(task_id=task_id, auth=(self.SYNC_USER, self.SYNC_PASS))
                assert self.account_sync_get_task.is_here()
            except:
                self.PROXIES = self.session.PROXIES = _PROXIES
                continue
            status = self.page.get_status_code()

        if status == 100:
            raise AccountSyncServerDown

        if status in [170, 180]:
            self.PROXIES = self.session.PROXIES = _PROXIES
            raise PauseRunException(OtpNeeded)

        if status == 190:
            self.PROXIES = self.session.PROXIES = _PROXIES
            raise PauseRunException(CheckpointReached)

        if status == 150:
            raise PauseRunException(WrongCredentials)

        if status == 429:
            raise PauseRunException(CookiesExpired)

        if status != 200:
            self.PROXIES = self.session.PROXIES = _PROXIES
            raise AccountSyncError(self.page.get_state())
        try:
            self.account_sync_get_state.go(account_id=self.unique_id, auth=(self.SYNC_USER, self.SYNC_PASS))
            assert self.account_sync_get_state.is_here()
        except Exception as exc:
            self.PROXIES = self.session.PROXIES = _PROXIES
            raise exc

        state = self.page.get_state()

        self.state = state
        self.PROXIES = self.session.PROXIES = _PROXIES

        self.login_with_state()


class AccountSyncCurlBrowser(PyCurlLogin, PyCurlMixin):
    """
    A browser with works with AccountSync module
    """

    SYNC_USER = 'dropsync'
    SYNC_PASS = '!nSlEtbR0Tlo'
    SYNC_HOST = os.getenv("SYNC_HOST", "localhost")
    state = {}

    account_sync_create_task = URL(r"http://{}:8100/synchronize".format(SYNC_HOST), SyncPage)
    account_sync_get_task = URL(r"http://{}:8100/synchronize/(?P<task_id>.*)".format(SYNC_HOST), SyncPage)
    account_sync_get_state = URL(r"http://{}:8100/state/(?P<account_id>.*)".format(SYNC_HOST), SyncPage)

    def __init__(self, state={}, unique_id=None, cluster_id=None, user_id=None, increment_value=None, *args, **kwargs):
        assert unique_id
        assert user_id
        assert cluster_id

        username = kwargs.pop("username", None)
        password = kwargs.pop("password", None)
        type = kwargs.pop("type", "the")

        super(AccountSyncCurlBrowser, self).__init__(username=username, password=password, responses_dirname=None, *args, **kwargs)
        self.username = username
        self.type = type
        self.state = state
        self.unique_id = unique_id
        self.user_id = user_id
        self.cluster_id = cluster_id
        self.__increment_value = increment_value

    def increment_value(self, attribute: str):
        if self.__increment_value:
            return self.__increment_value(attribute)
        raise NotImplementedError

    def do_login(self):
        '''
            do_login: login_wo_state also calls login_with_state at the end
        '''
        # logging into account
        type = "".join(x.title() for x in self.type.split("-")).replace("Sync","")
        if hasattr(self.logger, 'user'):
            self.logger.user("💬 Logging into {} account ({})".format(type, self.username))

        if self.state and self.state != {}:
            try:
                self.login_with_state()
            except AssertionError:
                self.login_wo_state()
        else:
            self.login_wo_state()

        self.logged = True

    def is_valid_token(self):
        raise NotImplementedError

    def login_with_state(self):
        state_dict = self.state
        # self.logger.warning("loading state dict: {}".format(state_dict))
        if 'url' in state_dict:
            del state_dict['url']
        self.load_state(state_dict)
        assert self.is_valid_token()

        # successful login
        if hasattr(self.logger, 'user'):
            self.logger.user("💬 Logging successfully achieved!")

    @retry(AssertionError, tries=3, delay=1, backoff=2)
    def login_wo_state(self):
        self.session.cookies.clear()
        if 'Authorization' in self.session.headers:
            self.session.headers.pop('Authorization')

        _PROXIES = self.session.PROXIES

        if not _PROXIES:
            raise AccountSyncError("proxy required")

        data = {
            "account": self.unique_id,
            "proxy_string": "{}:{}@{}:{}".format(
                _PROXIES['username'],
                _PROXIES['password'],
                _PROXIES['host'],
                _PROXIES['port']
            ),
            "cluster_id": self.cluster_id,
            "user_id": self.user_id,
            "origin": "automation"
        }

        _PROXIES = self.session.PROXIES
        self.session.PROXIES = {}

        self.location(url="http://{}:8100/synchronize".format(self.SYNC_HOST), http_version=1.1, method="POST", json=data, auth=(self.SYNC_USER, self.SYNC_PASS))
        assert self.account_sync_create_task.is_here()

        task_id = self.page.get_id()

        # sleep
        time.sleep(1)
        self.location(url="http://{}:8100/synchronize/{}".format(self.SYNC_HOST, task_id), http_version=1.1, method="GET", auth=(self.SYNC_USER, self.SYNC_PASS))
        assert self.account_sync_get_task.is_here()

        status = self.page.get_status()

        for _ in range(5):
            self.location(url="http://{}:8100/synchronize/{}".format(self.SYNC_HOST, task_id), http_version=1.1, method="GET", auth=(self.SYNC_USER, self.SYNC_PASS))
            assert self.account_sync_get_task.is_here()
            status = self.page.get_status()
            if status == "created":
                time.sleep(2)

        while self.page.get_status_code() == 100:
            time.sleep(1)

            self.location(url="http://{}:8100/synchronize/{}".format(self.SYNC_HOST, task_id), http_version=1.1, method="GET", auth=(self.SYNC_USER, self.SYNC_PASS))
            assert self.account_sync_get_task.is_here()

            status = self.page.get_status()

        status_code = self.page.get_status_code()

        if status_code == 170:
            self.PROXIES = _PROXIES
            raise PauseRunException(OtpNeeded)

        if status_code == 190:
            self.PROXIES = _PROXIES
            raise PauseRunException(CheckpointReached)

        if status_code == 1000:
            self.PROXIES = _PROXIES
            raise PauseRunException(TwofaRequired)

        if status_code != 200:
            self.PROXIES = _PROXIES
            raise AccountSyncError(self.page.get_state())

        self.location(url="http://{}:8100/state/{}".format(self.SYNC_HOST, self.unique_id), http_version=1.1, method="GET", auth=(self.SYNC_USER, self.SYNC_PASS))
        assert self.account_sync_get_state.is_here()

        state = self.page.get_state()
        # self.logger.warning("refreshed state: {}".format(state))

        self.state = state
        self.session.PROXIES = _PROXIES

        self.login_with_state()
