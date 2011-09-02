# -*- coding: utf-8 -*-

DEBUG = True
LDAP_ENABLED = False
STATS_CACHE = True

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql_psycopg2",
        "NAME": "cafesys",
        "TEST_NAME": "test_cafesys",
        "USER": "sp",
        "PASSWORD": "",
        "HOST": "",
        "PORT": "",
    }
}

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
EMAIL_HOST = ''
EMAIL_PORT = 25
EMAIL_USE_TLS = False
DEFAULT_FROM_EMAIL = 'admin@baljan.org'

SITE_ID=1

FACEBOOK_ENABLED = False
ANALYTICS_KEY= ''

