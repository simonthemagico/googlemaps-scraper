from functools import wraps
import traceback
from requests.exceptions import ReadTimeout, ConnectTimeout, ConnectionError, TooManyRedirects, ContentDecodingError, InvalidURL, InvalidSchema, MissingSchema, ChunkedEncodingError
from ssl import SSLError
from monseigneur.monseigneur.core.browser.exceptions import HTTPNotFound, ClientError, ServerError
from lxml.etree import XMLSyntaxError


def location_error_handler(func):
    @wraps(func)
    def inner(self, *args, **kwargs):

        assert hasattr(self, 'logger')

        try:
            func_output = func(self, *args, **kwargs)
            return func_output
        except ConnectTimeout as c:
            self.logger.warning(c)
            return []
        except ReadTimeout as r:
            self.logger.warning(r)
            return []
        except ConnectionError as d:
            self.logger.warning(d)
            return []
        except HTTPNotFound as h:
            self.logger.warning(h)
            return []
        except ClientError as cl:
            self.logger.warning(cl)
            return []
        except ServerError as sr:
            self.logger.warning(sr)
            return []
        except TooManyRedirects as tm:
            self.logger.warning(tm)
            return []
        except ContentDecodingError as cde:
            self.logger.warning(cde)
            return []
        except InvalidURL as ivd:
            self.logger.warning(ivd)
            return []
        except TypeError as tpe:
            self.logger.warning(tpe)
            return []
        except AssertionError as ase:  # if blank page
            self.logger.warning(ase)
            return []
        except LookupError as lke:  # unknown encoding
            self.logger.warning(lke)
            return []
        except InvalidSchema as ate:
            self.logger.warning(ate)
            return []
        except XMLSyntaxError as xml:
            self.logger.warning(xml)
            return []
        except UnicodeDecodeError as ude:
            self.logger.warning(ude)
            return []
        except UnicodeError as ue:
            self.logger.warning(ue)
            return []
        except MissingSchema as ms:
            self.logger.warning(ms)
            return []
        except ChunkedEncodingError as cee:
            self.logger.warning(cee)
            return []
        except SSLError as ssl:
            self.logger.warning(ssl)
            return []
        except RecursionError as e:
            self.logger.warning(e)
            return []
        except ValueError as ve:
            self.logger.warning(ve)
            return []
        except Exception as e:
            self.logger.error(traceback.format_exc())
            raise e

    return inner
