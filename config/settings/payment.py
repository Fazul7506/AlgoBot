"""Payment and subscription billing settings.

Production deployments can override prices and callback URLs through environment
variables. Callback URLs are explicit so hosted payment providers never depend
on a guessed Render host or local development URL.
"""
import os

PAYMENT_PROVIDER = os.getenv("PAYMENT_PROVIDER", "intasend").strip().lower()
PAYMENT_HTTP_TIMEOUT = int(os.getenv("PAYMENT_HTTP_TIMEOUT", "20"))
ALGOBOT_BILLING_CURRENCY = os.getenv("ALGOBOT_BILLING_CURRENCY", "KES").strip().upper()
# KES cents. Deployment values override these defaults without a code change.
ALGOBOT_BASIC_PRICE_CENTS = os.getenv("ALGOBOT_BASIC_PRICE_CENTS", "99900").strip() or None
ALGOBOT_PRO_PRICE_CENTS = os.getenv("ALGOBOT_PRO_PRICE_CENTS", "499900").strip() or None
ALGOBOT_ENTERPRISE_PRICE_CENTS = os.getenv("ALGOBOT_ENTERPRISE_PRICE_CENTS", "2499900").strip() or None
ALGOBOT_SUBSCRIPTION_PERIOD_DAYS = int(os.getenv("ALGOBOT_SUBSCRIPTION_PERIOD_DAYS", "30"))

# Explicit application return URLs. Provider checkout URLs are dynamic and
# must be created per invoice/amount; they should never be stored as env vars.
# Keep configured callback paths exactly as supplied.  The trailing slash is
# meaningful for Django callback routes and prevents an avoidable redirect
# from a hosted payment provider.
BILLING_SUCCESS_URL = os.getenv("BILLING_SUCCESS_URL", "").strip()
BILLING_CANCEL_URL = os.getenv("BILLING_CANCEL_URL", "").strip()
PESAPAL_CALLBACK_URL = os.getenv("PESAPAL_CALLBACK_URL", "").strip()
PESAPAL_CANCELLATION_URL = os.getenv("PESAPAL_CANCELLATION_URL", "").strip()

INTASEND_PUBLIC_KEY = os.getenv("INTASEND_PUBLIC_KEY", "").strip()
INTASEND_SECRET_KEY = os.getenv("INTASEND_SECRET_KEY", "").strip()
INTASEND_WEBHOOK_CHALLENGE = os.getenv("INTASEND_WEBHOOK_CHALLENGE", "").strip()
INTASEND_API_BASE_URL = os.getenv("INTASEND_API_BASE_URL", "https://api.intasend.com").strip()
# Leave checkout tariffs unset unless IntaSend has explicitly enabled and
# supplied a tariff for this merchant account.  Supplying a made-up tariff can
# cause IntaSend to reject an otherwise valid checkout request.
INTASEND_MOBILE_TARIFF = os.getenv("INTASEND_MOBILE_TARIFF", "").strip()
INTASEND_CARD_TARIFF = os.getenv("INTASEND_CARD_TARIFF", "").strip()
PESAPAL_CONSUMER_KEY = os.getenv("PESAPAL_CONSUMER_KEY", "").strip()
PESAPAL_CONSUMER_SECRET = os.getenv("PESAPAL_CONSUMER_SECRET", "").strip()
PESAPAL_NOTIFICATION_ID = os.getenv("PESAPAL_NOTIFICATION_ID", "").strip()
PESAPAL_API_BASE_URL = os.getenv("PESAPAL_API_BASE_URL", "https://pay.pesapal.com/v3").strip()
