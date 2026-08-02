import requests


TOKEN_URL = "https://auth.deriv.com/oauth2/token"


class DerivAuthService:

    @staticmethod
    def exchange_code(code, code_verifier, client_id, redirect_uri):

        response = requests.post(TOKEN_URL, data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "code_verifier": code_verifier,
            "redirect_uri": redirect_uri,
        })

        return response.json()