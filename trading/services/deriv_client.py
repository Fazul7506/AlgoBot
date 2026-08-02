"""Minimal Deriv API client wrapper used by the platform.
This is a lightweight HTTP wrapper that centralizes headers and provides
basic methods. It is intentionally small; extend as needed for production.
"""

import os
import requests
from typing import Optional, Dict, Any

DERIV_API_BASE = os.environ.get('DERIV_API_BASE', 'https://api.deriv.com')


class DerivClient:
    """Simple HTTP client for Deriv endpoints.

    Usage:
        client = DerivClient(access_token='...')
        client.buy_contract(...)
    """

    def __init__(self, access_token: Optional[str] = None, base_url: Optional[str] = None):
        self.base_url = base_url or DERIV_API_BASE
        self.access_token = access_token

    def set_token(self, token: str):
        self.access_token = token

    def _headers(self) -> Dict[str, str]:
        headers = {'Content-Type': 'application/json'}
        if self.access_token:
            headers['Authorization'] = f'Bearer {self.access_token}'
        return headers

    def request(self, method: str, path: str, json: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None):
        url = self.base_url.rstrip('/') + '/' + path.lstrip('/')
        resp = requests.request(method, url, json=json, params=params, headers=self._headers(), timeout=10)
        resp.raise_for_status()
        return resp.json()

    # Example wrappers (implement actual payloads per Deriv API docs)
    def get_account(self):
        return self.request('GET', '/v2/account')

    def buy_contract(self, symbol: str, contract_type: str, stake: float, duration: int = 60):
        payload = {
            'symbol': symbol,
            'contract_type': contract_type,
            'stake': stake,
            'duration': duration,
        }
        return self.request('POST', '/v2/contracts/buy', json=payload)

    def sell_contract(self, contract_id: str):
        payload = {'contract_id': contract_id}
        return self.request('POST', '/v2/contracts/sell', json=payload)
