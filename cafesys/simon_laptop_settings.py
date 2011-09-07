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

SITE_ID=1

FACEBOOK_ENABLED = False
ANALYTICS_KEY= ''

