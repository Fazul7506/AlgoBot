"""Browser-based views for AlgoBot."""
import json
import logging
from apps.market_data.models import MarketSymbol
from urllib.parse import urlparse
from django.conf import settings
from django.http import Http404,HttpResponse,JsonResponse
from django.shortcuts import render,redirect
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from apps.brokers.models import Broker,BrokerAccount,BrokerIntegrationRequest
from core.services.oauth_service import DerivOAuthService
logger=logging.getLogger(__name__)
def _preferred_deriv_account(user):
    accounts = list(BrokerAccount.objects.filter(user=user, broker__broker_type='deriv').select_related('broker').prefetch_related('connections').order_by('-last_synced_at', '-id'))
    # Only show accounts whose broker connection has been accepted and verified.
    return next((account for account in accounts if _deriv_connected(account)), None)
def _deriv_connected(account): return bool(account and account.status == "active" and account.broker.status == "active" and account.token_status == "active" and not account.is_token_expired and account.is_connection_eligible)
def home(request):
    if request.method=='HEAD': return HttpResponse(status=200)
    from core.broker_onboarding import has_authorized_broker_connection
    broker_connected = bool(request.user.is_authenticated and has_authorized_broker_connection(request.user))
    if broker_connected: return redirect('/dashboard/')
    return render(request,'core/home.html',{'hero_title':'AlgoBot AI trading platform','hero_copy':'Institutional-grade AI trading infrastructure for market intelligence, strategies, risk controls and broker execution.','broker_connected':broker_connected})
def login_page(request):
    from core.browser_auth import login_page as view
    return view(request)
def register_page(request):
    from core.browser_auth import register_page as view
    return view(request)
@login_required
def dashboard_page(request):
    from core.broker_onboarding import has_authorized_broker_connection, has_verified_account_email
    if not has_verified_account_email(request.user):
        from django.contrib import messages
        messages.info(request, 'Verify your AlgoBot email before opening the dashboard.')
        return redirect('verify_email_page')
    # A returning Google login gets one dashboard landing even if broker setup is
    # incomplete. Trading/API execution remains independently broker-gated.
    returning_google_login = bool(request.session.pop("google_existing_login_dashboard", False))
    if not returning_google_login and not has_authorized_broker_connection(request.user):
        from django.contrib import messages
        messages.info(request, 'Connect and verify your Deriv account before opening trading features.')
        return redirect('broker_marketplace_page')
    return render(request,'core/dashboard.html')
@login_required
def markets_page(request): return render(request,'core/markets.html')
@login_required
def strategies_page(request): return render(request,'core/strategies.html')
@login_required
@never_cache
def trading_page(request): return render(request,'core/trading.html')
@login_required
def backtesting_page(request): return render(request,'core/backtesting.html')
@login_required
def predictions_page(request): return render(request,'core/predictions.html')
@login_required
def risk_page(request): return render(request,'core/risk.html')
@login_required
def orders_page(request): return render(request,'core/orders.html')
@login_required
def positions_page(request): return render(request,'core/positions.html')
@login_required
def signals_page(request): return render(request,'core/signals.html')

@login_required
def analysis_page(request):
    markets = list(
        MarketSymbol.objects.filter(is_active=True, is_tradable=True)
        .values("symbol", "display_name", "market", "sub_market")
        .order_by("market", "symbol")
    )
    return render(
        request,
        "core/analysis.html",
        {"analysis_markets": markets},
    )
@login_required
def billing_success_page(request): return render(request,'core/billing_success.html')
@login_required
def billing_cancel_page(request): return render(request,'core/billing_cancel.html')
@login_required
def settings_page(request):
    return render(request, 'core/settings.html')
@login_required
def profile_page(request):
    """Delegate legacy imports to the canonical persistent profile editor."""
    from core.views_profile import profile_page as editable_profile_page
    return editable_profile_page(request)

