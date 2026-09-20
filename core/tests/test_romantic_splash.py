from django.test import RequestFactory, SimpleTestCase, override_settings

from core.context_processors import algobot_romantic_splash


class RomanticSplashContextTests(SimpleTestCase):
    def setUp(self):
        self.request = RequestFactory().get("/")

    @override_settings(TIME_ZONE="UTC")
    def test_disabled_by_default(self):
        with self.settings(ALGOBOT_SPLASH_ENABLED=False):
            context = algobot_romantic_splash(self.request)["algobot_romantic_splash"]
        self.assertFalse(context["enabled"])
        self.assertEqual(context["repeat"], "session")

    def test_home_path_can_be_enabled(self):
        with self.settings(ALGOBOT_SPLASH_ENABLED=True, ALGOBOT_SPLASH_PATHS_JSON='["/"]'):
            context = algobot_romantic_splash(self.request)["algobot_romantic_splash"]
        self.assertTrue(context["enabled"])
        self.assertEqual(context["name"], "👑 Mäh Qűěěñ ❤️")
        self.assertEqual(context["phone"], "0141 322612")

    def test_other_paths_are_not_enabled(self):
        request = RequestFactory().get("/login/")
        with self.settings(ALGOBOT_SPLASH_ENABLED=True, ALGOBOT_SPLASH_PATHS_JSON='["/"]'):
            context = algobot_romantic_splash(request)["algobot_romantic_splash"]
        self.assertFalse(context["enabled"])

    def test_messages_are_renderable_from_json_env(self):
        with self.settings(
            ALGOBOT_SPLASH_ENABLED=True,
            ALGOBOT_SPLASH_MESSAGES_JSON='["One ❤️", "Two 💋"]',
        ):
            context = algobot_romantic_splash(self.request)["algobot_romantic_splash"]
        self.assertEqual(context["messages"], ["One ❤️", "Two 💋"])
