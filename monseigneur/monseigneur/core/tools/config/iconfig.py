# -*- coding: utf-8 -*-

class ConfigError(Exception):
    pass


class IConfig(object):
    """
    Interface for config storage.

    Config stores keys and values. Each key is a path of components, allowing
    to group multiple options.
    """

    def load(self, default={}):
        """
        Load config.

        :param default: default values for the config
        :type default: dict[:class:`str`]
        """
        raise NotImplementedError()

    def save(self):
        """Save config."""
        raise NotImplementedError()

    def set(self, *args):
        """
        Set a config value.

        :param args: all args except the last arg are the path of the option key.
        :type args: str or object
        """
        raise NotImplementedError()

    def delete(self, *args):
        """
        Delete an option from config.

        :param args: path to the option key.
        :type args: str
        """
        raise NotImplementedError()

    def get(self, *args, **kwargs):
        """
        Get the value of an option.

        :param args: path of the option key.
        :param default: if specified, default value when path is not found
        """
        raise NotImplementedError()
