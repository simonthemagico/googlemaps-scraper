import os
import uuid
import logging
from monseigneur.monseigneur.core.backend.manager import BackendManager


class Fetcher(BackendManager):

    def __init__(self, *args, **kwargs):
        self.data_path = os.path.join(os.environ['HOME'], "mdev/monseigneur")
        self.config_path = os.path.join(os.environ['HOME'], "mdev/monseigneur/mbackend/")
        self.home_path = os.environ['HOME']

        custom_path = kwargs.pop("custom_path", None)
        absolute_path = kwargs.pop("absolute_path", None)

        if custom_path:
            self.PATH = os.path.join(self.data_path, "monseigneur/modules/{}".format(custom_path))
        elif absolute_path:
            self.PATH =  os.path.join(self.home_path, absolute_path)
        else:
            self.PATH = os.path.join(self.data_path, "monseigneur/modules/team")

        super(Fetcher, self).__init__(self.PATH, *args, **kwargs)
        logging.basicConfig()
        self.load_config()

    def build_backend(self, module_name, params, logger=None):
        backend_prefix = 'conn_%s_' % module_name
        backend_name = backend_prefix + uuid.uuid4().hex

        storage = None
        backend = super(Fetcher, self).build_backend(module_name, params, name=backend_name, logger=logger)
        backend.name = backend_name
        return backend
