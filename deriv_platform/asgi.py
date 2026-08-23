"""ASGI entrypoint for HTTP and authenticated WebSocket traffic."""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "deriv_platform.settings")

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application


django_asgi_application = get_asgi_application()

from .routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_application,
        "websocket": AuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
    }
)
