from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from unittest.mock import patch

from core.models import UserProfile


class ProfileCompletionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="profile-completion-user",
            email="profile-completion@example.test",
            password="A-secure-test-password-123!",
        )
        # The profile-gate tests need a verified account so the assertions
        # exercise profile completion rather than the earlier email-verification gate.
        UserProfile.objects.update_or_create(
            user=self.user,
            defaults={
                "email_verified": True,
                "email_verified_at": timezone.now(),
            },
        )

    def test_page_requires_local_login(self):
        response = self.client.get(reverse("profile_completion_page"))
        self.assertRedirects(
            response,
            f"{reverse('login_page')}?next={reverse('profile_completion_page')}",
            fetch_redirect_response=False,
        )

    def test_page_renders_for_signed_in_user_before_broker_connection(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("profile_completion_page"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Complete your profile")
        self.assertContains(response, "First name")
        self.assertContains(response, "Last name")
        self.assertContains(response, "Google account connected")
        self.assertContains(response, "Broker marketplace")

    def test_required_names_are_validated(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("profile_completion_page"),
            {"first_name": "", "last_name": "", "timezone": "UTC"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter your first and last name")
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "")
        self.assertEqual(self.user.last_name, "")

    @patch("core.broker_onboarding.has_authorized_broker_connection", return_value=False)
    def test_saving_profile_returns_to_broker_management_when_not_connected(self, _connected):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("profile_completion_page"),
            {
                "first_name": "Taylor",
                "terms_accepted": "on",
                "last_name": "Example",
                "phone": "+254700000000",
                "country": "Kenya",
                "timezone": "Africa/Nairobi",
                "bio": "AlgoBot user",
            },
        )
        self.assertRedirects(
            response, reverse("broker_marketplace_page"), fetch_redirect_response=False
        )
        self.user.refresh_from_db()
        self.assertEqual((self.user.first_name, self.user.last_name), ("Taylor", "Example"))
        profile = UserProfile.objects.get(user=self.user)
        self.assertEqual(profile.country, "Kenya")
        self.assertEqual(profile.timezone, "Africa/Nairobi")

    @patch("core.broker_onboarding.has_authorized_broker_connection", return_value=True)
    def test_new_google_signup_always_goes_to_broker_marketplace_after_profile(self, _connected):
        self.client.force_login(self.user)
        session = self.client.session
        session["google_profile_completion_pending"] = True
        session.save()

        response = self.client.post(
            reverse("profile_completion_page"),
            {"first_name": "Taylor",
                "terms_accepted": "on", "last_name": "Example", "timezone": "Africa/Nairobi"},
        )

        self.assertRedirects(
            response, reverse("broker_marketplace_page"), fetch_redirect_response=False
        )
        self.assertFalse(self.client.session.get("google_profile_completion_pending"))

    @patch("core.broker_onboarding.has_authorized_broker_connection", return_value=True)
    def test_profile_persistence_failure_does_not_mark_profile_complete(self, _connected):
        from django.db import DatabaseError
        from core.profile_completion import profile_is_complete

        UserProfile.objects.get_or_create(user=self.user)
        self.client.force_login(self.user)
        with patch("core.models.UserProfile.save", side_effect=DatabaseError("simulated storage failure")):
            response = self.client.post(
                reverse("profile_completion_page"),
                {
                    "first_name": "Taylor",
                    "last_name": "Example",
                    "terms_accepted": "on",
                    "timezone": "UTC",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "temporary storage problem")
        self.user.refresh_from_db()
        profile = UserProfile.objects.get(user=self.user)
        self.assertEqual(self.user.first_name, "")
        self.assertEqual(self.user.last_name, "")
        self.assertIsNone(profile.terms_accepted_at)
        self.assertFalse(profile_is_complete(self.user))

    @patch("core.broker_onboarding.has_authorized_broker_connection", return_value=True)
    def test_saving_profile_still_returns_to_marketplace_when_connected(self, _connected):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("profile_completion_page"),
            {"first_name": "Taylor",
                "terms_accepted": "on", "last_name": "Example"},
        )
        self.assertRedirects(
            response, reverse("broker_marketplace_page"), fetch_redirect_response=False
        )


    @patch("core.browser_auth._send_verification", return_value=True)
    def test_form_registration_requires_profile_completion_after_verified_login(self, _send_verification):
        response = self.client.post(
            reverse("register_page"),
            {
                "username": "new-form-user",
                "first_name": "Taylor",
                "last_name": "Example",
                "email": "new-form-user@example.test",
                "password": "A-secure-registration-password-123!",
                "password_confirm": "A-secure-registration-password-123!",
            },
        )
        self.assertRedirects(
            response, reverse("verify_email_page"), fetch_redirect_response=False
        )
        user = get_user_model().objects.get(username="new-form-user")
        profile = UserProfile.objects.get(user=user)
        self.assertIsNone(profile.terms_accepted_at)

        from django.utils import timezone
        profile.email_verified = True
        profile.email_verified_at = timezone.now()
        profile.save(update_fields=["email_verified", "email_verified_at"])
        response = self.client.post(
            reverse("login_page"),
            {
                "identifier": user.username,
                "password": "A-secure-registration-password-123!",
            },
        )
        self.assertRedirects(
            response, reverse("profile_completion_page"), fetch_redirect_response=False
        )

    def test_incomplete_profile_cannot_reach_dashboard_or_marketplace_after_logout_and_login(self):
        from core.profile_completion import profile_is_complete

        profile = UserProfile.objects.get(user=self.user)
        from django.utils import timezone
        profile.email_verified = True
        profile.email_verified_at = timezone.now()
        profile.save(update_fields=["email_verified", "email_verified_at"])
        self.client.force_login(self.user)
        for target in (reverse("dashboard_page"), reverse("broker_marketplace_page")):
            response = self.client.get(target)
            self.assertRedirects(
                response, reverse("profile_completion_page"), fetch_redirect_response=False
            )

        self.client.post(reverse("logout"))
        logged_in = self.client.post(
            reverse("login_page"),
            {"identifier": self.user.username, "password": "A-secure-test-password-123!"},
        )
        self.assertEqual(logged_in.status_code, 302)
        self.assertEqual(logged_in.url, reverse("profile_completion_page"))
        self.assertFalse(profile_is_complete(self.user))

    def test_legacy_google_session_flag_cannot_bypass_broker_onboarding(self):
        from django.utils import timezone

        self.user.first_name = "Taylor"
        self.user.last_name = "Example"
        self.user.save(update_fields=["first_name", "last_name"])
        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        profile.terms_accepted_at = timezone.now()
        profile.email_verified = True
        profile.email_verified_at = timezone.now()
        profile.save(update_fields=["terms_accepted_at", "email_verified", "email_verified_at"])
        self.client.force_login(self.user)
        session = self.client.session
        session["google_existing_login_dashboard"] = True
        session.save()

        with patch("core.broker_onboarding.has_authorized_broker_connection", return_value=False):
            response = self.client.get(reverse("dashboard_page"))

        self.assertRedirects(
            response, reverse("broker_marketplace_page"), fetch_redirect_response=False
        )

    def test_profile_gate_ignores_manipulated_next_parameter(self):
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("dashboard_page") + "?next=https://evil.example/steal"
        )
        self.assertRedirects(
            response, reverse("profile_completion_page"), fetch_redirect_response=False
        )

    def test_profile_picture_is_persisted_and_served_after_refresh(self):
        import io
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile

        image_buffer = io.BytesIO()
        Image.new("RGB", (64, 64), (20, 120, 180)).save(image_buffer, format="PNG")
        upload = SimpleUploadedFile(
            "avatar.png", image_buffer.getvalue(), content_type="image/png"
        )
        self.client.force_login(self.user)
        with patch("core.broker_onboarding.has_authorized_broker_connection", return_value=False):
            response = self.client.post(
                reverse("profile_completion_page"),
                {
                    "first_name": "Taylor",
                "terms_accepted": "on",
                    "last_name": "Example",
                    "username": self.user.username,
                    "timezone": "Africa/Nairobi",
                    "profile_picture": upload,
                },
            )
        self.assertEqual(response.status_code, 302)
        profile = UserProfile.objects.get(user=self.user)
        self.assertTrue(profile.profile_picture_data)
        self.assertEqual(profile.profile_picture_content_type, "image/webp")
        self.assertEqual(profile.avatar_url, "")
        photo_response = self.client.get(reverse("profile_picture"))
        self.assertEqual(photo_response.status_code, 200)
        self.assertEqual(photo_response["Content-Type"], "image/webp")
        self.assertEqual(photo_response.content, bytes(profile.profile_picture_data))

    def test_optional_password_can_be_set_without_losing_browser_session(self):
        self.client.force_login(self.user)
        new_password = "Distinct-Strong-Password!824"
        with patch("core.broker_onboarding.has_authorized_broker_connection", return_value=False):
            response = self.client.post(
                reverse("profile_completion_page"),
                {
                    "first_name": "Taylor",
                "terms_accepted": "on",
                    "last_name": "Example",
                    "username": self.user.username,
                    "new_password": new_password,
                    "confirm_password": new_password,
                    "timezone": "Africa/Nairobi",
                },
            )
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(new_password))
        self.assertEqual(
            self.client.get(reverse("profile_completion_page")).status_code, 200
        )

    def test_username_collision_is_rejected(self):
        other = get_user_model().objects.create_user(
            username="already-taken", email="other-profile@example.test"
        )
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("profile_completion_page"),
            {
                "first_name": "Taylor",
                "terms_accepted": "on",
                "last_name": "Example",
                "username": other.username,
                "timezone": "Africa/Nairobi",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "That username is already in use.")
        self.user.refresh_from_db()
        self.assertNotEqual(self.user.username, other.username)

    def test_security_center_profile_picture_survives_refresh(self):
        import io
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile

        image_buffer = io.BytesIO()
        Image.new("RGB", (80, 80), (80, 40, 180)).save(image_buffer, format="PNG")
        upload = SimpleUploadedFile(
            "security-avatar.png", image_buffer.getvalue(), content_type="image/png"
        )
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("profile_page"),
            {
                "first_name": "Taylor",
                "terms_accepted": "on",
                "last_name": "Example",
                "country": "Kenya",
                "timezone": "Africa/Nairobi",
                "phone": "",
                "bio": "",
                "profile_picture": upload,
            },
        )
        self.assertEqual(response.status_code, 302)
        profile = UserProfile.objects.get(user=self.user)
        self.assertTrue(profile.profile_picture_data)
        photo_response = self.client.get(reverse("profile_picture"))
        self.assertEqual(photo_response.status_code, 200)
        self.assertEqual(photo_response.content, bytes(profile.profile_picture_data))

    def test_optional_date_of_birth_and_gender_are_saved(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("profile_completion_page"),
            {
                "first_name": "Taylor",
                "terms_accepted": "on",
                "last_name": "Example",
                "username": self.user.username,
                "timezone": "Africa/Nairobi",
                "date_of_birth": "1998-04-12",
                "gender": "prefer_not_to_say",
            },
        )
        self.assertEqual(response.status_code, 302)
        profile = UserProfile.objects.get(user=self.user)
        self.assertEqual(str(profile.date_of_birth), "1998-04-12")
        self.assertEqual(profile.gender, "prefer_not_to_say")


    def test_reference_onboarding_avatar_is_the_upload_control(self):
        from pathlib import Path
        template = Path("templates/core/profile_completion.html").read_text(encoding="utf-8")
        self.assertIn('class="profile-onboarding__avatar-upload"', template)
        self.assertIn('for="profile_picture"', template)
        self.assertIn('id="profile-picture-preview-small"', template)
        self.assertIn('image/jpeg,image/png,image/webp', template)
        self.assertIn('event.dataTransfer', template)
        self.assertNotIn('type="file" accept="image/jpeg,image/png,image/webp"\n', template)

    def test_reference_progress_and_country_code_selectors_use_shared_anchored_selects(self):
        from pathlib import Path
        template = Path("templates/core/profile_completion.html").read_text(encoding="utf-8")
        base = Path("templates/base.html").read_text(encoding="utf-8")
        self.assertIn("Profile Details", template)
        self.assertIn("Additional Info", template)
        self.assertIn("Preferences", template)
        self.assertIn('id="phone_country_code"', template)
        self.assertIn('id="country" name="country"', template)
        self.assertIn("anchored_selects.js", base)
        self.assertIn("anchored_selects.css", base)


    def test_invalid_international_phone_is_rejected_server_side(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("profile_completion_page"),
            {
                "first_name": "Taylor",
                "terms_accepted": "on",
                "last_name": "Example",
                "phone": "not-a-phone",
                "country": "Kenya",
                "timezone": "UTC",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter a valid international phone number")
        profile = UserProfile.objects.get(user=self.user)
        self.assertEqual(profile.phone, "")

    def test_blank_optional_country_and_phone_do_not_erase_saved_values(self):
        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        profile.phone = "+254712345678"
        profile.country = "Kenya"
        profile.save(update_fields=["phone", "country", "updated_at"])
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("profile_completion_page"),
            {
                "first_name": "Taylor",
                "terms_accepted": "on",
                "last_name": "Example",
                "phone": "",
                "country": "",
                "timezone": "UTC",
            },
        )
        self.assertEqual(response.status_code, 302)
        profile.refresh_from_db()
        self.assertEqual(profile.phone, "+254712345678")
        self.assertEqual(profile.country, "Kenya")

    def test_country_and_phone_dropdowns_have_searchable_country_metadata(self):
        from pathlib import Path
        template = Path("templates/core/profile_completion.html").read_text(encoding="utf-8")
        self.assertIn('id="country"', template)
        self.assertIn('id="phone_country_code"', template)
        self.assertIn('id="phone_country_code" aria-label="Phone country calling code" data-ab-searchable="true"', template)
        self.assertIn('id="country" name="country" autocomplete="country-name" aria-label="Country or region" data-ab-searchable="true"', template)
        self.assertIn('data-iso="KE"', template)
        self.assertIn('data-dial-code="+254"', template)
        self.assertIn('data-iso="GB"', template)
        self.assertIn('data-iso="JP"', template)
        self.assertIn("syncCallingCode", template)


    def test_google_avatar_url_is_served_only_from_allowlisted_https_host(self):
        self.client.force_login(self.user)
        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        profile.avatar_url = "https://lh3.googleusercontent.com/a/test-avatar"
        profile.save(update_fields=["avatar_url", "updated_at"])
        response = self.client.get(reverse("profile_picture"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], profile.avatar_url)
        profile.avatar_url = "https://googleusercontent.com.evil.example/avatar.png"
        profile.save(update_fields=["avatar_url", "updated_at"])
        response = self.client.get(reverse("profile_picture"))
        self.assertEqual(response.status_code, 404)

    def test_reference_layout_includes_desktop_benefits_panel(self):
        from pathlib import Path
        template = Path("templates/core/profile_completion.html").read_text(encoding="utf-8")
        self.assertIn('class="profile-onboarding__content-grid"', template)
        self.assertIn("Get Started with AlgoBot", template)
        self.assertIn("Personalized recommendations", template)
        self.assertIn("Secure account verification", template)


    def test_country_selectors_use_full_existing_country_dataset_and_iso_sync(self):
        from pathlib import Path
        template = Path("templates/core/profile_completion.html").read_text(encoding="utf-8")
        self.assertIn("intlTelInput.getCountryData()", template)
        self.assertIn("const phoneOptions = data.map", template)
        self.assertIn("const syncFromCountry", template)
        self.assertIn("const syncFromPhone", template)
        self.assertIn("anchored_selects.js", Path("templates/base.html").read_text(encoding="utf-8"))


    def test_terms_acceptance_is_required_and_persisted(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("profile_completion_page"), {"first_name": "Taylor", "last_name": "Example", "timezone": "UTC"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please accept the Terms of Service and Privacy Policy")
        profile = UserProfile.objects.get(user=self.user)
        self.assertIsNone(profile.terms_accepted_at)
        response = self.client.post(reverse("profile_completion_page"), {"first_name": "Taylor", "last_name": "Example", "timezone": "UTC", "terms_accepted": "on"})
        self.assertEqual(response.status_code, 302)
        profile.refresh_from_db()
        self.assertIsNotNone(profile.terms_accepted_at)


    def test_shared_anchored_selects_do_not_misclassify_country_codes_or_render_letter_badges(self):
        from pathlib import Path

        script = Path("static/js/anchored_selects.js").read_text(encoding="utf-8")
        stylesheet = Path("static/css/anchored_selects.css").read_text(encoding="utf-8")
        self.assertIn("select.dataset.abSelectType === 'instrument'", script)
        self.assertNotIn("[...select.options].some(option => option.value && instrumentValue(option.value))", script)
        self.assertNotIn("slice(0, 2).toUpperCase()", script)
        self.assertNotIn(".ab-select-option-icon--fallback {", stylesheet)
        self.assertIn("ab-select-option-icon--market-fallback", script)
        self.assertIn("ab-select-option-icon--market-fallback", stylesheet)
        self.assertIn("select.dataset.abSearchable === 'true'", script)
        self.assertIn("select.id === 'phone_country_code'", script)
        self.assertIn("const isCountryOrPhoneSelect", script)
        self.assertIn("const hasSearch = select.dataset.abSearchable === 'true' || isInstrumentSelect(select)", script)
        self.assertIn("search.hidden = !hasSearch", script)
        self.assertIn("item.setAttribute('aria-selected', String(index === select.selectedIndex))", script)
        self.assertIn("const previousIndex = select.selectedIndex", script)
        self.assertIn("const nextIndex = [...select.options].indexOf(option)", script)
        self.assertIn("select.selectedIndex = nextIndex", script)
        self.assertIn("if (previousIndex !== nextIndex)", script)
        self.assertIn("if (!isInstrumentSelect(select) || !option || !option.value) return ''", script)
        self.assertIn("if (icon) icon.innerHTML = select.id === 'phone_country_code' ? '' : iconFor(select, current)", script)
        self.assertIn("(flag ? flag + ' ' : '') + current.value", script)

    def test_profile_edit_action_uses_a_dismissible_modal(self):
        from pathlib import Path

        template = Path("templates/core/profile.html").read_text(encoding="utf-8")
        self.assertIn('data-profile-edit-open', template)
        self.assertIn('data-profile-edit-modal', template)
        self.assertIn('data-profile-edit-close', template)
        self.assertIn('aria-modal="true"', template)
        self.assertIn("event.key === 'Escape'", template)


    def test_profile_modal_initializes_phone_widget_after_deferred_script(self):
        from pathlib import Path

        template = Path("templates/core/profile.html").read_text(encoding="utf-8")
        self.assertIn('src="https://cdn.jsdelivr.net/npm/intl-tel-input@25.3.1/build/js/intlTelInput.min.js" defer', template)
        self.assertIn("window.addEventListener('load', initialize, {once:true})", template)
        self.assertIn("window.intlTelInput(phone", template)
        self.assertIn("iti.getNumber()", template)
        self.assertIn("name=\"phone\" type=\"tel\"", template)
