# -*- coding: utf-8 -*-

__all__ = ['CacheMixin']


class CacheEntry(object):
    def __init__(self, response):
        self.response = response
        self.etag = response.headers.get('ETag')
        self.last_modified = response.headers.get('Last-Modified')

    def has_cache_key(self):
        return (self.etag or self.last_modified)

    def update_request(self, request):
        if self.last_modified:
            request.headers['If-Modified-Since'] = self.last_modified
        if self.etag:
            request.headers['If-None-Match'] = self.etag


class CacheMixin(object):
    """Mixin to inherit in a Browser"""

    def __init__(self, *args, **kwargs):
        super(CacheMixin, self).__init__(*args, **kwargs)

        self.cache = {}

        """Cache store object

        To limit the size of the cache, a :class:`core.tools.lrudict.LimitedLRUDict`
        instance can be used.
        """

        self.is_updatable = True

        """Whether the cache is updatable

        If `False`, once a request has been successfully executed, its response
        will always be returned.

        If `True`, the `ETag` and `Last-Modified` of the response will be
        stored along with the cache. When the request is re-executed, instead
        of simply returning the previous response, the server is queried to
        check if a newer version of the page exists.
        If a newer page exists, it is returned instead and overwrites the
        obsolete page in the cache.
        """

    def make_cache_key(self, request):
        """Make a key for the cache corresponding to the request."""

        body = getattr(request, 'body', None)
        headers = tuple(request.headers.values())
        return (request.method, request.url, body, headers)

    def open_with_cache(self, url, **kwargs):
        """Perform a request using the cache if possible."""
        request = self.build_request(url, **kwargs)

        key = self.make_cache_key(request)
        if key in self.cache:
            if not self.is_updatable:
                self.logger.debug('cache HIT for %r', request.url)
                return self.cache[key].response
            else:
                self.cache[key].update_request(request)

        response = super(CacheMixin, self).open(request, **kwargs)
        if response.status_code == 304:
            self.logger.debug('cache HIT for %r', request.url)
            return self.cache[key].response
        elif response.status_code == 200:
            entry = CacheEntry(response)
            if entry.has_cache_key():
                self.logger.debug('storing %r response in cache', request.url)
                self.cache[key] = entry

        self.logger.debug('cache MISS for %r', request.url)
        return response
