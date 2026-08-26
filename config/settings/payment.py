"""Payment and subscription billing settings.

All production values come from environment variables so Render remains the
single source of truth. Paid plan prices are stored in the smallest currency
unit (KES cents), matching the billing models and checkout service.
"""
import os

PAYMENT_PROVIDER = os.getenv("PAYMENT_PROVIDER", "intasend").strip().lower()
PAYMENT_HTTP_TIMEOUT = int(os.getenv("PAYMENT_HTTP_TIMEOUT", "20"))

ALGOBOT_BILLING_CURRENCY = os.getenv("ALGOBOT_BILLING_CURRENCY", "KES").strip().upper()
ALGOBOT_BASIC_PRICE_CENTS = os.getenv("ALGOBOT_BASIC_PRICE_CENTS", "").strip() or None
ALGOBOT_PRO_PRICE_CENTS = os.getenv("ALGOBOT_PRO_PRICE_CENTS", "").strip() or None
ALGOBOT_ENTERPRISE_PRICE_CENTS = os.getenv("ALGOBOT_ENTERPRISE_PRICE_CENTS", "").strip() or None
ALGOBOT_SUBSCRIPTION_PERIOD_DAYS = int(os.getenv("ALGOBOT_SUBSCRIPTION_PERIOD_DAYS", "30"))

INTASEND_PUBLIC_KEY = os.getenv("INTASEND_PUBLIC_KEY", "").strip()
INTASEND_SECRET_KEY = os.getenv("INTASEND_SECRET_KEY", "").strip()
INTASEND_WEBHOOK_CHALLENGE = os.getenv("INTASEND_WEBHOOK_CHALLENGE", "").strip()
INTASEND_API_BASE_URL = os.getenv("INTASEND_API_BASE_URL", "https://api.intasend.com").strip()

PESAPAL_CONSUMER_KEY = os.getenv("PESAPAL_CONSUMER_KEY", "").strip()
PESAPAL_CONSUMER_SECRET = os.getenv("PESAPAL_CONSUMER_SECRET", "").strip()
PESAPAL_NOTIFICATION_ID = os.getenv("PESAPAL_NOTIFICATION_ID", "").strip()
PESAPAL_API_BASE_URL = os.getenv("PESAPAL_API_BASE_URL", "https://pay.pesapal.com/v3").strip()
