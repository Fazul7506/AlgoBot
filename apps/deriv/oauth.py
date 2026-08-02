from urllib.parse import urlencode
from django.conf import settings

def authorization_url(state: str = "") -> str:
    return "https://oauth.deriv.com/oauth2/authorize?" + urlencode({"app_id": settings.DERIV_APP_ID, "l": "EN", "state": state})
