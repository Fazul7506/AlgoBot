from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.urls import path


urlpatterns = [
    path("", login_required(lambda request: render(request, "smart_money/dashboard.html")), name="smart_money_dashboard"),
    path("heatmap/", login_required(lambda request: render(request, "smart_money/heatmap.html")), name="smart_money_heatmap"),
]
