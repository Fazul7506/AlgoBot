from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .services import MonitoringEngine

@login_required
def dashboard(request):
    return render(request, "monitoring/dashboard.html", {"dashboard": MonitoringEngine().dashboard()})
