import os
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from core.context_processors import algobot_romantic_splash


class RomanticSplashContextTests(SimpleTestCase):
    def setUp(self):
        self.request = RequestFactory().get("/")

    def test_disabled_by_default(self):
        with patch.dict(os.environ, {"ALGOBOT_SPLASH_ENABLED": "false"}, clear=False):
            context = algobot_romantic_splash(self.request)["algobot_romantic_splash"]
        self.assertFalse(context["enabled"])
        self.assertEqual(context["repeat"], "session")

    def test_home_path_can_be_enabled(self):
        with patch.dict(
            os.environ,
            {"ALGOBOT_SPLASH_ENABLED": "true", "ALGOBOT_SPLASH_PATHS_JSON": "[\"/\"]"},
            clear=False,
        ):
            context = algobot_romantic_splash(self.request)["algobot_romantic_splash"]
        self.assertTrue(context["enabled"])
        self.assertEqual(context["name"], "Mäh Qűěěñ ❤️")
        self.assertEqual(context["phone"], "0141 322612")

    def test_other_paths_are_not_enabled(self):
        request = RequestFactory().get("/login/")
        with patch.dict(
            os.environ,
            {"ALGOBOT_SPLASH_ENABLED": "true", "ALGOBOT_SPLASH_PATHS_JSON": "[\"/\"]"},
            clear=False,
        ):
            context = algobot_romantic_splash(request)["algobot_romantic_splash"]
        self.assertFalse(context["enabled"])

    def test_messages_are_renderable_from_json_env(self):
        with patch.dict(
            os.environ,
            {
                "ALGOBOT_SPLASH_ENABLED": "true",
                "ALGOBOT_SPLASH_MESSAGES_JSON": "[\"One ❤️\", \"Two 💋\"]",
            },
            clear=False,
        ):
            context = algobot_romantic_splash(self.request)["algobot_romantic_splash"]
        self.assertEqual(context["messages"], ["One ❤️", "Two 💋"])

    def test_cinematic_controls_are_env_configurable(self):
        with patch.dict(
            os.environ,
            {
                "ALGOBOT_SPLASH_ENABLED": "true",
                "ALGOBOT_SPLASH_PARTICLES_ENABLED": "false",
                "ALGOBOT_SPLASH_CONFETTI_ENABLED": "true",
                "ALGOBOT_SPLASH_ROSES_ENABLED": "true",
                "ALGOBOT_SPLASH_COUNTDOWN_ENABLED": "true",
                "ALGOBOT_SPLASH_SOUND_ENABLED": "true",
                "ALGOBOT_SPLASH_CELEBRATION_DURATION_MS": "4200",
                "ALGOBOT_SPLASH_TRANSITION_STYLE": "cinematic",
                "ALGOBOT_SPLASH_INTENSITY": "cinematic",
                "ALGOBOT_SPLASH_MEMORY_MESSAGE": "Memory ❤️",
                "ALGOBOT_SPLASH_FINAL_MESSAGE": "Final ✨",
                "ALGOBOT_SPLASH_READY_MESSAGE": "Ready?",
                "ALGOBOT_SPLASH_PROCEED_LABEL": "ENTER ❤️",
                "ALGOBOT_SPLASH_AUTO_PROCEED": "false",
            },
            clear=False,
        ):
            context = algobot_romantic_splash(self.request)["algobot_romantic_splash"]

        self.assertFalse(context["particles_enabled"])
        self.assertTrue(context["confetti_enabled"])
        self.assertTrue(context["roses_enabled"])
        self.assertTrue(context["countdown_enabled"])
        self.assertTrue(context["sound_enabled"])
        self.assertEqual(context["celebration_duration_ms"], 4200)
        self.assertEqual(context["transition_style"], "cinematic")
        self.assertEqual(context["intensity"], "cinematic")
        self.assertEqual(context["memory_message"], "Memory ❤️")
        self.assertEqual(context["final_message"], "Final ✨")
        self.assertEqual(context["ready_message"], "Ready?")
        self.assertEqual(context["proceed_label"], "ENTER ❤️")
        self.assertFalse(context["auto_proceed"])
