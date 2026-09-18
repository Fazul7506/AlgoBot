from django.urls import path
from . import views

urlpatterns = [
    path("data/", views.analysis_data, name="analysis-data"),
    path("markets/", views.analysis_markets, name="analysis-markets"),
    path("contracts/", views.analysis_contracts, name="analysis-contracts"),
    path("account-context/", views.broker_account_context, name="broker-account-context"),
    path("proposal/", views.broker_proposal, name="broker-proposal"),
]
