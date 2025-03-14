# -*- coding: utf-8 -*-
import json
import re
import tldextract
from .regexer import Regex
from urllib.parse import quote_plus
from json.decoder import JSONDecodeError
from monseigneur.monseigneur.core.browser.elements import ItemElement, ListElement, method
from monseigneur.monseigneur.core.browser.filters.standard import Field, CleanText
from monseigneur.monseigneur.core.browser.filters.json import Dict
from monseigneur.monseigneur.core.browser.pages import HTMLPage, JsonPage

from googlemaps_matrix.module.constants import COUNTRIES
from googlemaps_matrix.results.models import Result, Contact


countries_by_country_code = {
    value.upper(): key for key, value in COUNTRIES.items()
}


PER_PAGE = 200
NUMBER_DAYS = {
    0: 'sundays',
    1: 'mondays',
    2: 'tuesdays',
    3: 'wednesdays',
    4: 'thursdays',
    5: 'fridays',
    6: 'saturdays'
}

class ConsentPage(HTMLPage):

    def is_here(self):
        return '/consent.' in self.response.url or re.findall(r'action="https://consent\.(google|youtube)\.(.+)/save"', self.text)

    def get_forms(self):
        forms = self.doc.xpath('//form')
        forms_data = []
        for form in forms:
            form_data = {}
            form_data['action'] = form.get('action')
            form_data['method'] = form.get('method')
            inputs = form.xpath('.//input')
            form_data['data'] = {}
            for input in inputs:
                if not input.get('name'):
                    continue
                form_data['data'][input.get('name')] = input.get('value')
            forms_data.append(form_data)
        return forms_data


class ListingHtmlPage(HTMLPage):

    def get_app_initialization(self):
        # fetch window.APP_INITIALIZATION_STATE=[[[5419.997689298756,<floating_lng>,<floating_lat>]
        match = re.search(r'window.APP_INITIALIZATION_STATE=\[\[\[(.*?),(.*?),(.*?)\]', self.response.text)
        if not match:
            return None, None
        return [match.group(3), match.group(2)]