@login_required
def profile_completion_page(request):
    """Collect the minimum identity details needed to finish workspace onboarding."""
    from django.contrib import messages
    from core.broker_onboarding import has_authorized_broker_connection
    from core.models import UserProfile
    import io
    from PIL import Image, UnidentifiedImageError

    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        from datetime import date
        from django.contrib.auth.password_validation import validate_password
        from django.contrib.auth.validators import UnicodeUsernameValidator
        from django.core.exceptions import ValidationError
        from django.contrib.auth import password_validation

        first_name = str(request.POST.get("first_name") or "").strip()
        last_name = str(request.POST.get("last_name") or "").strip()
        username = str(request.POST.get("username") or request.user.username).strip()
        new_password = str(request.POST.get("new_password") or "")
        confirm_password = str(request.POST.get("confirm_password") or "")
        dob_raw = str(request.POST.get("date_of_birth") or "").strip()
        gender = str(request.POST.get("gender") or "").strip()
        terms_accepted = request.POST.get("terms_accepted") in {"on", "true", "1"}
        avatar_file = request.FILES.get("profile_picture")
        picture_data = None
        errors = []
        if not first_name or not last_name:
            errors.append("Enter your first and last name to complete your profile.")
        if not profile.terms_accepted_at and not terms_accepted:
            errors.append("Please accept the Terms of Service and Privacy Policy to continue.")
        if not username or len(username) > 150:
            errors.append("Enter a valid username (150 characters or fewer).")
        else:
            try:
                UnicodeUsernameValidator()(username)
            except ValidationError as exc:
                errors.extend(exc.messages)
            if UserProfile.user.field.related_model.objects.filter(username__iexact=username).exclude(pk=request.user.pk).exists():
                errors.append("That username is already in use.")
        dob = None
        if dob_raw:
            try:
                dob = date.fromisoformat(dob_raw)
                if dob > date.today():
                    errors.append("Date of birth cannot be in the future.")
            except ValueError:
                errors.append("Enter a valid date of birth.")
        if gender and gender not in {"female", "male", "non_binary", "prefer_not_to_say", "self_described"}:
            errors.append("Choose a valid gender option.")
        phone_raw = str(request.POST.get("phone") or "").strip()
        if phone_raw:
            # The form submits an international number; validate it server-side too.
            phone_compact = "".join(character for character in phone_raw if character not in " ()-")
            if not phone_compact.startswith("+") or not phone_compact[1:].isdigit() or not 7 <= len(phone_compact[1:]) <= 15 or phone_compact[1:].startswith("0"):
                errors.append("Enter a valid international phone number including its country calling code.")
            else:
                phone_raw = phone_compact
        if avatar_file:
            if avatar_file.size > 5 * 1024 * 1024:
                errors.append("Profile picture must be 5 MB or smaller.")
            else:
                try:
                    image = Image.open(avatar_file)
                    if image.format not in {"JPEG", "PNG", "WEBP"}:
                        errors.append("Profile picture must be JPEG, PNG, or WEBP.")
                    elif image.width * image.height > 25_000_000:
                        errors.append("Profile picture dimensions must not exceed 25 megapixels.")
                    else:
                        image.verify()
                        avatar_file.seek(0)
                        image = Image.open(avatar_file)
                        image.load()
                        has_alpha = image.mode in {"RGBA", "LA"} or "transparency" in image.info
                        normalized = image.convert("RGBA" if has_alpha else "RGB")
                        normalized.thumbnail((512, 512), Image.Resampling.LANCZOS)
                        buffer = io.BytesIO()
                        normalized.save(buffer, format="WEBP", quality=85, method=6)
                        picture_data = buffer.getvalue()
                except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError):
                    errors.append("Upload a valid image file (JPEG, PNG, or WEBP).")
                finally:
                    avatar_file.seek(0)
        if new_password or confirm_password:
            if not new_password or new_password != confirm_password:
                errors.append("Enter matching passwords in both password fields.")
            else:
                try:
                    validate_password(new_password, user=request.user)
                except ValidationError as exc:
                    errors.extend(exc.messages)
        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            request.user.first_name = first_name[:150]
            request.user.last_name = last_name[:150]
            request.user.username = username
            user_fields = ["first_name", "last_name", "username"]
            if new_password:
                request.user.set_password(new_password)
                user_fields.append("password")
            request.user.save(update_fields=user_fields)
            if new_password:
                # Keep the current browser session valid after an explicit password set.
                from django.contrib.auth import update_session_auth_hash
                update_session_auth_hash(request, request.user)
            # Empty optional inputs must not erase previously saved profile data.
            if phone_raw:
                profile.phone = phone_raw[:32]
            submitted_country = str(request.POST.get("country") or "").strip()
            if submitted_country:
                profile.country = submitted_country[:100]
            profile.timezone = str(request.POST.get("timezone") or "UTC").strip()[:100] or "UTC"
            profile.bio = str(request.POST.get("bio") or "").strip()[:5000]
            # Blank optional fields must not erase values previously provided
            # by the user or a verified identity claim.
            if dob_raw:
                profile.date_of_birth = dob
            if gender:
                profile.gender = gender
            if terms_accepted and not profile.terms_accepted_at:
                from django.utils import timezone
                profile.terms_accepted_at = timezone.now()
            if picture_data is not None:
                # Use the same durable profile-row storage as the Security Center
                # editor. A browser preview is not considered saved until these
                # bytes and the content type are persisted.
                profile.profile_picture_data = picture_data
                profile.profile_picture_content_type = "image/webp"
                profile.avatar_url = ""
            profile.save(update_fields=[
                "phone", "country", "timezone", "bio", "date_of_birth", "gender",
                "avatar_url", "profile_picture_data", "profile_picture_content_type",
                "terms_accepted_at", "updated_at",
            ])
            messages.success(request, "Your AlgoBot profile is complete.")
            # Profile completion always advances to the marketplace. Broker
            # connection remains an explicit user action; the marketplace itself
            # must not be mistaken for a connected broker.
            request.session.pop("google_profile_completion_pending", None)
            return redirect("broker_marketplace_page")

    return render(request, "core/profile_completion.html", {
        "first_name": request.POST.get("first_name", request.user.first_name),
        "last_name": request.POST.get("last_name", request.user.last_name),
        "username": request.POST.get("username", request.user.username),
        "date_of_birth": request.POST.get("date_of_birth", profile.date_of_birth.isoformat() if profile.date_of_birth else ""),
        "gender": request.POST.get("gender", profile.gender),
        "phone": request.POST.get("phone", profile.phone),
        "country": request.POST.get("country", profile.country),
        "timezone_value": request.POST.get("timezone", profile.timezone or "UTC"),
        "bio": request.POST.get("bio", profile.bio),
        "terms_accepted": bool(profile.terms_accepted_at) or request.POST.get("terms_accepted") in {"on", "true", "1"},
        "terms_already_accepted": bool(profile.terms_accepted_at),
        "profile_picture_url": (
            reverse("profile_picture") + "?v=" + str(int(profile.updated_at.timestamp()))
            if profile.profile_picture_data or profile.avatar_url else ""
        ),
    })
