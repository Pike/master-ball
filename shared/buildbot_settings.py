from __future__ import absolute_import
import os

INSTALLED_APPS = ['life', 'pushes', 'mbdb', 'l10nstats']

try:
    from local import *  # noqa
except ImportError:
    pass

# overload configuration from environment, as far as we have it
try:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': os.environ['ELMO_DB_NAME'],
            'USER': os.environ['ELMO_DB_USER'],
            'PASSWORD': os.environ['ELMO_DB_PASSWORD'],
            'HOST': os.environ['ELMO_DB_HOST'],
            'PORT': '',
            'CONN_MAX_AGE': 500,
            'OPTIONS': {
                'charset': 'utf8',
                'use_unicode': True,
            },
            'TEST': {
                'CHARSET': "utf8",
                'COLLATION': 'utf8_general_ci',
            },
        },
    }
except KeyError:
    pass
for local_var, env_var in (
            ('BUILD_BASE', 'ELMO_BUILD_BASE'),
            ('DATADOG_NAMESPACE', 'ELMO_DATADOG_NAMESPACE'),
            ('ES_COMPARE_HOST', 'ES_COMPARE_HOST'),
            ('ES_COMPARE_INDEX', 'ES_COMPARE_INDEX'),
            ('HG_SHARES', 'ELMO_HG_SHARES'),
            ('SECRET_KEY', 'ELMO_SECRET_KEY'),
            ('REPOSITORY_BASE', 'ELMO_REPOSITORY_BASE'),
):
    if env_var in os.environ:
        locals()[local_var] = os.environ[env_var]
