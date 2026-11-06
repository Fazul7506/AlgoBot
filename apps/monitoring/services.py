from __future__ import annotations
import logging, os, time, uuid
from dataclasses import dataclass
from typing import Any
from django.core.cache import cache
from django.db import connection
from django.utils import timezone
from .constants import DEFAULT_THRESHOLDS
from .models import Alert, AuditLog, BrokerHealth, Incident, LogEntry, Metric, SystemHealth, TraceSpan
logger=logging.getLogger(__name__)
@dataclass(frozen=True)
class HealthCheckResult: service_name:str; status:str; response_time:float; details:dict[str,Any]
class HealthMonitoringService:
    monitored_services=["Application","Database","Redis","Celery","WebSocket","Broker","Trading Engine","Strategy Engine","AI Engine","Risk Engine","Backtesting Engine","API","Authentication","Storage","Cache"]
    def check_service(self,service_name):
        started=time.perf_counter(); status="healthy"; details={}
        try:
            if service_name=="Database":
                with connection.cursor() as cursor: cursor.execute("SELECT 1"); details["database"]=cursor.fetchone()[0]
            elif service_name in {"Redis","Cache"}: cache.set("monitoring:health","ok",10); details["cache"]=cache.get("monitoring:health")
            elif service_name=="Storage": details["cwd_writable"]=os.access(os.getcwd(),os.W_OK)
        except Exception as exc: status="down"; details["error"]=str(exc)
        ms=(time.perf_counter()-started)*1000; SystemHealth.objects.create(service_name=service_name,status=status,response_time=ms,details=details); return HealthCheckResult(service_name,status,ms,details)
    def run_checks(self): return [self.check_service(s) for s in self.monitored_services]
    def latest(self): return SystemHealth.objects.order_by("service_name","-timestamp").distinct("service_name") if connection.vendor=="postgresql" else SystemHealth.objects.all()[:50]
class BrokerMonitoringService:
    def record(self,broker,**kwargs): return BrokerHealth.objects.create(broker=broker,**kwargs)
    def disconnected(self,broker): self.record(broker,connection_status="down",websocket_status="down",api_status="down",last_ping=timezone.now()); return AlertEngine().create_alert("Broker disconnected","Broker","CRITICAL",f"{broker} connection is down",broker)
class TradingMonitoringService:
    """Account-scoped trading telemetry derived from broker-authoritative records."""

    def snapshot(self, user=None):
        from datetime import timedelta
        from django.db.models import Avg, Count, Q
        from django.utils import timezone
        from apps.brokers.models import BrokerAccount, ExecutionReport, Order, Position

        accounts = BrokerAccount.objects.filter(status="active")
        if user is not None:
            accounts = accounts.filter(user=user)
        account_ids = accounts.values_list("id", flat=True)
        positions = Position.objects.filter(account_id__in=account_ids)
        orders = Order.objects.filter(account_id__in=account_ids)
        closed = positions.filter(status__iexact="closed")
        terminal_orders = orders.filter(status__in=(
            "executed", "filled", "closed", "reconciled", "rejected", "expired", "cancelled", "failed",
        ))
        terminal_counts = terminal_orders.aggregate(
            successful=Count("id", filter=Q(status__in=("executed", "filled", "closed", "reconciled"))),
            total=Count("id"),
        )
        latency = ExecutionReport.objects.filter(order__account_id__in=account_ids).aggregate(
            value=Avg("latency")
        )["value"]
        profit = {
            "wins": closed.filter(profit__gt=0).count(),
            "losses": closed.filter(profit__lt=0).count(),
            "average_win": closed.filter(profit__gt=0).aggregate(value=Avg("profit"))["value"],
            "average_loss": closed.filter(profit__lt=0).aggregate(value=Avg("profit"))["value"],
        }
        now = timezone.now()
        return {
            "trades_per_minute": positions.filter(opened_at__gte=now - timedelta(minutes=1)).count(),
            "open_positions": positions.filter(status__iexact="open").count(),
            "closed_positions": closed.count(),
            "pending_orders": orders.filter(status__in=(
                "created", "validated", "approved", "queued", "submitted", "pending", "partially_filled",
            )).count(),
            "execution_latency": round(float(latency), 2) if latency is not None else None,
            "rejected_orders": orders.filter(status="rejected").count(),
            "success_rate": (
                round(100 * terminal_counts["successful"] / terminal_counts["total"], 2)
                if terminal_counts["total"] else None
            ),
            "average_profit": profit["average_win"],
            "average_loss": profit["average_loss"],
        }