def terms_page(request): return render(request,'core/terms.html')
def privacy_page(request): return render(request,'core/privacy.html')
def forgot_password_page(request):
    from core.browser_auth import forgot_password_page as view
    return view(request)
def reset_password_page(request,token=None):
    from core.browser_auth import reset_password_page as view
    return view(request, token=token)
def verify_email_page(request):
    from core.browser_auth import verify_email_page as view
    return view(request)
def account_identity_page(request):
    from core.browser_auth import account_identity_page as view
    return view(request)

def unlink_google_identity(request):
    from core.browser_auth import unlink_google_identity as view
    return view(request)
def cookie_policy_page(request): return render(request,'core/cookies.html')
def licensing_page(request): return render(request,'core/licensing.html')
def contact_page(request): return render(request,'core/contact.html')
def about_page(request): return render(request,'core/about.html')
def public_status_page(request): return render(request,'core/system_status.html')
@never_cache
def deriv_login(request):
    from django.contrib import messages
    from core.broker_onboarding import has_verified_account_email
    if not request.user.is_authenticated:
        messages.info(request, 'Create or sign in to your AlgoBot account and verify your email before connecting Deriv.')
        return redirect('login_page')
    if not has_verified_account_email(request.user):
        messages.info(request, 'Verify your AlgoBot email before connecting Deriv.')
        return redirect('verify_email_page')
    is_valid,error_message=DerivOAuthService.validate_configuration()
    if not is_valid: logger.error('deriv_oauth_misconfigured',extra={'error':error_message}); return HttpResponse('Deriv OAuth is unavailable. Please try again later.',status=503)
    if request.user.is_authenticated and _deriv_connected(_preferred_deriv_account(request.user)): return redirect('dashboard_page')
    redirect_uri=settings.DERIV_REDIRECT_URI; configured_uri=urlparse(redirect_uri)
    if configured_uri.scheme and configured_uri.netloc and not settings.DEBUG and (request.scheme!=configured_uri.scheme or request.get_host()!=configured_uri.netloc):
        canonical_url=f'{configured_uri.scheme}://{configured_uri.netloc}{request.path}'; canonical_url=f'{canonical_url}?{request.GET.urlencode()}' if request.GET else canonical_url; return redirect(canonical_url)
    try:
        code_verifier,code_challenge=DerivOAuthService.generate_pkce_pair(); state=DerivOAuthService.generate_state(); DerivOAuthService.store_oauth_state_in_session(request,state,code_verifier,redirect_uri); authorization_url=DerivOAuthService.create_authorization_url(state,code_challenge)
    except Exception: logger.exception('deriv_oauth_start_failed'); return HttpResponse('AlgoBot could not start the secure broker connection. Please try again in a moment.',status=503)
    return redirect(authorization_url)
