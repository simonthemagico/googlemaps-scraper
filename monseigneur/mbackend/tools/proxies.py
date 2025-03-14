# -*- coding: utf-8 -*-


class proxytools:

    @classmethod
    def forge_proxy_dictionaries(cls, proxy_list):
        proxy_dictionaries = []
        for proxy in proxy_list:
            proxy_dict = {
                "http": "{}".format(proxy),
                "https": "{}".format(proxy),
                "ftp": "{}".format(proxy)
            }

            proxy_dictionaries.append(proxy_dict)
        return proxy_dictionaries

    @classmethod
    def forge_proxy_dictionary(cls, proxy):
        proxy_dict = {
            "http": "{}".format(proxy),
            "https": "{}".format(proxy),
            "ftp": "{}".format(proxy)
        }
        return proxy_dict