class StrategyMonitoringService:
    """Strategy activity counts are scoped through each user's configuration."""

    def snapshot(self, user=None):
        from apps.strategies.models import StrategyConfiguration, StrategyExecution, StrategySignal

        configurations = StrategyConfiguration.objects.all()
        executions = StrategyExecution.objects.filter(configuration__isnull=False)
        signals = StrategySignal.objects.filter(configuration__isnull=False)
        if user is not None:
            configurations = configurations.filter(user=user)
            executions = executions.filter(configuration__user=user)
            signals = signals.filter(configuration__user=user)
        return {
            "running_strategies": configurations.filter(enabled=True, is_active=True).count(),
            "paused_strategies": configurations.filter(enabled=True, is_active=False).count(),
            "stopped_strategies": configurations.filter(enabled=False).count(),
            "signals_generated": signals.count(),
            # StrategyExecution records are not settled trades; win/loss and
            # profit metrics must come from a reconciled performance ledger.
            "win_rate": None,
            "loss_rate": None,
            "profit_factor": None,
            "performance_drift": None,
            "strategy_errors": executions.filter(status="failed").count(),
        }


class RiskMonitoringService:
    """Reuse the risk domain's account-aware calculations; do not invent P&L."""

    def snapshot(self, user=None):
        if user is None:
            return {
                "current_drawdown": None, "portfolio_risk": None, "exposure": None,
                "margin": None, "daily_loss": None, "daily_profit": None,
                "risk_score": None, "circuit_breakers": None,
            }
        from apps.risk.services import RiskMonitoringService as RiskDomainService

        data = RiskDomainService().dashboard(user)
        return {
            "current_drawdown": data.get("current_drawdown"),
            "portfolio_risk": data.get("risk_score"),
            "exposure": data.get("portfolio_exposure"),
            "margin": data.get("margin_level"),
            "daily_loss": None,
            "daily_profit": data.get("today_profit_loss"),
            "risk_score": data.get("risk_score"),
            "circuit_breakers": data.get("circuit_breaker_status"),
        }


class AIMonitoringService:
    """Model and prediction quality from persisted, resolved prediction outcomes."""

    def snapshot(self, user=None):
        from django.db.models import Count, Q
        from apps.ai_engine.models import AIModel, Prediction, PredictionOutcome, TrainingJob

        predictions = Prediction.objects.all()
        training = TrainingJob.objects.all()
        if user is not None:
            predictions = predictions.filter(user=user)
            training = training.filter(Q(user=user) | Q(user__isnull=True))
        outcomes = PredictionOutcome.objects.filter(
            prediction__in=predictions, correct__isnull=False,
        )
        outcome_counts = outcomes.aggregate(
            correct=Count("id", filter=Q(correct=True)),
            total=Count("id"),
        )
        model = AIModel.objects.filter(status="champion").order_by("-created_at").first()
        latest_training = training.order_by("-started_at", "-id").first()
        total = outcome_counts["total"]
        return {
            "predictions_generated": predictions.count(),
            "prediction_latency": None,
            "prediction_accuracy": round(100 * outcome_counts["correct"] / total, 2) if total else None,
            "model_drift": None,
            "feature_drift": None,
            "training_status": latest_training.status if latest_training else None,
            "inference_errors": None,
            "champion_model": str(model) if model else None,
            "memory_usage": None,
            "gpu_usage": None,
        }