class ListingPage(JsonPage):

    def build_doc(self, content):
        # self.browser.content = content
        if content[-6:] == '/*""*/':
            content = json.loads(content[:-6])['d']
        content = content[5:]
        try:
            self.doc = json.loads(content)
        except JSONDecodeError:
            raise IncompletePageError
        self.browser.save_custom_response(content, ".json")
        return self.doc

    def get_dates(self):
        from_date = Dict('0/1/1/14/35/0', default='')(self.doc)
        till_date = Dict('0/1/1/14/35/0', default='')(self.doc)
        if from_date and till_date:
            return [from_date, till_date]
        return []

    def get_altitude(self):
        return Dict('1/0/0')(self.doc)

    def get_total_items(self):
        return len(self.doc.xpath('//a[contains(@href,"/maps/place")]'))

    def has_next_page(self):
        return not (len(Dict('0/1', default=[])(self.doc)) < PER_PAGE)

    @method
    class iter_results(ListElement):

        def find_elements(self):
            els = Dict('0/1', default=[])(self.page.doc)
            for el in els:
                if Dict('14/9/3', default=None)(el):
                    yield el[14]

        class get_result(ItemElement):
            klass = Result

            def obj_url(self):
                name = Field('name')(self) or " "
                lat = round(Field('lat')(self), 5)
                lng = round(Field('lng')(self), 5)
                zero_x = Field('zero_x')(self)
                raw_url = Dict('89', default=None)(self)
                preview_url = Dict('42', default=None)(self)
                place_id = Dict('78', default=None)(self)

                if place_id:
                    url = f"https://www.google.com/maps/place/{quote_plus(name.replace(' ', '+'))}/data=!4m6!3m5!1s{zero_x}!8m2!3d{lat}!4d{lng}!19s{place_id}?authuser=0&hl=en&rclk=1"
                elif raw_url:
                    g_url = quote_plus(raw_url)
                    if not zero_x:
                        url = f"https://www.google.com/maps/place/{quote_plus(name.replace(' ', '+'))}/@{lat},{lng}/data=!4m9!3m8!5m2!4m1!1i2!8m2!3d{lng}!4d3.1589799!16s{g_url}!17BQ0FF"
                    else:
                        url = f"https://www.google.com/maps/place/{quote_plus(name.replace(' ', '+'))}/@{lat},{lng}/data=!3m1!4b1!4m6!3m5!1s{zero_x}!8m2!3d{lat}!4d{lng}!16s{g_url}"
                else:
                    url = preview_url
                if place_id and len(url) > 1000:
                    url = f'https://www.google.com/maps/place/?q=place_id:{place_id}'
                return url

            def obj_zero_x(self):
                zero_x = Dict('10')(self)
                return zero_x

            def obj_cid(self):
                zero_x = Field('zero_x')(self)
                if not zero_x:
                    return
                zero_x = zero_x.split(':')[-1]
                return str(int(zero_x, 16))

            def obj_name(self):
                return Dict('11')(self)

            def obj_lng(self):
                return Dict('9/3')(self)

            def obj_lat(self):
                return Dict('9/2')(self)

            def obj_score(self):
                return Dict('4/7', default=None)(self)

            def obj_ratings(self):
                return Dict('4/8', default=None)(self)

            def obj_address(self):
                return Dict('39', default=None)(self)

            def obj_zip_code(self):
                return Dict('183/1/4', default=None)(self)

            def obj_country(self):
                iso = Dict("243", default=None)(self)
                if not iso:
                    return
                return countries_by_country_code.get(iso.upper())

            def obj_country_code(self):
                return Dict("243", default=None)(self)

            def obj_city(self):
                return Dict('183/1/3', default=None)(self)

            def obj_category(self):
                category = ", ".join(Dict('13', default=[])(self) or [])
                return category

            def obj_special_category(self):
                special_category = Dict('64/3', default=[])(self)
                if special_category:
                    if type(special_category) is list:
                        special_category = ", ".join([CleanText().filter(el) for el in special_category])
                    else:
                        special_category = CleanText().filter(special_category)
                    return special_category
                return None

            def obj_phone(self):
                return Dict('178/0/3', default=None)(self)

            def obj_description(self):
                return Dict('32/1/1', default=None)(self)

            def obj_website(self):
                website = Dict('7/0', default=None)(self)
                if website and website.startswith('/url'):
                    website = re.findall(r'q=(.*?)&', website)
                    return None if not website else website[0]
                return website

            def obj_main_image_url(self):
                v = Dict('51/0/1/0', default=None)(self)
                if v and not v.startswith('http'):
                    return "https://lh5.googleusercontent.com/p/{}".format(v)
                return v

            def obj_price(self):
                return Dict('4/10', default=None)(self)

            def obj_images_count(self):
                return Dict('37/1', default=0)(self) or 0

            def obj_opening_hours(self):
                opening_hours = []
                v = Dict('34/1', default=[])(self) or []
                for e in v:
                    opening_hours += [Dict('0')(e) + " " + " ".join(Dict('1')(e))]
                return ", ".join(opening_hours)

            def obj_is_temporarily_closed(self):
                closed = Dict('160/0', default=None)(self)
                return bool(closed)

            def obj_is_permanently_closed(self):
                closed = Dict('23', default=None)(self)
                return bool(closed)

            def obj_has_owner(self):
                v = Dict('49/1', default='')(self).lower() == 'claim this business'
                return not bool(v)

            def obj_booking_link(self):
                return Dict('75/0/0/2/0/1/2/0', default=None)(self)

            def obj_popular_times(self):
                popular_times = []
                for i, v in enumerate(Dict('84/0', default=[])(self)):
                    day = NUMBER_DAYS[i]
                    e = Dict('1', default=None)(v)
                    if not e:
                        popular_times.append('{}: closed'.format(day))
                        continue
                    n = []
                    for k in e:
                        _time = Dict('4')(k)
                        _value = Dict('1')(k)
                        n += ["{} {}".format(_time, _value)]
                    popular_times += [day + ": " + ", ".join(n)]
                return ', '.join(popular_times)

            def obj_menu(self):
                menu = Dict('38/0', default=None)(self)
                if menu and 'search?q=' in menu:
                    menu = menu.split('&')[0]
                if menu and menu.startswith('/url'):
                    menu = re.findall(r'q=(.*?)&', menu)
                    return None if not menu else menu[0]
                return menu