def broker_connect_page(request): return deriv_login(request)
@login_required
def broker_marketplace_page(request):
    from apps.brokers.models import BrokerConnection
    # Populate the built-in directory independently of OAuth/account linking.
    # get_or_create is repeatable and does not overwrite admin-managed records.
    from apps.brokers.services import BrokerManager
    BrokerManager().ensure_defaults()
    brokers = list(Broker.objects.all().order_by('name'))
    active_accounts = BrokerAccount.objects.filter(user=request.user, status='active', token_status='active').select_related('broker').prefetch_related('connections')
    connected_types = set()
    connected_accounts = {}
    for account in active_accounts:
        connection_ok = account.connections.filter(status__in=('connected', 'ready', 'syncing', 'degraded')).exists()
        if connection_ok:
            connected_types.add(account.broker.broker_type)
            connected_accounts.setdefault(account.broker.broker_type, []).append(account)
    for broker in brokers:
        broker.user_connected = broker.broker_type in connected_types
        broker.user_accounts = connected_accounts.get(broker.broker_type, [])
    return render(request, 'core/broker_marketplace.html', {'brokers': brokers})
@login_required

@login_required
@require_POST
def submit_broker_marketplace_request(request):
    """Persist a marketplace request for the broker integration team assistant."""
    try:
        payload = json.loads(request.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"detail": "Invalid request payload."}, status=400)
    provider_name = str(payload.get("provider_name") or "").strip()[:120]
    # Marketplace requests intentionally collect only the broker name. Keep the
    # richer fields optional for older clients and staff-created requests.
    use_case = str(payload.get("use_case") or f"Marketplace request for broker integration: {provider_name}").strip()[:4000]
    provider_website = str(payload.get("provider_website") or "").strip()[:500]
    if not provider_name:
        return JsonResponse({"detail": "Broker name is required."}, status=400)
    if provider_website and not provider_website.startswith(("https://", "http://")):
        return JsonResponse({"detail": "Provider website must start with https:// or http://."}, status=400)
    integration_request = BrokerIntegrationRequest.objects.create(
        provider_name=provider_name,
        provider_website=provider_website,
        requested_by=request.user,
        contact_email=(request.user.email or "")[:254],
        use_case=use_case,
        desired_capabilities=["marketplace_request"],
    )
    return JsonResponse({
        "ok": True,
        "request_id": integration_request.pk,
        "status": integration_request.get_status_display(),
        "message": "Your request was saved for the AlgoBot broker integration team.",
    }, status=201)

def strategy_builder_page(request): return render(request,'core/strategy_builder.html')
@login_required
def operations_module_page(request,module):
    if module == 'brokers':
        # The canonical broker experience is the marketplace; do not render the
        # legacy operations workspace with an uninitialized browser API client.
        return broker_marketplace_page(request)
    if module=='notifications':
        from apps.notifications.channel_service import connection_status
        return render(request,'notifications/channels.html',{'channels':connection_status(request.user)})
    modules={'automation':{'title':'Automation','eyebrow':'WORKFLOW OPERATIONS','description':'Review workflows, execution history and approval controls from the API.','actions':[('Open workflows','/automation/','link')],'endpoints':[('/api/automation/workflows/','Workflows','GET'),('/api/automation/history/','Execution history','GET')]},'brokers':{'title':'Broker accounts','eyebrow':'BROKER OPERATIONS','description':'Manage the connected broker accounts that supply the workspace with trading data.','actions':[('Connect broker','/brokers/connect/','link'),('Browse brokers','/brokers/marketplace/','link')],'endpoints':[('/api/brokers/accounts/','Connected accounts','GET'),('/api/broker-health/','Broker health','GET')]}}
    try: module_config=modules[module]
    except KeyError as exc: raise Http404('Unknown operations module.') from exc
    return render(request,'operations/module_workspace.html',{'module_key':module,'module':module_config,'module_endpoints_json':json.dumps([{'url':u,'label':l,'method':m} for u,l,m in module_config['endpoints']])})
