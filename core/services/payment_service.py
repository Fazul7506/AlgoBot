import logging
from typing import Optional
from django.conf import settings

logger = logging.getLogger(__name__)


class PaymentService:
    """Abstracted payment service. Currently provides Stripe placeholder methods.

    To enable real payments, set `PAYMENT_PROVIDER=stripe` and provide
    `STRIPE_API_KEY` and `STRIPE_WEBHOOK_SECRET` in `settings.py` or env.
    """

    def __init__(self):
        self.provider = getattr(settings, 'PAYMENT_PROVIDER', 'stripe')
        self.stripe_api_key = getattr(settings, 'STRIPE_API_KEY', '')
        self.stripe_webhook_secret = getattr(settings, 'STRIPE_WEBHOOK_SECRET', '')

    def create_checkout_session(self, user, subscription_plan):
        logger.info('Creating checkout session for %s plan=%s', getattr(user, 'username', None), subscription_plan)

        if self.provider != 'stripe':
            logger.warning('Payment provider %s not supported; returning placeholder', self.provider)
            return {'url': 'https://checkout.example.com/session/placeholder'}

        try:
            import stripe
        except Exception:
            logger.exception('stripe library not available')
            return {'url': 'https://checkout.example.com/session/placeholder'}

        stripe.api_key = self.stripe_api_key

        # Resolve price id and mode
        price_id = None
        mode = 'payment'

        # subscription_plan may be a Subscription instance or string key
        if hasattr(subscription_plan, 'stripe_price_id') and subscription_plan.stripe_price_id:
            price_id = subscription_plan.stripe_price_id
            mode = 'subscription' if getattr(subscription_plan, 'recurring', False) else 'payment'
        elif isinstance(subscription_plan, str):
            # allow a mapping in settings: STRIPE_PRICE_MAP = {'PRO': 'price_...'}
            price_map = getattr(settings, 'STRIPE_PRICE_MAP', {}) or {}
            price_id = price_map.get(subscription_plan)

        base_url = getattr(settings, 'BASE_URL', '').rstrip('/')
        success_url = f'{base_url}/billing/success'
        cancel_url = f'{base_url}/billing/cancel'

        try:
            if price_id:
                session = stripe.checkout.Session.create(
                    payment_method_types=['card'],
                    mode=mode,
                    line_items=[{
                        'price': price_id,
                        'quantity': 1,
                    }],
                    metadata={'user_id': str(user.id), 'plan': str(getattr(subscription_plan, 'plan', subscription_plan))},
                    success_url=success_url,
                    cancel_url=cancel_url,
                )
            else:
                # Fallback: create a one-off payment using price data
                amount = getattr(subscription_plan, 'price_cents', 0) or 0
                currency = getattr(subscription_plan, 'currency', 'usd')
                session = stripe.checkout.Session.create(
                    payment_method_types=['card'],
                    mode='payment',
                    line_items=[{
                        'price_data': {
                            'currency': currency,
                            'product_data': {'name': f"{getattr(subscription_plan, 'plan', 'Custom plan')}"},
                            'unit_amount': int(amount),
                        },
                        'quantity': 1,
                    }],
                    metadata={'user_id': str(user.id), 'plan': str(getattr(subscription_plan, 'plan', subscription_plan))},
                    success_url=success_url,
                    cancel_url=cancel_url,
                )

            return {'session_id': session.id, 'url': getattr(session, 'url', '')}
        except Exception:
            logger.exception('Failed to create Stripe checkout session')
            return {'url': 'https://checkout.example.com/session/placeholder'}

    def handle_webhook(self, payload: bytes, sig_header: str) -> Optional[dict]:
        if self.provider != 'stripe':
            logger.warning('Received webhook but provider %s not supported', self.provider)
            return None

        try:
            import stripe
        except Exception:
            logger.exception('stripe library not available')
            return None

        stripe.api_key = self.stripe_api_key

        try:
            event = stripe.Webhook.construct_event(payload, sig_header, self.stripe_webhook_secret)
        except Exception as exc:
            logger.exception('Webhook signature verification failed: %s', exc)
            return None

        # Process relevant events
        try:
            typ = event['type']
            data = event['data']['object']

            if typ == 'checkout.session.completed':
                # Retrieve metadata
                metadata = data.get('metadata', {}) or {}
                user_id = metadata.get('user_id')
                plan_key = metadata.get('plan')

                from django.contrib.auth import get_user_model
                from core.models import Invoice, Payment, Subscription, ReferralReward

                User = get_user_model()
                user = None
                try:
                    user = User.objects.filter(id=int(user_id)).first() if user_id else None
                except Exception:
                    user = None

                amount_total = data.get('amount_total') or data.get('amount_subtotal') or 0
                currency = data.get('currency', 'usd')
                external_id = data.get('id')

                if user:
                    invoice = Invoice.objects.create(user=user, external_id=external_id, amount_cents=int(amount_total or 0), currency=currency, paid=True, metadata={'stripe_event': typ})
                    Payment.objects.create(user=user, invoice=invoice, external_id=external_id, amount_cents=int(amount_total or 0), currency=currency, status='succeeded')

                    # Update or create subscription
                    try:
                        sub, _ = Subscription.objects.get_or_create(user=user)
                        # If checkout used a known price, attach it
                        if 'subscription' in data.get('mode', '') or data.get('display_items'):
                            # best-effort: set stripe_price_id if available in session
                            price = None
                            if data.get('line_items'):
                                price = data['line_items'][0].get('price', {}).get('id')
                            sub.stripe_price_id = plan_key or getattr(sub, 'stripe_price_id', '')
                        sub.price_cents = int(amount_total or 0)
                        sub.currency = currency
                        sub.is_active = True
                        sub.renewed_at = sub.renewed_at
                        sub.save()
                    except Exception:
                        logger.exception('Failed to update subscription for user %s', getattr(user, 'username', None))

                    # Award referral credits
                    try:
                        profile = getattr(user, 'trading_profile', None)
                        if profile and getattr(profile, 'referred_by', None):
                            # Default referral credit amount (dollars)
                            credit_amount = getattr(settings, 'REFERRAL_CREDIT_AMOUNT', 0.0)
                            if credit_amount <= 0:
                                # Fallback: 5% of purchase
                                credit_amount = (int(amount_total or 0) / 100.0) * 0.05

                            profile.referral_credits = (profile.referral_credits or 0.0) + float(credit_amount)
                            profile.save()
                            ReferralReward.objects.create(referrer=profile.referred_by, referee=user, amount_credits=float(credit_amount))
                    except Exception:
                        logger.exception('Failed to award referral credit for user %s', getattr(user, 'username', None))

            return {'received': True, 'type': typ}

        except Exception:
            logger.exception('Failed to process stripe webhook')
            return None

    def create_invoice_record(self, user, amount_cents: int, currency: str = 'usd'):
        from core.models import Invoice
        invoice = Invoice.objects.create(user=user, amount_cents=amount_cents, currency=currency)
        return invoice
 