class DetailPage(JsonPage):

    def build_doc(self, text):
        if text.startswith('<!DOCTYPE html>'):
            doc = re.search(r'window\.APP_INITIALIZATION_STATE=(.*?);window\.APP_FLAGS', text)
            doc = json.loads(doc.group(1))
            text = doc[3][6]
        doc = json.loads(text[5:])[6]
        return doc

    def image_id(self):
        img = Dict('89', default=None)(self.doc)
        return img

    @method
    class get_result(ItemElement):
        klass = Result

        def obj_name(self):
            return self.obj.name or Dict('11')(self)

        def obj_lat(self):
            return float(self.obj.lat or Dict('9/2')(self))

        def obj_lng(self):
            return float(self.obj.lng or Dict('9/3')(self))

        def obj_zero_x(self):
            return self.obj.zero_x or Dict('10')(self)

        def obj_url(self):
            if self.obj.url:
                return self.obj.url
            g_url = Dict('89', default=None)(self)
            preview_url = Dict('42', default=None)(self)
            place_id = Dict('78', default=None)(self)
            lat = round(Field('lat')(self), 5)
            lng = round(Field('lng')(self), 5)
            zero_x = Field('zero_x')(self)
            name = Field('name')(self)

            if place_id:
                url = f"https://www.google.com/maps/place/{quote_plus(name.replace(' ', '+'))}/data=!4m6!3m5!1s{zero_x}!8m2!3d{lat}!4d{lng}!19s{place_id}?authuser=0&hl=en&rclk=1"
            elif g_url:
                g_url = quote_plus(g_url)
                if not zero_x:
                    url = f"https://www.google.com/maps/place/{quote_plus(name.replace(' ', '+'))}/@{lat},{lng}/data=!4m9!3m8!5m2!4m1!1i2!8m2!3d{lng}!4d3.1589799!16s{g_url}!17BQ0FF"
                else:
                    url = f"https://www.google.com/maps/place/{quote_plus(name.replace(' ', '+'))}/@{lat},{lng}/data=!3m1!4b1!4m6!3m5!1s{zero_x}!8m2!3d{lat}!4d{lng}!16s{g_url}"
            else:
                url = preview_url
            if place_id and len(url) > 1000:
                url = f'https://www.google.com/maps/place/?q=place_id:{place_id}'
            return url

        def obj_website(self):
            website = self.obj.website or Dict('7/0', default=None)(self)
            if website and website.startswith('/url'):
                website = re.findall(r'q=(.*?)&', website)
                return None if not website else website[0]
            return website

        def obj_country(self):
            if self.obj.country_name:
                return self.obj.country_name
            iso = self.obj.country_code or Dict("243", default=None)(self)
            if iso:
                return countries_by_country_code.get(iso.upper())
            return None

        def obj_country_code(self):
            return self.obj.country_code or Dict("243", default=None)(self)

        def obj_address(self):
            return self.obj.address or Dict('39', default=None)(self)

        def obj_zip_code(self):
            return self.obj.zip_code or Dict('183/1/4', default=None)(self)

        def obj_city(self):
            return self.obj.city or Dict('183/1/3', default=None)(self)

        def obj_phone(self):
            return self.obj.phone or Dict('178/0/3', default=None)(self)

        def obj_score(self):
            return self.obj.score or Dict('4/7', default=None)(self)

        def obj_ratings(self):
            return self.obj.ratings or Dict('4/8', default=None)(self)

        def obj_price(self):
            return self.obj.price or Dict('4/10', default=None)(self)

        def obj_opening_hours(self):
            if self.obj.opening_hours:
                return self.obj.opening_hours
            opening_hours = []
            v = Dict('34/1', default=[])(self) or []
            for e in v:
                opening_hours += [Dict('0')(e) + " " + " ".join(Dict('1')(e))]
            return ", ".join(opening_hours)

        def obj_booking_link(self):
            return self.obj.booking_link or Dict('75/0/0/2/0/1/2/0', default=None)(self)

        def obj_menu(self):
            menu = Dict('38/0', default=None)(self)
            if menu and 'search?q=' in menu:
                menu = menu.split('&')[0]
            if menu and menu.startswith('/url'):
                menu = re.findall(r'q=(.*?)&', menu)
                return None if not menu else menu[0]
            return menu

        def obj_poi(self):
            poi = []
            for v in Dict('100/1', default=[])(self):
                for e in Dict('2', default=[])(v):
                    if not Dict('3')(e):
                        poi.append(Dict('1')(e))
            return ", ".join(poi)

        def obj_description(self):
            return self.obj.description or Dict('32/1/1', default=None)(self)

        def obj_plus_code(self):
            return Dict('183/2/2/0', default=None)(self)

        def obj_last_opening_hours_updated_at(self):
            return Dict('203/5/0', default=None)(self)

        def obj_health(self):
            for v in Dict('100/1', default=[])(self):
                if v[0] == 'health_and_safety':
                    return True
            return False

        def obj_popular_times(self):
            popular_times = []
            for i, v in enumerate(Dict('84/0', default=[])(self)):
                day = NUMBER_DAYS[i]
                e = Dict('1', default=None)(v)
                if not e:
                    popular_times.append('{}: closed'.format(day))
                    continue
                n = []
                for k in e:
                    _time = Dict('4')(k)
                    _value = Dict('1')(k)
                    n += ["{} {}".format(_time, _value)]
                popular_times += [day + ": " + ", ".join(n)]
            return ', '.join(popular_times)

        def obj_images_count(self):
            return Dict('37/1', default=0)(self) or 0

        def obj_is_temporarily_closed(self):
            status_obj = Dict('96/5/-1/3', default=None)(self)
            if status_obj is not None and 'permanently closed' in status_obj:
                return True
            return False

        def obj_is_permanently_closed(self):
            status_obj = Dict('96/5/-1/3', default=None)(self)
            if status_obj is not None and 'temporarily closed' in status_obj:
                return True
            return False

        def obj_has_owner(self):
            v = Dict('49/1', default='')(self).lower() == 'claim this business'
            return not bool(v)

        def obj_about(self):
            about = {}
            text_about = Dict('32', default=None)(self)
            if text_about:
                about['about_description'] = ' '.join(self.extract_text(text_about))

            feature_section = Dict('100/1', default=None)(self)
            if feature_section:
                for feature_item in feature_section:
                    feature_items = []
                    feature_key = Dict('0')(feature_item)
                    for feature_value in Dict('2')(feature_item):
                        feature_items.append(Dict('1')(feature_value))
                    about[feature_key] = feature_items

            amenities = Dict('64/2', default=None)(self) or Dict('35/32/0/0/1', default=None)(self)
            if amenities:
                amenities_list = [amenity[2] for amenity in amenities if amenity[3] == 1]
                about['amenities'] = ', '.join(amenities_list)

            return json.dumps(about)

        def extract_text(self, text) -> list:
            text_list = []
            if isinstance(text, str):
                text_list.append(text)
            elif isinstance(text, list):
                for item in text:
                    if isinstance(item, int) or item is None:
                        continue
                    if isinstance(item, str) and re.search(r'http', item):
                        continue
                    if isinstance(item, list):
                        text_list.extend(self.extract_text(item))
                    elif isinstance(item, str):
                        text_list.append(item)
            return text_list

