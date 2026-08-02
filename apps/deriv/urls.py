from django.urls import path
from . import views
urlpatterns = [path("deriv/balance/", views.balance), path("deriv/history/", views.history), path("deriv/portfolio/", views.portfolio)]
