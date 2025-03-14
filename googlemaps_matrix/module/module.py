# -*- coding: utf-8 -*-

from deproto import Protobuf
from .browser import GoogleMapsBrowser
from monseigneur.monseigneur.core.tools.backend import Module
from monseigneur.monseigneur.core.browser.filters.json import Dict


__all__ = ['GoogleMapsModule']


class GoogleMapsModule(Module):

    NAME = 'googlemaps_matrix'
    MAINTAINER = u'Simon Rochwerg'
    EMAIL = 'simon.rochwerg.pro@gmail.com'
    VERSION = '1.0'
    DESCRIPTION = u'developer-by-leadstrooper.com'
    LICENSE = 'AGPL'
    BROWSER = GoogleMapsBrowser

    def get_rating(self, rating, _, data=None):
        NO_RATING_FILTER = 'Any rating'
        if not data:
            return rating
        data = data.split('?')[0]
        if rating and rating != NO_RATING_FILTER:
            return rating
        try:
            pb = Protobuf(data)
            code = pb.decode()
            json_data = code.to_json()
        except (ValueError, IndexError):
            return NO_RATING_FILTER
        ids = {
            0: NO_RATING_FILTER,
            1: '2.0+',
            7: '2.5+',
            2: '3.0+',
            8: '3.5+',
            3: '4.0+',
            9: '4.5+',
        }
        rid = Dict('3/1/4/3', default=0)(json_data)
        return ids[rid or 0]

    def go_results(self, url, language="en", country="US", page=1, ratings=None):
        ratings = self.get_rating(ratings, *url.split('/data=', 1))
        return self.browser.go_results(url, language, country, page, ratings)

    def iter_results(self):
        return self.browser.iter_results()

    def get_total_pages(self):
        return self.browser.get_total_pages()

    def get_total_results(self):
        return self.browser.get_total_results()

    def deduce_total_results(self):
        return self.browser.total_results

    def go_result(self, result):
        return self.browser.go_result(result)

    def get_result(self, obj):
        return self.browser.get_result(obj)

    def get_contacts(self, result):
        return self.browser.get_contacts(result)

    def fill_result_details(self, result):
        if self.go_result(result):
            return self.get_result(obj=result)
        return result

    def fill_images(self, result, cursor=None, img_id=None):
        return self.browser.fill_images(result, cursor, img_id)

    def get_image_id(self, obj):
        return self.browser.get_image_id(obj)
