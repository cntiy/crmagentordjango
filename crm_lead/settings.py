"""
Django settings for crm_lead project.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ('1', 'true', 'yes', 'on')


def env_required(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise RuntimeError(f"环境变量 {name} 未设置")
    return val


DEBUG = env_bool('DJANGO_DEBUG', False)

if DEBUG:
    SECRET_KEY = os.environ.get(
        'DJANGO_SECRET_KEY',
        'django-insecure-dev-only-do-not-use-in-prod',
    )
else:
    SECRET_KEY = env_required('DJANGO_SECRET_KEY')

ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
    if h.strip()
]


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'qywork',
]

# ===== 企业微信配置 =====
QYWORK_CORP_ID = os.environ.get('QYWORK_CORP_ID', '')
QYWORK_AGENT_ID = os.environ.get('QYWORK_AGENT_ID', '')
QYWORK_AGENT_SECRET = os.environ.get('QYWORK_AGENT_SECRET', '')
QYWORK_VERIFY_FILE = BASE_DIR / 'WW_verify_lKNYL5JBAI1lduZs.txt'

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'crm_lead.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'crm_lead.wsgi.application'

DATABASE_ROUTERS = ['crm_lead.db_router.CrmRouter']


# Database

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    },
    'crm': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.environ.get('CRM_DB_NAME', 'crm_data'),
        'USER': os.environ.get('CRM_DB_USER', 'root'),
        'PASSWORD': os.environ.get('CRM_DB_PASSWORD', ''),
        'HOST': os.environ.get('CRM_DB_HOST', '127.0.0.1'),
        'PORT': os.environ.get('CRM_DB_PORT', '3306'),
        'OPTIONS': {
            'charset': 'utf8mb4',
        },
    },
}


AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