class InfrastructureMonitoringService:
    """Expose only host metrics that this process can actually measure."""

    def snapshot(self):
        import shutil
        from django.conf import settings
        from django.db import connection
        from django.core.cache import cache

        cpu = os.getloadavg()[0] if hasattr(os, "getloadavg") else None
        memory = None
        try:
            pages = os.sysconf("SC_PHYS_PAGES")
            available = os.sysconf("SC_AVPHYS_PAGES")
            memory = round(100 * (1 - available / pages), 2) if pages else None
        except (AttributeError, OSError, ValueError):
            pass
        try:
            disk = shutil.disk_usage(os.getcwd())
            disk_percent = round(100 * disk.used / disk.total, 2) if disk.total else None
        except OSError:
            disk_percent = None
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            database = "healthy"
        except Exception:
            database = "down"
        cache_backend = str(
            settings.CACHES.get("default", {}).get("BACKEND", "")
        ).lower()
        if "redis" not in cache_backend:
            redis_status = "not_configured"
        else:
            try:
                key = "monitoring:infrastructure-probe"
                cache.set(key, "ok", timeout=5)
                redis_status = "healthy" if cache.get(key) == "ok" else "degraded"
            except Exception:
                redis_status = "down"
        return {
            "cpu": cpu, "memory": memory, "disk": disk_percent,
            "database": database, "redis": redis_status,
            "network": None, "bandwidth": None, "threads": None,
            "processes": None, "docker": None, "workers": None,
            "celery": None, "gpu": None, "temperature": None,
        }
class MetricsService:
    def record(self,metric_name,value,unit="",module="application",tags=None): return Metric.objects.create(metric_name=metric_name,value=value,unit=unit,module=module,tags=tags or {})
    def collect_application_metrics(self):
        metrics={"database_queries":len(connection.queries)}
        for name,value in metrics.items(): self.record(name,float(value),module="application")
        return metrics
class AlertEngine:
    def create_alert(self,title,category,severity,message,source,metadata=None): return Alert.objects.create(title=title,category=category,severity=severity,message=message,source=source,metadata=metadata or {})
    def evaluate(self,payload):
        alerts=[]
        for key,title in (("cpu","High CPU usage"),("memory","Memory critical"),("disk","Disk nearly full")):
            value=payload.get(key)
            if value is not None and float(value)>=DEFAULT_THRESHOLDS[key]: alerts.append(self.create_alert(title,"Infrastructure","HIGH",f"{key} reached {value}","monitoring",{"metric":key}))
        if payload.get("broker_connection")=="down": alerts.append(self.create_alert("Broker disconnected","Broker","CRITICAL","Broker connectivity lost","broker"))
        if payload.get("database")=="down": alerts.append(self.create_alert("Database unavailable","Database","EMERGENCY","Database health check failed","database"))
        return alerts
    def acknowledge(self,alert_id): alert=Alert.objects.get(pk=alert_id); alert.acknowledge(); return alert
class IncidentService:
    def create_from_alert(self,alert,assigned_to=None): return Incident.objects.create(title=alert.title,severity=alert.severity,alert=alert,assigned_to=assigned_to)
    def resolve(self,incident_id,root_cause="",postmortem=""):
        incident=Incident.objects.get(pk=incident_id); incident.status="resolved"; incident.resolved_at=timezone.now(); incident.root_cause=root_cause; incident.postmortem=postmortem; incident.save(update_fields=["status","resolved_at","root_cause","postmortem"]); return incident
class AuditService:
    def record(self,action,module,user=None,resource="",old_value=None,new_value=None,ip_address=None): return AuditLog.objects.create(user=user,action=action,module=module,resource=resource,old_value=old_value,new_value=new_value,ip_address=ip_address)
class LogAggregationService:
    def ingest(self,stream,level,message,source="",context=None): return LogEntry.objects.create(stream=stream,level=level,message=message,source=source,context=context or {})
    def search(self,query="",stream=None):
        qs=LogEntry.objects.all(); qs=qs.filter(stream=stream) if stream else qs; qs=qs.filter(message__icontains=query) if query else qs; return qs[:500]
