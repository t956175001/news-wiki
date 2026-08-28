import os

from django.core.asgi import get_asgi_application

from config.settings import resolve_settings_module

os.environ.setdefault("DJANGO_SETTINGS_MODULE", resolve_settings_module())

application = get_asgi_application()
