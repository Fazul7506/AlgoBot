from django.shortcuts import render
from .services import MonitoringEngine

def dashboard(request):
    return render(request, "monitoring/dashboard.html", {"dashboard": MonitoringEngine().dashboard()})