class TracingService:
    def start_span(self,operation,module,trace_id=None,parent_span_id="",**attributes): return TraceSpan.objects.create(trace_id=trace_id or uuid.uuid4().hex,span_id=uuid.uuid4().hex,parent_span_id=parent_span_id,operation=operation,module=module,attributes=attributes)
    def finish_span(self,span,status="ok"): span.duration_ms=(timezone.now()-span.started_at).total_seconds()*1000; span.status=status; span.save(update_fields=["duration_ms","status"]); return span
class NotificationService:
    channels=["in_app","email","telegram","discord","slack","sms","push","webhook"]
    def send(self,channel,title,message,target="",payload=None):
        if channel not in self.channels: return {"channel":channel,"delivered":False,"status":"unsupported"}
        logger.info("notification requested channel=%s title=%s target=%s",channel,title,target); return {"channel":channel,"title":title,"target":target,"delivered":False,"status":"queued_only","payload":payload or {}}
class SelfHealingService:
    def execute(self,action,target,payload=None):
        allowed={"restart_celery","reconnect_websocket","reconnect_broker","restart_service","flush_cache","clear_queues","retry_failed_tasks","restart_monitoring","reload_strategies","reload_ai_models"}
        if action not in allowed: return {"action":action,"target":target,"status":"rejected"}
        if action=="flush_cache": cache.clear()
        LogAggregationService().ingest("infrastructure","INFO",f"self-healing request {action} for {target}","self-healing",payload or {}); return {"action":action,"target":target,"status":"requested","timestamp":timezone.now().isoformat()}
class MonitoringEngine:
    def __init__(self):
        self.health = HealthMonitoringService()
        self.broker = BrokerMonitoringService()
        self.trading = TradingMonitoringService()
        self.strategy = StrategyMonitoringService()
        self.risk = RiskMonitoringService()
        self.ai = AIMonitoringService()
        self.infrastructure = InfrastructureMonitoringService()
        self.metrics = MetricsService()
        self.alerts = AlertEngine()

    def dashboard(self, user=None):
        from django.db.models import Q
        from apps.brokers.models import BrokerAccount, BrokerConnection

        health = SystemHealth.objects.order_by("-timestamp").first()
        accounts = BrokerAccount.objects.filter(status="active")
        if user is not None:
            accounts = accounts.filter(user=user)
        account_ids = accounts.values_list("id", flat=True)
        latest_connection = BrokerConnection.objects.filter(
            broker_account_id__in=account_ids
        ).order_by("-updated_at").first()
        broker_status = (
            "connected" if BrokerConnection.objects.filter(
                broker_account_id__in=account_ids, status="connected"
            ).exists() else latest_connection.status if latest_connection else "not_connected"
        )
        trading = self.trading.snapshot(user=user)
        strategy = self.strategy.snapshot(user=user)
        risk = self.risk.snapshot(user=user)
        ai = self.ai.snapshot(user=user)
        alerts = Alert.objects.exclude(status="resolved")
        incidents = Incident.objects.exclude(status="resolved")
        if user is not None:
            alerts = alerts.filter(user=user)
            incidents = incidents.filter(Q(assigned_to=user) | Q(alert__user=user)).distinct()

        system_health = health.status if health else None
        if user is not None and not getattr(user, "is_staff", False):
            # Trader accounts receive their own account state, not global
            # infrastructure or internal engine diagnostics.
            system_health = "available"

        return {
            "overall_system_health": system_health,
            "broker_status": broker_status,
            "current_drawdown": risk.get("current_drawdown"),
            "active_alerts": alerts.count(),
            "open_incidents": incidents.count(),
            "current_trades": trading["open_positions"],
            "current_predictions": ai["predictions_generated"],
            "trading": trading,
            "strategy": strategy,
            "ai": ai,
            "risk": risk,
        }

    def collect(self):
        health = self.health.run_checks()
        metrics = self.metrics.collect_application_metrics()
        alerts = self.alerts.evaluate({})
        return {"health_checks": len(health), "metrics": metrics, "alerts": len(alerts)}
