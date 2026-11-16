from unittest.mock import patch

from asgiref.sync import sync_to_async
from django.contrib.messages import get_messages
from django.utils import timezone

from apps.brokers.models import Broker, BrokerAccount, BrokerConnection

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import UserProfile


class SafeDerivOAuthCallbackTests(TestCase):
    @override_settings(
        DERIV_OAUTH_CLIENT_ID="oauth-client-test",
        DERIV_REDIRECT_URI="https://algobot.dpdns.org/callback/",
    )
    def test_provider_error_does_not_restart_oauth_for_anonymous_user(self):
        response = self.client.get(reverse("callback") + "?error=access_denied")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("login_page"))
        self.assertNotIn("/dashboard/", response.url)

    @override_settings(
        DERIV_OAUTH_CLIENT_ID="oauth-client-test",
        DERIV_REDIRECT_URI="https://algobot.dpdns.org/callback/",
    )
    def test_provider_error_keeps_authenticated_user_in_broker_management(self):
        user = get_user_model().objects.create_user(
            username="broker-failure-user", email="broker-failure@example.test", password="pass12345"
        )
        UserProfile.objects.update_or_create(user=user, defaults={"email_verified": True})
        self.client.force_login(user)

        response = self.client.get(reverse("callback") + "?error=access_denied")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("broker_marketplace_page"))
        self.assertNotIn("/dashboard/", response.url)

    @override_settings(
        DERIV_OAUTH_CLIENT_ID="oauth-client-test",
        DERIV_REDIRECT_URI="https://algobot.dpdns.org/callback/",
    )
    def test_invalid_oauth_state_does_not_restart_oauth_or_open_dashboard(self):
        session = self.client.session
        session["oauth_state"] = "expected-state"
        session["pkce_verifier"] = "verifier"
        session["oauth_redirect_uri"] = "https://algobot.dpdns.org/callback/"
        session.save()

        response = self.client.get(
            reverse("callback") + "?code=test-code&state=wrong-state"
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("login_page"))
        self.assertEqual(response.url, reverse("login_page"))
        self.assertNotIn("/dashboard/", response.url)

    @override_settings(
        DERIV_OAUTH_CLIENT_ID="oauth-client-test",
        DERIV_REDIRECT_URI="https://algobot.dpdns.org/callback/",
    )
    @patch("core.views_deriv_oauth_safe._verify_account", return_value=(None, []))
    @patch(
        "core.views_deriv_oauth_safe.DerivOAuthService.exchange_code_for_token",
        return_value=(
            True,
            {
                "access_token": "token",
                "expires_in": 3600,
                "refresh_token": "refresh",
            },
            None,
        ),
    )
    def test_authenticated_account_verification_failure_never_redirects_dashboard(
        self, exchange_token, verify_account
    ):
        user = get_user_model().objects.create_user(
            username="broker-verification-failure", email="broker-verification-failure@example.test", password="pass12345"
        )
        UserProfile.objects.update_or_create(user=user, defaults={"email_verified": True})
        self.client.force_login(user)
        session = self.client.session
        session["oauth_state"] = "expected-state"
        session["pkce_verifier"] = "verifier"
        session["oauth_redirect_uri"] = "https://algobot.dpdns.org/callback/"
        session.save()

        with (
            patch(
                "core.views_deriv_oauth_safe.DerivOAuthService.validate_state",
                return_value=(True, ""),
            ),
            patch(
                "core.views_deriv_oauth_safe.DerivOAuthService.validate_pkce",
                return_value=(True, ""),
            ),
            patch(
                "core.views_deriv_oauth_safe.DerivOAuthService.validate_token_response",
                return_value=(True, ""),
            ),
        ):
            response = self.client.get(
                reverse("callback") + "?code=test-code&state=expected-state"
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("broker_marketplace_page"))
        self.assertNotIn("/dashboard/", response.url)
        exchange_token.assert_called_once()
        verify_account.assert_called_once()


    @override_settings(
        DERIV_OAUTH_CLIENT_ID="oauth-client-test",
        DERIV_REDIRECT_URI="https://algobot.dpdns.org/callback/",
        CREDENTIALS_ENCRYPTION_KEY="test-only-fernet-key",
    )
    def test_successful_oauth_verifies_demo_and_real_accounts_and_uses_broker_only_confirmation(self):
        user = get_user_model().objects.create_user(
            username="broker-success-user",
            email="broker-success@example.test",
            password="pass12345",
            first_name="Broker",
            last_name="Tester",
        )
        UserProfile.objects.update_or_create(user=user, defaults={"email_verified": True})
        self.client.force_login(user)
        session = self.client.session
        session["oauth_state"] = "expected-state"
        session["pkce_verifier"] = "verifier"
        session["oauth_redirect_uri"] = "https://algobot.dpdns.org/callback/"
        session.save()

        records = [
            {"account_id": "VRTC-DEMO-1", "account_type": "demo", "is_virtual": True},
            {"account_id": "CR-REAL-1", "account_type": "real", "is_virtual": False},
        ]
        broker = Broker.objects.create(
            name="Deriv",
            broker_type="deriv",
            status="active",
            supports_demo=True,
            supports_live=True,
            metadata={"auth": "oauth"},
        )

        def persist_account(*, user, broker, record, access_token, refresh_token, expires_at, **kwargs):
            account = BrokerAccount.objects.create(
                user=user,
                broker=broker,
                account_id=record["account_id"],
                status="active",
                credentials={"account_type": record["account_type"]},
                expires_at=expires_at,
            )
            account.set_access_token(access_token)
            account.save(update_fields=["access_token"])
            BrokerConnection.objects.create(
                broker=broker,
                broker_account=account,
                status="degraded",
            )
            return account

        async def connect_account(service, broker, account):
            connection, _ = await sync_to_async(BrokerConnection.objects.update_or_create)(
                broker_account=account,
                defaults={
                    "broker": broker,
                    "status": "connected",
                    "last_ping": timezone.now(),
                    "connected_at": timezone.now(),
                },
            )
            return connection

        async def sync_account(service, account):
            def persist_snapshot():
                account.last_synced_at = timezone.now()
                account.save(update_fields=["last_synced_at"])
            await sync_to_async(persist_snapshot, thread_sensitive=True)()
            return account, {"account_id": account.account_id, "account_type": account.account_type}

        with (
            patch("core.views_deriv_oauth_safe.DerivOAuthService.validate_state", return_value=(True, "")),
            patch("core.views_deriv_oauth_safe.DerivOAuthService.validate_pkce", return_value=(True, "")),
            patch("core.views_deriv_oauth_safe.DerivOAuthService.validate_token_response", return_value=(True, "")),
            patch(
                "core.views_deriv_oauth_safe.DerivOAuthService.exchange_code_for_token",
                return_value=(True, {"access_token": "oauth-token", "refresh_token": "refresh", "expires_in": 3600}, None),
            ),
            patch("core.views_deriv_oauth_safe._verify_account", return_value=(records[0], records)),
            patch("core.views_deriv_oauth_safe.fetch_deriv_identity", return_value={"loginid": "VRTC-DEMO-1", "user_id": "provider-user"}),
            patch("core.views_deriv_oauth_safe.sync_deriv_user_identity", return_value={}),
            patch("core.views_deriv_oauth_safe._persist_deriv_account", side_effect=persist_account),
            patch("apps.brokers.services.BrokerConnectionService.connect", new=connect_account),
            patch("apps.brokers.services.SynchronizationService.sync_account", new=sync_account),
        ):
            response = self.client.get(
                reverse("callback") + "?code=test-code&state=expected-state"
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard_page"))
        accounts = list(BrokerAccount.objects.filter(user=user, broker=broker).order_by("account_id"))
        self.assertEqual({account.account_type for account in accounts}, {"demo", "real"})
        self.assertEqual(BrokerConnection.objects.filter(broker_account__in=accounts, status="connected").count(), 2)
        self.assertTrue(all(account.last_synced_at for account in accounts))
        demo_account = next(account for account in accounts if account.account_type == "demo")
        self.assertEqual(self.client.session.get("active_broker_account_id"), demo_account.pk)

        # Verify the post-redirect browser JWT and broker-account API preserve
        # the same session-authoritative active account.
        token_response = self.client.get(reverse("browser_api_token"))
        self.assertEqual(token_response.status_code, 200)
        account_response = self.client.get(
            "/api/brokers/accounts/",
            HTTP_AUTHORIZATION="Bearer " + token_response.json()["access"],
        )
        self.assertEqual(account_response.status_code, 200)
        payload = account_response.json()
        rows = payload.get("results", payload) if isinstance(payload, dict) else payload
        demo_row = next(row for row in rows if row["account_id"] == "VRTC-DEMO-1")
        real_row = next(row for row in rows if row["account_id"] == "CR-REAL-1")
        self.assertTrue(demo_row["is_active"])
        self.assertFalse(real_row["is_active"])
        active_response = self.client.get(
            "/api/brokers/accounts/active/",
            HTTP_AUTHORIZATION="Bearer " + token_response.json()["access"],
        )
        self.assertEqual(active_response.status_code, 200)
        self.assertEqual(active_response.json()["active_account_id"], demo_account.pk)

        messages = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertIn("Deriv connected successfully.", messages)
        self.assertFalse(any("VRTC-DEMO-1" in message or "CR-REAL-1" in message for message in messages))
