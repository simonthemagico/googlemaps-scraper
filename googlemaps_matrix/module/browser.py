# -*- coding: utf-8 -*-
from monseigneur.monseigneur.core.browser import URL, PagesBrowser
from monseigneur.monseigneur.core.browser.exceptions import ServerError
from monseigneur.monseigneur.core.tools.decorators import retry
from googlemaps_matrix.module.exceptions import IncompletePageError, PageInaccessible, WrongInput
from googlemaps_matrix.results.models import Result
from googlemaps_matrix.module.contact_browser import ContactBrowser
from .pages import ListingPage, ListingHtmlPage, DetailPage, ConsentPage, ImagesPage
from requests.exceptions import ProxyError, ConnectionError, ChunkedEncodingError
from urllib.parse import urlparse, unquote, quote
from datetime import datetime, timedelta
import time
import random
import re
import string
import json
import math


__all__ = ["GoogleMapsBrowser"]

EARTH_RADIUS_IN_METERS = 6371010
TILE_SIZE = 256
SCREEN_PIXEL_HEIGHT = 768
RADIUS_X_PIXEL_HEIGHT = 27.3611 * EARTH_RADIUS_IN_METERS * SCREEN_PIXEL_HEIGHT
PER_PAGE = 200


class GoogleMapsBrowser(PagesBrowser):
    BASEURL = "https://www.google.com/"

    listing_page = URL(r"/search\?(.*)", ListingPage)
    listing_html_page = URL(r"/maps/search(.*)", ListingHtmlPage)
    detail_page = URL(r"/maps/preview(.*)", DetailPage)
    single_page = URL(r"/maps/place(.*)", DetailPage)
    consent_page = URL(
        r"https://consent.google.com/m(.+)",
        r"https://consent.google.fr/m(.+)",
        ConsentPage,
    )
    images_page = URL(r"/maps/rpc/photo/listentityphotos(.*)", ImagesPage)
    language = "en"
    image_id = None

    def __init__(self, is_superuser=False, *args, **kwargs):
        super(GoogleMapsBrowser, self).__init__(*args, **kwargs)
        self.contact_collector = ContactBrowser(*args, **kwargs)
        self.set_random_proxy()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36'
        })
        self.term = ""
        self.language = "en"
        self.country = "US"
        self.is_superuser = is_superuser
        self.objs = []
        self.map_dates = []

    def set_random_proxy(self):
        self.session.cookies.set("CONSENT", "YES+cb.20230123-17-p1.en+FX+715")

    def give_consent(self, url):
        assert self.consent_page.is_here()
        forms = self.page.get_forms()
        form = forms[0]
        self.location(form['action'], data=form['data'], method=form['method'])

    def get_app_initialization(self, url):
        self.location(url)
        if self.consent_page.is_here():
            self.give_consent(url)
        if not self.listing_html_page.is_here():
            return None, None
        return self.page.get_app_initialization()

    def extract_params(self, url):
        params = self._extract_from_url(url) or self._fallback_extract(url)
        if not params:
            raise WrongInput
        cat, lat, lng, zoom = params
        self.term = cat
        return cat, lat, lng, zoom

    def _extract_from_url(self, url):
        patterns = [
            r"/maps/(?:search|place)/(?P<cat>[^/]+)/@(?P<lat>[-.\d]+),(?P<lng>[\d.-]+),(?P<zoom>\d+)z",
            r"/maps/(?:search|place)/(?P<cat>[^/]+)/@(?P<lat>[-.\d]+),(?P<lng>[\d.-]+)"
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                params = match.groupdict()
                return params['cat'], params['lat'], params['lng'], params.get('zoom', '8')

    def _fallback_extract(self, url):
        lat, lng = self.get_app_initialization(url)
        if lat and lng:
            cat_match = re.search(r"/maps/search/(?P<cat>[^/]+)", url)
            if cat_match:
                cat = cat_match.group('cat')
                return cat, lat, lng, '8'
            else:
                self.logger.warning(f"cat not found in url: {url}")

    def zoom_to_alt(self, lat, zoom):
        lat = float(lat)
        zoom = int(zoom)
        try:
            return str(
                (RADIUS_X_PIXEL_HEIGHT * math.cos((lat * math.pi) / 180))
                / ((2**zoom) * TILE_SIZE)
            )
        except (ZeroDivisionError, OverflowError):
            raise WrongInput

    def alt_to_zoom(self, altitude, latitude):
        altitude = float(altitude)
        latitude = float(latitude)
        return round(
            math.log(
                1
                / math.tan(math.pi / 180 * 13.1 / 2)
                * (SCREEN_PIXEL_HEIGHT / 2)
                * 2
                * math.pi
                / (
                    TILE_SIZE
                    * altitude
                    / (EARTH_RADIUS_IN_METERS * math.cos(math.pi / 180 * latitude))
                )
            )
            / 0.693147180559945
        )

    def gen_random(
        self,
        length: int = 43,
        chars: str = string.ascii_uppercase + string.ascii_lowercase + string.digits,
        extra_chars: str = "",
    ):
        return "".join(random.choice(chars + extra_chars) for _ in range(length))

    def get_contacts(self, result):
        return self.contact_collector.get_contacts(result)

    def single_url_param(self, url):
        params = {
            'name': '',
            'lat': '',
            'lng': '',
            'zoom': '',
            'zero_x': '',
            'g_url': '',
            'place_id': ''
        }
        parsed_url = urlparse(unquote(url))
        path_parts = parsed_url.path.split('/')
        if len(path_parts) > 3:
            params['name'] = unquote(path_parts[3])
        combined_path = f"{parsed_url.path}/{parsed_url.fragment}"
        regex = re.compile(
            r'@(?P<lat>-?\d+\.\d+),(?P<lng>-?\d+\.\d+),(?P<zoom>\d+)z|'
            r'!3d(?P<lat2>-?\d+\.\d+)!4d(?P<lng2>-?\d+\.\d+)|'
            r'0x(?P<zx1>[0-9a-f]+):0x(?P<zx2>[0-9a-f]+)|'
            r'19s(?P<place_id>[A-Za-z0-9_-]+)|'
            r'/(?P<g_url>[a-z]/[^!]+)'
        )

        for match in regex.finditer(combined_path):
            match_dict = match.groupdict()
            params['lat'] = match_dict['lat'] or match_dict['lat2'] or params['lat']
            params['lng'] = match_dict['lng'] or match_dict['lng2'] or params['lng']
            params['zoom'] = match_dict['zoom'] or params['zoom']
            params['zero_x'] = f"0x{match_dict['zx1']}:0x{match_dict['zx2']}" if match_dict['zx1'] else params['zero_x']
            params['place_id'] = match_dict['place_id'] or params['place_id']
            params['g_url'] = match_dict['g_url'] or params['g_url']

        return params

    def get_search_term_from_url(self, url):
        match = re.search(r"/maps/search/([^/@?]+)", url)
        if match:
            return match.group(1)
        return None

    @retry(ProxyError, tries=4, delay=2, backoff=0)
    @retry(ConnectionError, tries=4, delay=2, backoff=0)
    @retry(IncompletePageError, tries=3, delay=2, backoff=0)
    def go_results(self, url, language, country, page, ratings=None):
        rating_id = {
            "4.5+": "44857",
            "4.0+": "8294",
            "3.5+": "44856",
            "3.0+": "8296",
            "2.5+": "44855",
            "2.0+": "8298"
        }.get(ratings)
        self.image_id = None
        self.language = language
        self.country = country
        self.objs = []
        if '/place/' in url:
            single_params = self.single_url_param(url)
            result_obj = Result()
            if all(single_params[key] for key in ['lat', 'lng', 'zero_x', 'name']):
                result_obj.name = single_params['name']
                result_obj.lat = single_params['lat']
                result_obj.lng = single_params['lng']
                result_obj.zero_x = single_params['zero_x']
                # result_obj.place_id = single_params['place_id']
                result_obj.url = url
                self.total_pages = 1
                self.go_result(result_obj)
            elif single_params['zero_x']:
                self.location(url)
            else:
                raise WrongInput
            if self.consent_page.is_here():
                self.give_consent(url)
            assert self.detail_page.is_here()
            self.objs = [self.page.get_result(result_obj)]
        else:
            if 'google.com/search' in url:
                raise WrongInput
            search_term, lat, lng, zoom = self.extract_params(url)
            try:
                alt = self.zoom_to_alt(lat, zoom)
            except ValueError:
                raise WrongInput
            for page in range(1, 3 + 1):
                ratings = f'!4m1!2i{rating_id}' if rating_id else ''
                ratings_data = '!50m31!1m27!1m5!1u2!2m3!2m2!2m1!2e9' if rating_id else '!50m25!1m21'
                random_23 = self.gen_random(23)
                ratings_extra = f'!22m5!1s{random_23}:94!2z{self.gen_random(60)}' if rating_id else f'!22m2!1s{random_23}'
                url = "https://www.google.com/search?tbm=map&gl={country}&authuser=0&hl={lang}&pb=!4m8!1m3!1d{alt}!2d{lng}!3d{lat}!3m2!1i1024!2i768!4f13.1!7i{per_page}!8i{start}!10b1!12m37!1m2!18b1!30b1!2m3!5m1!6e2!20e3!6m17!4b1!49b1!63m0!66b1!73m0!74i150000!75b1!85b1!89b1!91b1!110m0!114b1!149b1!166f1.35!183m0!196b1!201b1!10b1!12b1!13b1!14b1!16b1!17m1!3e1!20m3!5e2!6b1!14b1!94b1!19m4!2m3!1i360!2i120!4i8!20m57!2m2!1i203!2i100!3m2!2i4!5b1!6m6!1m2!1i86!2i86!1m2!1i408!2i240!7m42!1m3!1e1!2b0!3e3!1m3!1e2!2b1!3e2!1m3!1e2!2b0!3e3!1m3!1e8!2b0!3e3!1m3!1e10!2b0!3e3!1m3!1e10!2b1!3e2!1m3!1e9!2b1!3e2!1m3!1e10!2b0!3e3!1m3!1e10!2b1!3e2!1m3!1e10!2b0!3e4!2b1!4b1!9b0{ratings_extra}{ratings}!7e81!24m103!1m28!13m9!2b1!3b1!4b1!6i1!8b1!9b1!14b1!20b1!25b1!18m17!3b1!4b1!5b1!6b1!13b1!14b1!17b1!21b1!22b1!25b1!27m1!1b0!28b0!31b0!32b0!33m1!1b0!5m5!2b1!5b1!6b1!7b1!10b1!10m1!8e3!11m1!3e1!14m1!3b1!17b1!20m2!1e3!1e6!24b1!25b1!26b1!29b1!30m1!2b1!36b1!39m3!2m2!2i1!3i1!43b1!52b1!54m1!1b1!55b1!56m1!1b1!65m5!3m4!1m3!1m2!1i224!2i298!71b1!72m19!1m5!1b1!2b1!3b1!5b1!7b1!4b1!8m10!1m6!4m1!1e1!4m1!1e3!4m1!1e4!3sother_user_reviews!6m1!1e1!9b1!89b1!103b1!113b1!114m3!1b1!2m1!1b1!117b1!122m1!1b1!125b0!126b1!127b1!26m4!2m3!1i80!2i92!4i8!30m28!1m6!1m2!1i0!2i0!2m2!1i530!2i768!1m6!1m2!1i974!2i0!2m2!1i1024!2i768!1m6!1m2!1i0!2i0!2m2!1i1024!2i20!1m6!1m2!1i0!2i748!2m2!1i1024!2i768!34m19!2b1!3b1!4b1!6b1!7b1!8m6!1b1!3b1!4b1!5b1!6b1!7b1!9b1!12b1!14b1!20b1!23b1!25b1!26b1!37m1!1e81!42b1!46m1!1e9!47m0!49m9!3b1!6m2!1b1!2b1!7m2!1e3!2b1!8b1!9b1{ratings_data}!2m7!1u3!4sOpen now!5e1!9s{random_23}!10m2!3m1!1e1!2m7!1u2!4sTop rated!5e1!9s{random_23}!10m2!2m1!1e1!3m1!1u2!3m1!1u3!4BIAE!2e2!3m1!3b1!59BQ2dBd0Fn!61b1!67m3!7b1!10b1!14b0!69i701&q={search_term}&tch=1&ech=1&psi={random_20}.{timestamp}.1".format(
                    country=country,
                    lang=language,
                    per_page=PER_PAGE,
                    alt=alt,
                    lat=lat,
                    lng=lng,
                    start=((page - 1) * PER_PAGE),
                    random_23=self.gen_random(40),
                    random_20=self.gen_random(length=20),
                    ratings=ratings,
                    ratings_extra=ratings_extra,
                    ratings_data=ratings_data,
                    search_term=search_term,
                    timestamp=int(time.time() * 1000),
                )

                try:
                    self.location(url)
                except ServerError:
                    raise MatrixException(PageInaccessible)
                assert self.listing_page.is_here()
                self.map_dates = self.page.get_dates()
                self.page.search_term = search_term
                self.objs.extend(list(self.page.iter_results()))

                if not self.page.has_next_page() or len(self.objs) >= 200:
                    break

    def get_total_pages(self):
        return 1

    def get_total_results(self):
        return len(self.objs)

    def iter_results(self):
        for result_obj in self.objs:
            yield result_obj

    @retry(ConnectionError, tries=4, delay=2, backoff=0)
    @retry(IncompletePageError, tries=3, delay=2, backoff=0)
    @retry(ChunkedEncodingError, tries=3, delay=2, backoff=0)
    def go_result(self, result):
        term = quote(self.term).replace("%", "*")[:50]
        if not result.name:
            name = self.get_search_term_from_url(result.url)
        else:
            name = quote(result.name)
        lat = result.lat
        lng = result.lng
        lang = self.language
        country = self.country
        zero_x = result.zero_x
        if zero_x:
            url = "https://www.google.com/maps/preview/place?authuser=0&gl={country}&hl={lang}&pb=!1m14!1s{zero_x}!3m12!1m3!1d19906.219016901206!2d{lat}!3d{lng}!2m3!1f0!2f0!3f0!3m2!1i696!2i728!4f13.1!6s{term}!12m4!2m3!1i360!2i120!4i8!13m57!2m2!1i203!2i100!3m2!2i4!5b1!6m6!1m2!1i86!2i86!1m2!1i408!2i240!7m42!1m3!1e1!2b0!3e3!1m3!1e2!2b1!3e2!1m3!1e2!2b0!3e3!1m3!1e8!2b0!3e3!1m3!1e10!2b0!3e3!1m3!1e10!2b1!3e2!1m3!1e9!2b1!3e2!1m3!1e10!2b0!3e3!1m3!1e10!2b1!3e2!1m3!1e10!2b0!3e4!2b1!4b1!9b0!14m2!1skF08YoqTIOzYz7sPivKUmAc!7e81!15m70!1m22!4e2!13m8!2b1!3b1!4b1!6i1!8b1!9b1!14b1!20b1!18m11!3b1!4b1!5b1!6b1!9b1!12b1!13b1!14b1!15b1!17b1!20b1!2b1!5m5!2b1!3b1!5b1!6b1!7b1!10m1!8e3!14m1!3b1!17b1!20m2!1e3!1e6!24b1!25b1!26b1!29b1!30m1!2b1!36b1!39m3!2m2!2i1!3i1!43b1!52b1!54m1!1b1!55b1!56m2!1b1!3b1!65m5!3m4!1m3!1m2!1i224!2i298!71b1!72m4!1m2!3b1!5b1!4b1!89b1!21m0!22m1!1e81!29m0!30m1!3b1!34m2!7b1!10b1!37i595!38sCixSZXN0YXVyYW50IGRlIHNww6ljaWFsaXTDqXMgYWxzYWNpZW5uZXMgbG5rYVouIixyZXN0YXVyYW50IGRlIHNww6ljaWFsaXTDqXMgYWxzYWNpZW5uZXMgbG5rYZIBEWFsc2FjZV9yZXN0YXVyYW50mgEkQ2hkRFNVaE5NRzluUzBWSlEwRm5TVVJIZGxCRWJuUlJSUkFC&q={name}".format(
                    zero_x=zero_x,
                    lat=lat,
                    lng=lng,
                    term=term,
                    lang=lang,
                    country=country,
                    name=name,
                )
        else:
            if len(self.map_dates) > 0:
                from_ = self.map_dates[0]
                to_ = self.map_dates[1]
            else:
                from_ = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
                to_ = (datetime.now() + timedelta(days=8)).strftime("%Y-%m-%d")
            g_url = re.search(r"/g/([^!]+)", unquote(result.url)).group(1)
            url = "https://www.google.com/maps/preview/place?authuser=0&gl={country}&hl={lang}&pb=!1m20!3m12!1m3!1d13800.971507202541!2d4.828811168670659!3d45.76338958740234!2m3!1f0!2f0!3f0!3m2!1i720!2i476!4f13.1!4m2!3d{lat}!4d{lng}!15m3!1m1!4s%2Fg%2F{g_url}!2BQ0FF!6s{term}!12m4!2m3!1i360!2i120!4i8!13m57!2m2!1i203!2i100!3m2!2i4!5b1!6m6!1m2!1i86!2i86!1m2!1i408!2i240!7m42!1m3!1e1!2b0!3e3!1m3!1e2!2b1!3e2!1m3!1e2!2b0!3e3!1m3!1e8!2b0!3e3!1m3!1e10!2b0!3e3!1m3!1e10!2b1!3e2!1m3!1e9!2b1!3e2!1m3!1e10!2b0!3e3!1m3!1e10!2b1!3e2!1m3!1e10!2b0!3e4!2b1!4b1!9b0!14m2!1sphT4Zf_KG7qJ7NYPzeeNwAQ!7e81!15m112!1m44!4e1!13m9!2b1!3b1!4b1!6i1!8b1!9b1!14b1!20b1!25b1!15m1!1i2!17m10!1m3!1i{from_year}!2i{from_month}!3i{from_day}!2m3!1i{to_year}!2i{to_month}!3i{to_day}!3i1!6i1!18m19!3b1!4b1!5b1!6b1!9b1!12b1!13b1!14b1!15b1!17b1!20b1!21b1!22b1!25b1!27m1!1b0!28b0!30b0!32b0!10m1!8e3!11m1!3e1!14m1!3b1!17b1!20m2!1e3!1e6!24b1!25b1!26b1!29b1!30m1!2b1!36b1!39m3!2m2!2i1!3i1!43b1!52b1!54m1!1b1!55b1!56m2!1b1!3b1!65m5!3m4!1m3!1m2!1i224!2i298!71b1!72m19!1m5!1b1!2b1!3b1!5b1!7b1!4b1!8m10!1m6!4m1!1e1!4m1!1e3!4m1!1e4!3sother_user_reviews!6m1!1e1!9b1!89b1!103b1!113b1!114m3!1b1!2m1!1b1!117b1!122m1!1b1!125b0!21m0!22m2!1e81!8e4!29m0!30m6!3b1!4b1!6m1!2b1!7m1!2b1!34m2!7b1!10b1!37i684!39s{query_name}!40b0!41b1&q={name}".format(
                    lang=lang,
                    country=country,
                    lat=lat,
                    lng=lng,
                    term=term,
                    name=name,
                    g_url=g_url,
                    from_year=from_.split("-")[0],
                    from_month=from_.split("-")[1],
                    from_day=from_.split("-")[2],
                    to_year=to_.split("-")[0],
                    to_month=to_.split("-")[1],
                    to_day=to_.split("-")[2],
                    query_name=name.replace("%20", "+").replace('%21', '').strip('+')
                )
        if self.detail_page.is_here() and url == self.response.url:
            return True
        try:
            self.location(url)
        except ServerError:
            return False
        except json.decoder.JSONDecodeError:
            raise IncompletePageError(str(url))
        assert self.detail_page.is_here()
        self.image_id = self.page.image_id()
        return True

    def get_result(self, obj):
        assert self.detail_page.is_here()
        return self.page.get_result(obj=obj)

    def get_image_id(self, obj):
        if self.image_id:
            return self.image_id
        if not self.detail_page.is_here():
            self.go_result(obj)
        return self.page.image_id()

    @retry(ServerError, tries=3, delay=5, backoff=0)
    def fill_images(self, obj, cursor=None, img_id=None):
        """Get a single page of images for the given object"""
        url = "https://www.google.com/maps/rpc/photo/listentityphotos?authuser=0&hl={lang}&gl={country}&pb=!1e2!3m3!1s{zero_x}!9e0!11s{img_id}!5m5{is_first}!2m2!1i203!2i100!3m{index}!2i20{cursor}!5b1!7m42!1m3!1e1!2b0!3e3!1m3!1e2!2b1!3e2!1m3!1e2!2b0!3e3!1m3!1e8!2b0!3e3!1m3!1e10!2b0!3e3!1m3!1e10!2b1!3e2!1m3!1e9!2b1!3e2!1m3!1e10!2b0!3e3!1m3!1e10!2b1!3e2!1m3!1e10!2b0!3e4!2b1!4b1!9b0!6m3!1s!7e81!15i16698!16m2!2b1!4e1"

        is_first = 1 if cursor else 0
        index = 3 if cursor else 2
        cursor_param = '!3s' + cursor if cursor else ''

        self.location(url.format(
            zero_x=obj.zero_x,
            img_id=img_id,
            cursor=cursor_param,
            is_first=is_first,
            index=index,
            lang=self.language,
            country=self.country
        ))

        assert self.images_page.is_here()
        next_cursor = self.page.get_cursor()
        images = self.page.get_images()

        return images, next_cursor
