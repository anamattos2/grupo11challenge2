"""Configuração do backend. Segredos e conexões vêm somente do ambiente."""
import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Variáveis já definidas no ambiente têm prioridade sobre o arquivo local.
load_dotenv(BASE_DIR.parent.parent / ".env")


def env(nome: str) -> str:
    """Retorna uma variável obrigatória ou interrompe a inicialização."""
    valor = os.environ.get(nome)
    if not valor:
        raise ImproperlyConfigured(f"Variável de ambiente obrigatória ausente: {nome}")
    return valor


def env_lista(nome: str) -> list[str]:
    """Lê uma variável opcional com valores separados por vírgula."""
    return [item.strip() for item in os.environ.get(nome, "").split(",") if item.strip()]


SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = os.environ.get("DJANGO_DEBUG", "false").lower() == "true"
ALLOWED_HOSTS = env_lista("DJANGO_ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env_lista("DJANGO_CSRF_TRUSTED_ORIGINS")

# Fora do modo de depuração, os cookies só trafegam por HTTPS.
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_AGE = 8 * 60 * 60

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "autenticacao",
    "financas",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

ROOT_URLCONF = "config.urls"

# Necessário para a página de documentação interativa do Django Ninja.
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
    }
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB"),
        "USER": env("POSTGRES_USER"),
        "PASSWORD": env("POSTGRES_PASSWORD"),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
