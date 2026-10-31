from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from core.account_context import SESSION_KEY, get_active_account_for_session


class SessionAccountContextTests(SimpleTestCase):
    def test_explicit_session_selection_is_authoritative(self):
        account = SimpleNamespace(
            pk=17,
            broker=SimpleNamespace(broker_type="deriv"),
            account_type="real",
        )
        queryset = MagicMock()
        queryset.filter.return_value.first.return_value = account
        session = {"active_broker_account_id": "17"}

        with patch("core.account_context.connected_accounts", return_value=queryset):
            resolved = get_active_account_for_session(SimpleNamespace(is_authenticated=True), session)

        self.assertIs(resolved, account)
        self.assertEqual(session[SESSION_KEY], "17")

    def test_stale_session_selection_is_cleared_and_fails_closed(self):
        queryset = MagicMock()
        queryset.filter.return_value.first.return_value = None
        session = {"active_broker_account_id": "999"}

        with patch("core.account_context.connected_accounts", return_value=queryset):
            resolved = get_active_account_for_session(SimpleNamespace(is_authenticated=True), session)

        self.assertIsNone(resolved)
        self.assertNotIn(SESSION_KEY, session)


class BrokerEventAccountScopeTests(SimpleTestCase):
    def test_events_for_the_selected_account_are_forwardable(self):
        from core.broker_events import account_event_matches_active_account

        self.assertTrue(account_event_matches_active_account({"account_id": 17}, 17))

    def test_events_for_another_account_are_filtered(self):
        from core.broker_events import account_event_matches_active_account

        self.assertFalse(account_event_matches_active_account({"account_id": 18}, 17))

    def test_account_events_fail_closed_without_a_selected_account(self):
        from core.broker_events import account_event_matches_active_account

        self.assertFalse(account_event_matches_active_account({"account_id": 18}, None))

    def test_user_level_events_without_account_scope_are_preserved(self):
        from core.broker_events import account_event_matches_active_account

        self.assertTrue(account_event_matches_active_account({"message": "connected"}, None))
