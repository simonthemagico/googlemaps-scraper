# -*- coding: utf-8 -*-

import os
import importlib
import sys

from monseigneur.monseigneur.core.tools.backend import Module
from monseigneur.monseigneur.core.tools.compat import basestring
from monseigneur.monseigneur.core.tools.log import getLogger
from monseigneur.monseigneur.core.exceptions import ModuleLoadError

__all__ = ['LoadedModule', 'ModulesLoader', 'RepositoryModulesLoader']


class LoadedModule(object):
    def __init__(self, package):
        self.logger = getLogger('backend')
        self.package = package
        self.klass = None
        # if package has __all__ attribute, use it to find the Module class
        if hasattr(package, '__all__'):
            self.get_instance(package)
        # otherwise, find the first class that is a subclass of Module
        if not self.klass:
            self.get_instance(package)
        if not self.klass:
            raise ImportError('%s is not a backend (no Module class found)' % package)

    def get_instance(self, package):
        for attrname in package.__all__:
            attr = getattr(package, attrname)
            if isinstance(attr, type) and issubclass(attr, Module) and attr != Module:
                self.klass = attr

    @property
    def name(self):
        return self.klass.NAME

    @property
    def maintainer(self):
        return u'%s <%s>' % (self.klass.MAINTAINER, self.klass.EMAIL)

    @property
    def version(self):
        return self.klass.VERSION

    @property
    def description(self):
        return self.klass.DESCRIPTION

    @property
    def license(self):
        return self.klass.LICENSE

    @property
    def config(self):
        return self.klass.CONFIG

    @property
    def website(self):
        if self.klass.BROWSER and hasattr(self.klass.BROWSER, 'BASEURL') and self.klass.BROWSER.BASEURL:
            return self.klass.BROWSER.BASEURL
        if self.klass.BROWSER and hasattr(self.klass.BROWSER, 'DOMAIN') and self.klass.BROWSER.DOMAIN:
            return '%s://%s' % (self.klass.BROWSER.PROTOCOL, self.klass.BROWSER.DOMAIN)
        else:
            return None

    @property
    def icon(self):
        return self.klass.ICON

    def iter_caps(self):
        return self.klass.iter_caps()

    def has_caps(self, *caps):
        """Return True if module implements at least one of the caps."""
        for c in caps:
            if (isinstance(c, basestring) and c in [cap.__name__ for cap in self.iter_caps()]) or \
               (type(c) == type and issubclass(self.klass, c)):
                return True
        return False

    def create_instance(self, backend, backend_name, params, logger=None):
        try:
            backend_instance = self.klass(backend, backend_name, params, logger=logger or self.logger)
        except TypeError:
            backend_instance = self.klass()
        self.logger.debug(u'Created backend "%s" for module "%s"' % (backend_name, self.name))
        return backend_instance


class ModulesLoader(object):
    """
    Load modules.
    """
    LOADED_MODULE = LoadedModule

    def __init__(self, path, version=None):
        self.version = version
        self.path = path
        self.loaded = {}
        self.logger = getLogger('modules')

    def get_or_load_module(self, module_name):
        """
        Can raise a ModuleLoadError exception.
        """
        if module_name not in self.loaded:
            self.load_module(module_name)
        return self.loaded[module_name]

    def iter_existing_module_names(self):
        for name in os.listdir(self.path):
            try:
                if '__init__.py' in os.listdir(os.path.join(self.path, name)):
                    yield name
            except OSError:
                # if path/name is not a directory
                continue

    def module_exists(self, name):
        for existing_module_name in self.iter_existing_module_names():
            if existing_module_name == name:
                return True
        return False

    def load_all(self):
        for existing_module_name in self.iter_existing_module_names():
            try:
                self.load_module(existing_module_name)
            except ModuleLoadError as e:
                self.logger.warning('could not load module %s: %s', existing_module_name, e)

    def _add_in_modules_path(self, path):
        try:
            import leadstrooper_modules
        except ImportError:
            from types import ModuleType

            leadstrooper_modules = ModuleType('leadstrooper_modules')
            sys.modules['leadstrooper_modules'] = leadstrooper_modules

            leadstrooper_modules.__path__ = [path]
        else:
            if path not in leadstrooper_modules.__path__:
                leadstrooper_modules.__path__.append(path)

    def load_module(self, module_name):

        module_path = self.get_module_path(module_name)

        if module_name in self.loaded:
            self.logger.debug('Module "%s" is already loaded from %s', module_name, module_path)
            return

        self._add_in_modules_path(module_path)
        module_spec = importlib.util.find_spec(f'leadstrooper_modules.{module_name}')
        pymodule = importlib.import_module(f'leadstrooper_modules.{module_name}')
        module = self.LOADED_MODULE(pymodule)

        self.loaded[module_name] = module

    def get_module_path(self, module_name):
        return self.path


class RepositoryModulesLoader(ModulesLoader):
    """
    Load modules from repositories.
    """

    def __init__(self, repositories):
        super(RepositoryModulesLoader, self).__init__(repositories.modules_dir, repositories.version)
        self.repositories = repositories

    def iter_existing_module_names(self):
        for name in self.repositories.get_all_modules_info():
            yield name

    def get_module_path(self, module_name):
        minfo = self.repositories.get_module_info(module_name)
        if minfo is None:
            raise ModuleLoadError(module_name, 'No such module %s' % module_name)
        if minfo.path is None:
            raise ModuleLoadError(module_name, 'Module %s is not installed' % module_name)

        return minfo.path
