from .models import Alert, BrokerHealth, Incident, LogEntry, Metric, SystemHealth, TraceSpan

class MonitoringRepository:
    models = {"system_health": SystemHealth, "broker_health": BrokerHealth, "alert": Alert, "metric": Metric, "incident": Incident, "log_entry": LogEntry, "trace_span": TraceSpan}

    def latest(self, model_name, limit=100):
        return self.models[model_name].objects.all()[:limit]
