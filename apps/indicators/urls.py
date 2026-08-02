from django.urls import path
from . import views
urlpatterns=[
 path('indicators/', views.IndicatorListAPIView.as_view(), name='indicator-list'),
 path('indicators/<str:symbol>/', views.SymbolIndicatorAPIView.as_view(), name='indicator-symbol'),
 path('analysis/trend/', views.TrendAPIView.as_view(), name='analysis-trend'),
 path('analysis/patterns/', views.PatternAPIView.as_view(), name='analysis-patterns'),
 path('analysis/support-resistance/', views.SupportResistanceAPIView.as_view(), name='analysis-support-resistance'),
 path('analysis/volatility/', views.VolatilityAPIView.as_view(), name='analysis-volatility'),
]
