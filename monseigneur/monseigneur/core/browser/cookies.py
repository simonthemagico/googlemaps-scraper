# -*- coding: utf-8 -*-

import requests.cookies
try:
    import cookielib
except ImportError:
    import http.cookiejar as cookielib


__all__ = ['MonseigneurCookieJar', 'BlockAllCookies']


class MonseigneurCookieJar(requests.cookies.RequestsCookieJar):
    @classmethod
    def from_cookiejar(klass, cj):
        """
        Create a MonseigneurCookieJar from another CookieJar instance.
        """
        return requests.cookies.merge_cookies(klass(), cj)

    def export(self, filename):
        """
        Export all cookies to a file, regardless of expiration, etc.
        """
        cj = requests.cookies.merge_cookies(cookielib.LWPCookieJar(), self)
        cj.save(filename, ignore_discard=True, ignore_expires=True)

    def copy(self):
        """Return an object copy of the cookie jar."""
        new_cj = type(self)()
        if hasattr(self, 'get_policy'):
            new_cj.set_policy(self.get_policy())
        else:
            new_cj.set_policy(self._policy)
        new_cj.update(self)
        return new_cj

    def delete(self, name, domain=None, path=None):
        # delete cookies with the given name, domain and path
        requests.cookies.remove_cookie_by_name(self, name, domain, path)


class BlockAllCookies(cookielib.CookiePolicy):
    return_ok = set_ok = domain_return_ok = path_return_ok = lambda self, *args, **kwargs: False
    netscape = True
    rfc2965 = hide_cookie2 = False
