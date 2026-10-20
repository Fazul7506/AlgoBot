import hashlib

from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.test import TestCase
from django.urls import reverse


class SecuritySessionInventoryTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="session-owner", password="password")
        self.client.force_login(self.user)

    def _other_session(self):
        session = SessionStore()
        session["_auth_user_id"] = str(self.user.pk)
        session["_auth_user_backend"] = "django.contrib.auth.backends.ModelBackend"
        session["_auth_user_hash"] = self.user.get_session_auth_hash()
        session.save()
        return session

    def test_inventory_does_not_expose_raw_session_keys(self):
        other = self._other_session()
        response = self.client.get(reverse("security-session-inventory"))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        other_row = next(row for row in payload["sessions"] if not row["current"])
        self.assertEqual(other_row["id"], hashlib.sha256(other.session_key.encode()).hexdigest())
        self.assertNotIn(other.session_key, response.content.decode())

    def test_user_can_revoke_another_session_but_not_current_session(self):
        other = self._other_session()
        fingerprint = hashlib.sha256(other.session_key.encode()).hexdigest()
        response = self.client.post(reverse("security-session-revoke", args=[fingerprint]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Session.objects.filter(session_key=other.session_key).exists())

        current_key = self.client.session.session_key
        current_fingerprint = hashlib.sha256(current_key.encode()).hexdigest()
        response = self.client.post(reverse("security-session-revoke", args=[current_fingerprint]))
        self.assertEqual(response.status_code, 400)
        self.assertTrue(Session.objects.filter(session_key=current_key).exists())
