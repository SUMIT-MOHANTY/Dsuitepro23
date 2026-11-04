"""
Django Development Settings for Enterprise LMS
Local development configuration with DEBUG enabled and SQLite fallback support.
"""

import os
from .base import *

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['localhost', '127.0.0.1', '*']

# Database Configuration for Development
# Uses SQLite by default for zero-config local development
# Set USE_POSTGRESQL=true to use PostgreSQL locally
if os.getenv('USE_POSTGRESQL', 'false').lower() == 'true':
    # Use PostgreSQL configuration from base settings
    pass
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# CORS - Allow all origins in development
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True

# Static files - Serve from development server
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'

# Media files - Local filesystem storage in development
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Email backend - Console output for development
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Cache - LocMemCache for development (no Redis required)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
    }
}

# Celery - Run tasks synchronously in development
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Logging - More verbose in development
LOGGING['loggers']['django']['level'] = 'DEBUG'
LOGGING['loggers']['apps']['level'] = 'DEBUG'

# Debug toolbar (optional - uncomment if django-debug-toolbar is installed)
# INSTALLED_APPS += ['debug_toolbar']
# MIDDLEWARE += ['debug_toolbar.middleware.DebugToolbarMiddleware']
# INTERNAL_IPS = ['127.0.0.1']

# JWT Configuration - Longer token lifetime for development
SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'] = timedelta(hours=1)
SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'] = timedelta(days=30)

# Disable secure cookie settings for development
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_SSL_REDIRECT = False

# Spectacular settings - Enable schema serving in development
SPECTACULAR_SETTINGS['SERVE_INCLUDE_SCHEMA'] = True
