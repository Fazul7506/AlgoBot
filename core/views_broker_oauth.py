"""Strict broker OAuth callback used by the browser connection flow."""

import asyncio
import json
import logging

import requests
import websockets
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.models import User
from django.shortcuts import redirect
from django.utils import timezone

from apps.brokers.models import Broker, BrokerAccount, BrokerConnection
from core.models import BotSettings, Subscription, UserProfile
from core.services.oauth_service import DerivOAuthService

logger = logging.getLogger('oauth')
DERIV_ACCOUNTS_URL = settings.DERIV_OPTIONS_ACCOUNTS_URL


def _account_records(payload: dict) -> list[dict]:
    data = payload.get('data', []) if isinstance(payload, dict) else []
    if isinstance(data, dict): data = [data]
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def _select_account(payload: dict) -> dict | None:
    accounts = _account_records(payload)
    return accounts[0] if accounts else None


def _account_id(record: dict) -> str:
    return str(record.get('account_id') or record.get('loginid') or '').strip()


def _account_type(record: dict, websocket_balance: dict | None = None) -> str:
    websocket_balance = websocket_balance or {}
    value = str(record.get('account_type') or '').lower().strip()
    if value in {'real', 'demo'}:
        return value
    if record.get('is_virtual') is True or websocket_balance.get('is_virtual') is True:
        return 'demo'
    return 'real'


async def _verify_authenticated_websocket(access_token: str, account_id: str) -> dict:
    headers = {'Authorization': f'Bearer {access_token}', 'Deriv-App-ID': settings.DERIV_APP_ID, 'Accept': 'application/json'}
    try:
        otp_response = requests.post(f'{DERIV_ACCOUNTS_URL}/{account_id}/otp', headers=headers, timeout=(3.05, 10))
        otp_response.raise_for_status()
        otp_payload = otp_response.json()
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status == 401: raise ValueError('Deriv rejected the OAuth credential') from exc
        if status == 403: raise ValueError('Deriv denied trading access for this account') from exc
        raise ValueError('Deriv could not create an authenticated WebSocket session') from exc
    except (requests.RequestException, ValueError) as exc:
        raise ValueError('Deriv authentication service is temporarily unavailable') from exc
    ws_url = (otp_payload.get('data') or {}).get('url')
    if not ws_url: raise ValueError('Deriv did not return an authenticated WebSocket URL')
    async with websockets.connect(ws_url, open_timeout=10, close_timeout=10) as ws:
        await ws.send(json.dumps({'balance': 1, 'req_id': 1}))
        response = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
    if response.get('error'): raise ValueError(response['error'].get('message', 'Deriv authenticated WebSocket verification failed'))
    return response.get('balance') or {}


def _verify_account(access_token: str) -> tuple[dict | None, list[dict]]:
    headers = {'Authorization': f'Bearer {access_token}', 'Deriv-App-ID': settings.DERIV_APP_ID, 'Accept': 'application/json'}
    try:
        response = requests.get(DERIV_ACCOUNTS_URL, headers=headers, timeout=(3.05, 10))
        response.raise_for_status(); payload = response.json()
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status == 401: raise ValueError('Deriv rejected the OAuth access token') from exc
        if status == 403: raise ValueError('Deriv denied access to the trading account') from exc
        raise ValueError('Deriv account verification failed') from exc
    except (requests.RequestException, ValueError) as exc:
        raise ValueError('Deriv account verification is temporarily unavailable') from exc
    accounts = _account_records(payload)
    return _select_account(payload), accounts


def _ensure_defaults(user):
    UserProfile.objects.get_or_create(user=user)
    Subscription.objects.get_or_create(user=user)
    BotSettings.objects.get_or_create(user=user)


