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
    def snapshot(self): return {"trades_per_minute":None,"open_positions":None,"closed_positions":None,"pending_orders":None,"execution_latency":None,"rejected_orders":None,"success_rate":None,"average_profit":None,"average_loss":None}
class StrategyMonitoringService:
    def snapshot(self): return {"running_strategies":None,"paused_strategies":None,"stopped_strategies":None,"signals_generated":None,"win_rate":None,"loss_rate":None,"profit_factor":None,"performance_drift":None,"strategy_errors":None}
class RiskMonitoringService:
    def snapshot(self): return {"current_drawdown":None,"portfolio_risk":None,"exposure":None,"margin":None,"daily_loss":None,"daily_profit":None,"risk_score":None,"circuit_breakers":None,"kill_switch_status":"unknown"}
class AIMonitoringService:
    def snapshot(self): return {"prediction_latency":None,"prediction_accuracy":None,"model_drift":None,"feature_drift":None,"training_status":"unknown","inference_errors":None,"champion_model":None,"memory_usage":None,"gpu_usage":None}
class InfrastructureMonitoringService:
    def snapshot(self): return {"cpu":os.getloadavg()[0] if hasattr(os,"getloadavg") else None,"memory":None,"disk":None,"database":"unknown","redis":"unknown","network":None,"bandwidth":None,"threads":None,"processes":None,"docker":"unknown","workers":None,"celery":"unknown","gpu":None,"temperature":None}
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
    def __init__(self): self.health=HealthMonitoringService(); self.broker=BrokerMonitoringService(); self.trading=TradingMonitoringService(); self.strategy=StrategyMonitoringService(); self.risk=RiskMonitoringService(); self.ai=AIMonitoringService(); self.infrastructure=InfrastructureMonitoringService(); self.metrics=MetricsService(); self.alerts=AlertEngine()
    def dashboard(self):
        health=SystemHealth.objects.order_by("-timestamp").first(); broker=BrokerHealth.objects.order_by("-last_ping").first()
        return {"overall_system_health":health.status if health else "unknown","broker_status":broker.connection_status if broker else "unknown","trading_engine_status":"unknown","strategy_engine_status":"unknown","ai_engine_status":"unknown","risk_engine_status":"unknown","current_cpu_usage":None,"current_memory_usage":None,"current_network_usage":None,"current_drawdown":None,"active_alerts":Alert.objects.exclude(status="resolved").count(),"open_incidents":Incident.objects.exclude(status="resolved").count(),"active_users":None,"current_trades":None,"current_predictions":None,"queue_health":"unknown"}
    def collect(self): health=self.health.run_checks(); metrics=self.metrics.collect_application_metrics(); alerts=self.alerts.evaluate({}); return {"health_checks":len(health),"metrics":metrics,"alerts":len(alerts)}
