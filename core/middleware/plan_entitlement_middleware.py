"""Server-side subscription enforcement for API/tool usage."""
from __future__ import annotations
from django.http import JsonResponse
from django.utils import timezone
from core.billing_entitlements import EXECUTION_METHODS, EXECUTION_PATH_PREFIXES, check, effective_plan, FEATURE_LABELS, reset_at

def rate_limit_response_data(user, metric, window, current, limit):
    plan=effective_plan(user); reset=reset_at(window); retry_after=max(0,int((reset-timezone.now()).total_seconds())); remaining=None if limit<0 else max(0,limit-current); label=FEATURE_LABELS.get(metric,metric.replace("_"," "))
    return {"detail":f"{label} quota exceeded for the {window} window.","code":"plan_quota_exceeded","metric":metric,"metric_label":label,"window":window,"used":current,"limit":None if limit<0 else limit,"remaining":remaining,"unlimited":limit<0,"reset_at":reset.isoformat(),"retry_after_seconds":retry_after,"plan":plan.key,"plan_name":plan.name,"upgrade_available":plan.key!="ENTERPRISE"}

class PlanEntitlementMiddleware:
    FEATURE_PATHS=(("backtests",("/api/backtesting/",)),("predictions",("/api/ai/","/api/predictions/")),("orders",("/api/orders/",)),("automations",("/api/automation/",)))
    BACKTEST_ACTIONS=("/backtest","/compare","/optimize")
    @staticmethod
    def _is_execution_request(request):
        return request.method.upper() in EXECUTION_METHODS and any(request.path.startswith(prefix) for prefix in EXECUTION_PATH_PREFIXES)
    @classmethod
    def _feature_metric(cls,request):
        method=request.method.upper()
        if method not in EXECUTION_METHODS: return None
        if request.path.startswith("/api/strategies/") and method=="POST":
            return "backtests" if any(action in request.path for action in cls.BACKTEST_ACTIONS) else "strategies"
        for candidate,prefixes in cls.FEATURE_PATHS:
            if any(request.path.startswith(prefix) for prefix in prefixes): return candidate
        return None
    @classmethod
    def _requires_authenticated_user(cls,request): return cls._feature_metric(request) is not None or cls._is_execution_request(request)
    @staticmethod
    def _unauthenticated_response(): return JsonResponse({"detail":"Authentication credentials were not provided.","code":"authentication_required"},status=401)
    def __init__(self,get_response): self.get_response=get_response
    def __call__(self,request):
        is_api=request.path.startswith("/api/"); is_authenticated=bool(getattr(request.user,"is_authenticated",False))
        if not is_api or not is_authenticated: return self.get_response(request)
        is_execution=self._is_execution_request(request); metric=self._feature_metric(request) or "api_calls"
        if is_execution:
            for window,retry in (("day","86400"),("minute","60")):
                allowed,current,limit=check(request.user,"api_calls",1,window)
                if not allowed: return JsonResponse(rate_limit_response_data(request.user,"api_calls",window,current,limit),status=429,headers={"Retry-After":retry})
        if metric!="api_calls":
            allowed,current,limit=check(request.user,metric,1,"day")
            if not allowed: return JsonResponse(rate_limit_response_data(request.user,metric,"day",current,limit),status=429,headers={"Retry-After":"86400"})
        response=self.get_response(request); response["X-AlgoBot-Plan"]=effective_plan(request.user).key; response["X-AlgoBot-Quota-Metric"]=metric if is_execution or metric!="api_calls" else "none"; return response
