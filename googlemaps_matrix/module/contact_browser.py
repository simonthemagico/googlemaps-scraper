# -*- coding: utf-8 -*-
import urllib3
import tldextract
import os
import random
from urllib.parse import urlparse
from requests.adapters import HTTPAdapter
from monseigneur.monseigneur.core.browser import URL
from monseigneur.monseigneur.core.browser import PagesBrowser

from googlemaps_matrix.module.pages import PersoPage
from googlemaps_matrix.results.models import Contact
from googlemaps_matrix.module.decorators import location_error_handler


class TimeoutHTTPAdapter(HTTPAdapter):
    def __init__(self, *args, **kwargs):
        if "timeout" in kwargs:
            self.timeout = kwargs["timeout"]
            del kwargs["timeout"]
        super().__init__(*args, **kwargs)

    def send(self, request, **kwargs):
        timeout = kwargs.get("timeout")
        if timeout is None and hasattr(self, 'timeout'):
            kwargs["timeout"] = self.timeout
        return super().send(request, **kwargs)


__all__ = ['ContactBrowser']


class ContactBrowser(PagesBrowser):

    BASEURL = ''
    VERIFY = True
    DOWNGRADE = False
    MAX_RETRIES = 1
    TIMEOUT = 10

    perso_page = URL('(.*)', PersoPage)

    def __init__(self, *args, **kwargs):
        super(ContactBrowser, self).__init__(*args, **kwargs)
        self.session.mount('http://', TimeoutHTTPAdapter(timeout=self.TIMEOUT))
        self.session.mount('https://', TimeoutHTTPAdapter(timeout=self.TIMEOUT))

    @location_error_handler
    def get_contact_links(self, url):
        if not url:
            return []
        if url and url.strip('?# ') == '':
            self.logger.error('Invalid URL provided %s', url)
            return []
        if not url.startswith('http'):
            url = 'http://' + url
        contact_links = []
        self.logger.warning('Now going to: {!r}'.format(url))
        headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
            'cache-control': 'no-cache',
            'pragma': 'no-cache',
            'priority': 'u=0, i',
            'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'none',
            'sec-fetch-user': '?1',
            'upgrade-insecure-requests': '1',
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        }
        try:
            self.location(url, headers=headers, allow_redirects=True)
            assert self.perso_page.is_here()
            assert 'http' in self.page.url
            for contact_link in self.page.get_contact_links():
                contact_links.append(contact_link)
            return contact_links
        except urllib3.exceptions.LocationParseError:
            return []
        except ValueError as e:
            raise e

    @location_error_handler
    def get_contact_items(self, url, is_phone, is_mail, is_social_media):
        if not url:
            self.logger.error('Invalid URL provided %s', url)
            return []
        if url and url.strip('?# ') == '':
            self.logger.error('Invalid URL provided %s', url)
            return []
        contact_objects = []
        self.logger.warning('Now going to: {!r}'.format(url))

        headers = {}
        proxies = {}
        if 'facebook.com' in url:
            headers = {
                'authority': 'www.facebook.com',
                'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'accept-language': 'en-US,en;q=0.9',
                'cache-control': 'max-age=0',
                'dpr': '1',
                'sec-ch-prefers-color-scheme': 'light',
                'sec-ch-ua': '"Not.A/Brand";v="8", "Chromium";v="114", "Google Chrome";v="114"',
                'sec-ch-ua-full-version-list': '"Not.A/Brand";v="8.0.0.0", "Chromium";v="114.0.5735.133", "Google Chrome";v="114.0.5735.133"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-model': '""',
                'sec-ch-ua-platform': '"Linux"',
                'sec-ch-ua-platform-version': '"4.15.0"',
                'sec-fetch-dest': 'document',
                'sec-fetch-mode': 'navigate',
                'sec-fetch-site': 'none',
                'sec-fetch-user': '?1',
                'upgrade-insecure-requests': '1',
                'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
                'viewport-width': '1125',
            }
            parsed = urlparse(url)
            parsed = parsed._replace(netloc='www.facebook.com')
            url = parsed.geturl()
            proxies = self.set_random_proxy()
        try:

            headers = {
                'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'accept-language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
                'cache-control': 'no-cache',
                'pragma': 'no-cache',
                'priority': 'u=0, i',
                'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"macOS"',
                'sec-fetch-dest': 'document',
                'sec-fetch-mode': 'navigate',
                'sec-fetch-site': 'none',
                'sec-fetch-user': '?1',
                'upgrade-insecure-requests': '1',
                'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            }

            self.location(url, headers=headers, proxies=proxies, allow_redirects=True)
        except ValueError as e:
            if 'IPv6 address' in str(e):
                return contact_objects
            raise

        assert self.perso_page.is_here()

        if is_mail:
            for contact_object in self.page.iter_mails():
                contact_objects.append(contact_object)
        if is_phone:
            for contact_object in self.page.iter_phones():
                contact_objects.append(contact_object)
        if is_social_media:
            for contact_object in self.page.iter_social_media():
                contact_objects.append(contact_object)

        clean_contact_obj_list = []
        if contact_objects:
            for contact_obj in contact_objects:
                if contact_obj.value not in [el.value for el in clean_contact_obj_list]:
                    clean_contact_obj_list.append(contact_obj)

        return clean_contact_obj_list


    def set_random_proxy(self):
        home = os.path.expanduser("~")
        with open(f"{home}/mdev/matrix/modules/googlemaps_matrix/module/smartproxy.txt") as f:
            v = random.choice(f.read().splitlines())
            value_list = [value.strip() for value in v.split(":")]
            proxy_string = "http://{}:{}@{}:{}".format(value_list[2], value_list[3], value_list[0], value_list[1])
        assert proxy_string
        self.logger.warning(proxy_string)
        return {
            'http': proxy_string,
            'https': proxy_string,
        }

    def fix_result(self, result):
        socials = ['facebook', 'instagram', 'linkedin', 'twitter', 'email', 'phone']
        if not any([hasattr(result, social) for social in socials]) and not result.website:
            self.logger.error("No website provided")
            return result
        for social in socials:
            if not hasattr(result, social):
                continue
            value = getattr(result, social)
            if isinstance(value, str):
                setattr(result, social, value.split(', '))
            elif isinstance(value, list):
                setattr(result, social, value[:10])
            else:
                setattr(result, social, [])

        extracted = tldextract.extract(result.website or '')
        domain = '.'.join([extracted.domain, extracted.suffix])

        socials = ['facebook', 'instagram', 'linkedin', 'twitter', 'email', 'phone']
        for social in socials:
            if social in domain or (social == 'twitter' and 'x.com' in domain):
                if not hasattr(result, social):
                    continue
                if not getattr(result, social):
                    setattr(result, social, [])
                setattr(result, social, [result.website, *getattr(result, social, [])])
                result.website = None

        return result

    def get_contacts(self, result, is_phone=True, is_mail=True, is_social_media=True):
        result = self.fix_result(result)

        contact_links: list = self.get_contact_links(result.website) or []

        if result.website and result.website not in contact_links:
            contact_links.append(result.website)
        if hasattr(result, 'facebook') and result.facebook and len(result.facebook) == 1:
            contact_links.append(result.facebook[0])

        duplicates = []
        for contact_link in contact_links:
            try:
                contacts = self.get_contact_items(contact_link, is_phone, is_mail, is_social_media)
            except urllib3.exceptions.LocationParseError:
                continue
            for contact in contacts or []:
                if duplicates.count(contact.value) or not contact.value:
                    continue
                duplicates.append(contact.value)
                result = self.handle_contact(result, contact)
        return self.clean_contacts(result)

    def handle_contact(self, result, contact: Contact):

        socials = {
            'FACEBOOK': 'facebook',
            'INSTAGRAM': 'instagram',
            'LINKEDIN': 'linkedin',
            'TWITTER': 'twitter'
        }

        contacts = {
            'MAIL': 'email',
            'PHONE': 'phone',
        }

        if contact.usage not in socials and contact.type not in contacts:
            return result

        attr = socials[contact.usage] if contact.usage in socials else contacts[contact.type]

        if not hasattr(result, attr):
            return result

        if not getattr(result, attr):
            setattr(result, attr, [])

        getattr(result, attr).append(contact.value)
        return result

    def clean_contacts(self, result, socials = ['facebook', 'instagram', 'linkedin', 'twitter', 'email', 'phone']):
        for social in socials:
            if not hasattr(result, social):
                setattr(result, social, None)
                continue

            value = getattr(result, social)
            if isinstance(value, list) and not value:
                setattr(result, social, None)
            elif isinstance(value, list):
                value = value[:10]
                setattr(result, social, ', '.join(value))
            elif isinstance(value, str):
                setattr(result, social, value.lower())
        return result


if __name__=="__main__":
    class Result(): pass
    b = ContactBrowser()

    result = Result()
    website = 'https://www.sessile.fr/trouvez-votre-fleuriste/floralies-2/?utm_source=google_my_business&utm_medium=organic&utm_campaign=website'
    result.website = website
    result.instagram = None
    result.facebook = None
    result.linkedin = None
    result.twitter = None
    result.email = None

    result = b.get_contacts(result, is_phone=False, is_mail=True, is_social_media=True)
    print(result.__dict__)
    #b.get_contact_links('https://get-a-headsalon.co.uk/contact/')