def _persist_deriv_account(*, user, broker, record, access_token, refresh_token, expires_at, preferred=False, websocket_balance=None, websocket_health='not_checked'):
    """Persist one Deriv account returned by OAuth without dropping sibling accounts."""
    account_id = _account_id(record)
    if not account_id:
        return None
    websocket_balance = websocket_balance or {}
    currency = record.get('currency') or websocket_balance.get('currency') or 'USD'
    balance_value = record.get('balance') if record.get('balance') is not None else websocket_balance.get('balance') or 0
    avatar_url = str(record.get('avatar_url') or websocket_balance.get('avatar_url') or '').strip()
    account_type = _account_type(record, websocket_balance)

    broker_account, _ = BrokerAccount.objects.get_or_create(
        broker=broker,
        account_id=account_id,
        defaults={'user': user},
    )
    broker_account.user = user
    broker_account.currency = currency
    broker_account.balance = balance_value
    broker_account.equity = websocket_balance.get('equity') if websocket_balance.get('equity') is not None else balance_value
    broker_account.status = 'active'
    broker_account.is_preferred = preferred
    broker_account.credentials = {
        **(broker_account.credentials or {}),
        'account_type': account_type,
        'connection_health': websocket_health,
        **({'avatar_url': avatar_url} if avatar_url else {}),
    }
    broker_account.set_access_token(access_token)
    broker_account.set_refresh_token(refresh_token or '')
    broker_account.expires_at = expires_at
    broker_account.token_status = 'active'
    broker_account.last_refresh = timezone.now()
    broker_account.last_synced_at = timezone.now()
    broker_account.save()

    if websocket_health == 'verified':
        BrokerConnection.objects.update_or_create(
            broker_account=broker_account,
            defaults={
                'broker': broker,
                'status': 'connected',
                'last_ping': timezone.now(),
                'connected_at': timezone.now(),
                'heartbeat': {'oauth_verified': True, 'websocket_health': websocket_health},
            },
        )
    else:
        BrokerConnection.objects.update_or_create(
            broker_account=broker_account,
            defaults={
                'broker': broker,
                'status': 'degraded',
                'last_ping': None,
                'connected_at': timezone.now(),
                'heartbeat': {'oauth_verified': True, 'websocket_health': websocket_health},
            },
        )
    return broker_account


