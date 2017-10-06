# -*- encoding: utf-8 -*-
"""Project configuration helpers."""
from nailgun.config import ServerConfig


def nailgun_check():
    """Check if there is an auto-loadable json config."""
    try:
        ServerConfig(url='').get()
        return True
    except:
        try:
            ServerConfig(url='').get(
                path='config/server_configs.json').save()
            return True
        except Exception as e:
            raise e