class PersoPage(HTMLPage):

    EXCLUDED_EXTENSIONS = ['.jpg', '.png', '.gif', '.mp3', '.jpeg', 'sentry.wixpress', 'sentry.entities', '.jtv', '.webp', '.pdf', '.svg']
    CONTACT_KEYWORDS = ['contact', 'about', 'kontakt']
    PERSONAL_EMAIL_DOMAINS = [
        'gmail', 'wanadoo', 'outlook', 'hotmail', 'live', 'msn',
        'yahoo', 'icloud', 'protonmail', 'free.fr', 'aol', 'mail',
        'orange.fr', 'sfr.fr', 'yandex', 'gmx'
    ]

    def is_here(self):
        return True

    @property
    def domain(self):
        extracted = tldextract.extract(self.url)
        return '.'.join([extracted.domain, extracted.suffix])

    def get_contact_links(self):
        """Get contact and about page links from the website."""
        base_url = '/'.join(self.url.split('/')[:3])

        # Build XPath conditions for each keyword
        conditions = []
        for keyword in self.CONTACT_KEYWORDS:
            conditions.extend([
                f"contains(translate(@href, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{keyword}')",
                f"contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{keyword}')"
            ])

        xpath = f"//*[{' or '.join(conditions)}]/@href"
        links = self.doc.xpath(xpath)

        # Process and yield valid URLs
        seen_links = set()
        for link in links:
            if not link:  # Skip empty links
                continue

            if link.startswith('http'):
                clean_link = link
            else:
                clean_link = self.clean_link(link, base_url)

            # Skip invalid URLs and duplicates
            try:
                # Basic URL validation
                if not any(clean_link.startswith(prefix) for prefix in ['http://', 'https://']):
                    continue
                if clean_link not in seen_links:
                    seen_links.add(clean_link)
                    yield clean_link
            except Exception:
                continue

    def clean_link(self, link, base_url):
        """Clean and normalize relative links."""
        if link.startswith('//'):
            return f'https:{link}'
        elif link.startswith('/'):
            return f'{base_url}{link}'
        return f'{base_url}/{link}'

    def iter_mails(self):
        """Extract and normalize email addresses from the page content."""
        # Get both visible text and element attributes that might contain emails
        content = self.response.text
        # Also check common attributes that might contain emails
        for element in self.doc.xpath('//*[@href or @data-email or @content or @value]'):
            for attr in ['href', 'data-email', 'content', 'value']:
                attr_value = element.get(attr, '')
                if attr_value:
                    content += ' ' + attr_value

        # Handle common email obfuscation techniques
        content = (content.replace(r'\u0040', '@')
                        .replace('[at]', '@')
                        .replace('(at)', '@')
                        .replace(' at ', '@')
                        .replace('[dot]', '.')
                        .replace('(dot)', '.')
                        .replace(' dot ', '.'))

        # Find all potential email addresses
        seen_emails = set()
        for email in Regex.mail.findall(content):
            # Skip if contains excluded extensions
            if any(ext in email.lower() for ext in self.EXCLUDED_EXTENSIONS):
                continue

            # Clean and normalize the email
            email = self.normalize_email(email)

            if not email or email in seen_emails:
                continue

            seen_emails.add(email)
            contact_obj = Contact()
            contact_obj.value = email
            contact_obj.type = "MAIL"
            contact_obj.source = self.url

            # Determine if personal or professional
            domain = email.split('@')[-1].split('.')[0].lower()
            contact_obj.usage = ('PERSONAL' if any(personal_domain in domain
                                                 for personal_domain in self.PERSONAL_EMAIL_DOMAINS)
                               else 'PROFESSIONAL')

            yield contact_obj

    def normalize_email(self, email):
        """Clean and normalize email addresses."""
        try:
            # Remove common noise
            email = (email.strip()
                    .rstrip('.')  # Remove trailing dots
                    .rstrip(',')  # Remove trailing commas
                    .strip('"')   # Remove quotes
                    .strip("'")   # Remove single quotes
                    .replace(' ', ''))  # Remove spaces

            # Basic validation
            if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
                return None

            # Convert to lowercase
            email = email.lower()

            return email
        except Exception:
            return None

    def iter_phones(self):
        contact_list = []
        phones_table = list(set([el for el in Regex.phone.findall(self.response.text)]))

        if phones_table:
            for phone in phones_table:
                phone = self.normalize_phone(phone)
                if phone in [el.value for el in contact_list]:
                    pass
                else:
                    contact_obj = Contact()
                    contact_obj.value = phone
                    contact_obj.type = "PHONE"
                    if Regex.personal_phone.findall(contact_obj.value):
                        contact_obj.usage = 'PERSONAL'
                    else:
                        contact_obj.usage = 'PROFESSIONAL'
                    contact_obj.source = self.url
                    contact_list.append(contact_obj)
                    yield contact_obj

    def iter_social_media(self):
        social_media_list = []
        instagrams_table = list(set([el for el in Regex.instagram.findall(self.response.text)]))
        facebooks_table = list(set([el for el in Regex.facebook.findall(self.response.text)]))
        twitters_table = list(set([el for el in Regex.twitter.findall(self.response.text)]))
        linkedins_table = list(set([el for el in Regex.linkedin.findall(self.response.text)]))

        _domain = self.domain
        if 'facebook.com' in _domain:
            facebooks_table = []
        if 'intagram.com' in _domain:
            instagrams_table = []
        if 'twitter.com' in _domain:
            twitters_table = []
        if 'linkedin.com' in _domain:
            linkedins_table = []

        _tables = [instagrams_table, facebooks_table, twitters_table, linkedins_table]
        social_media_table = sum(_tables, [])
        for social_media in social_media_table:
            social_media = self.normalize_url(social_media)
            if social_media in [el.value for el in social_media_list]:
                continue
            else:
                social_media_obj = Contact()

                social_media_obj.value = social_media
                social_media_obj.type = "SOCIAL_MEDIA"

                if 'instagram' in social_media:
                    social_media_obj.usage = "INSTAGRAM"
                elif 'facebook' in social_media:
                    social_media_obj.usage = "FACEBOOK"
                elif 'twitter' in social_media:
                    social_media_obj.usage = "TWITTER"
                elif 'linkedin' in social_media:
                    social_media_obj.usage = "LINKEDIN"
                else:
                    continue

                social_media_obj.source = self.url
                yield social_media_obj
                social_media_list.append(social_media_obj)

    def normalize_url(self, url):
        url = url.lower()
        url = re.sub(r'/$', '', url)
        clean_routes = [
            '/posts',
            '/about',
            'groups',
            '/photos',
            '/videos',
            '?'
        ]
        for clean_route in clean_routes:
            url = url.split(clean_route)[0]
        return url

    def normalize_phone(self, phone):
        return re.sub(r'[\s(),.-]', '', phone)


class ImagesPage(JsonPage):
    def build_doc(self, content):
        self.doc = json.loads(content[5:])
        return self.doc

    def get_images(self):
        images = []
        try:
            images_ = Dict('0', default=[])(self.doc)
            for image in images_:
                link = Dict('0')(image)
                if link:
                    images.append(link.split('=')[0])
        except Exception:
            images_ = Dict('12/0', default=[])(self.doc)
            for image in images_:
                link = Dict('3/0/6/0')(image)
                if link:
                    images.append(link.split('=')[0])
        return images

    def get_cursor(self):
        return Dict('5')(self.doc)