def callback(request):
    """Complete Deriv OAuth after the broker accounts themselves are verified."""
    if request.GET.get('error'):
        messages.error(request, 'Deriv sign-in was cancelled or rejected. Please try again.')
        DerivOAuthService.clear_oauth_session(request)
        return redirect('broker_connect_page')

    received_state = request.GET.get('state'); code = request.GET.get('code')
    valid, reason = DerivOAuthService.validate_state(received_state, request.session.get('oauth_state'))
    if not valid:
        logger.warning('deriv_oauth_state_validation_failed', extra={'error': reason}); messages.error(request, 'Broker security validation failed. Please restart the connection.'); DerivOAuthService.clear_oauth_session(request); return redirect('broker_connect_page')
    code_verifier = request.session.get('pkce_verifier'); redirect_uri = request.session.get('oauth_redirect_uri')
    valid, reason = DerivOAuthService.validate_pkce(code_verifier, redirect_uri, settings.DERIV_REDIRECT_URI)
    if not valid or not code:
        logger.warning('deriv_oauth_pkce_or_code_validation_failed', extra={'error': reason}); messages.error(request, 'The broker connection could not be validated. Please try again.'); DerivOAuthService.clear_oauth_session(request); return redirect('broker_connect_page')
    success, token_data, token_error = DerivOAuthService.exchange_code_for_token(code, code_verifier, http_client=requests)
    if not success or not token_data:
        logger.error('deriv_oauth_token_exchange_failed', extra={'error': token_error}); messages.error(request, 'Deriv could not complete the secure connection. Please try again.'); DerivOAuthService.clear_oauth_session(request); return redirect('broker_connect_page')
    valid, reason = DerivOAuthService.validate_token_response(token_data)
    if not valid:
        logger.error('deriv_oauth_invalid_token_response', extra={'error': reason}); messages.error(request, 'Deriv returned an invalid authorization response.'); DerivOAuthService.clear_oauth_session(request); return redirect('broker_connect_page')

    access_token = token_data['access_token']
    try:
        account, accounts = _verify_account(access_token)
        if not account or not accounts: raise ValueError('Deriv returned no Options trading account')
        account_id = _account_id(account)
        if not account_id: raise ValueError('Deriv did not return a broker account identity')
    except Exception as exc:
        logger.exception('deriv_oauth_broker_account_verification_failed', extra={'error': str(exc)}); messages.error(request, 'Deriv authentication succeeded, but AlgoBot could not verify the trading account.'); DerivOAuthService.clear_oauth_session(request); return redirect('broker_connect_page')

    selected_account_id = account_id
    broker, _ = Broker.objects.get_or_create(broker_type='deriv', defaults={'name': 'Deriv', 'status': 'active', 'supports_live': True, 'websocket_endpoint': settings.DERIV_AUTH_WS_BASE_URL})

    if request.user.is_authenticated:
        user = request.user
        selected_existing = BrokerAccount.objects.filter(broker=broker, account_id=selected_account_id).select_related('user').first()
        if selected_existing and selected_existing.user_id != user.id:
            messages.error(request, 'That Deriv account is already connected to another AlgoBot user.'); DerivOAuthService.clear_oauth_session(request); return redirect('broker_connect_page')
    else:
        existing_account = BrokerAccount.objects.filter(broker=broker, account_id=selected_account_id).select_related('user').first()
        if existing_account:
            user = existing_account.user
        else:
            user = User.objects.create(username=f'deriv_{selected_account_id}', first_name='Deriv'); user.set_unusable_password(); user.save(update_fields=['password'])

    auth_login(request, user); _ensure_defaults(user)
    expires_in = int(token_data.get('expires_in', 3600)); expires_at = DerivOAuthService.parse_token_expiry(expires_in)
    refresh_token = token_data.get('refresh_token', '')

    persisted_ids = []
    skipped_ids = []
    selected_health = 'not_checked'
    for record in accounts:
        current_id = _account_id(record)
        if not current_id:
            continue
        existing = BrokerAccount.objects.filter(broker=broker, account_id=current_id).select_related('user').first()
        if existing and existing.user_id != user.id:
            if current_id == selected_account_id:
                messages.error(request, 'That Deriv account is already connected to another AlgoBot user.'); DerivOAuthService.clear_oauth_session(request); return redirect('broker_connect_page')
            logger.warning('deriv_oauth_secondary_account_already_connected', extra={'account_id': current_id, 'user_id': user.id})
            skipped_ids.append(current_id)
            continue

        websocket_balance = {}
        websocket_health = 'degraded'
        try:
            websocket_balance = asyncio.run(_verify_authenticated_websocket(access_token, current_id))
            websocket_health = 'verified'
        except Exception as exc:
            logger.warning('deriv_oauth_account_websocket_health_degraded', extra={'account_id': current_id, 'error': str(exc)})

        persisted = _persist_deriv_account(
            user=user,
            broker=broker,
            record=record,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            preferred=(current_id == selected_account_id),
            websocket_balance=websocket_balance,
            websocket_health=websocket_health,
        )
        if persisted:
            persisted_ids.append(current_id)
            if current_id == selected_account_id:
                selected_health = websocket_health

    # Only accounts returned by this OAuth credential are candidates for the
    # preferred set. Existing unrelated broker accounts stay untouched.
    if persisted_ids:
        BrokerAccount.objects.filter(user=user, broker=broker).exclude(account_id=selected_account_id).update(is_preferred=False)

    DerivOAuthService.clear_oauth_session(request)
    if selected_health == 'degraded':
        messages.warning(request, f'Deriv account {selected_account_id} connected. Live broker health is temporarily degraded; AlgoBot will retry automatically.')
    else:
        sibling_count = max(0, len(persisted_ids) - 1)
        suffix = f' {sibling_count} additional Deriv account(s) are available for switching.' if sibling_count else ''
        messages.success(request, f'Deriv account {selected_account_id} connected successfully.{suffix}')
    return redirect('dashboard_page')
