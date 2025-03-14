__all__ = ['ConsentPageRedirectionError']


class ConsentPageRedirectionError(Exception):
    pass


class IncompletePageError(Exception):
    pass


class PageInaccessible(Exception):
    pass


class WrongInput(Exception):
    pass


class InvalidUrl(Exception):
    pass
