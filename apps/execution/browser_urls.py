from django.urls import path
from .views import OrderViewSet

browser_preview_view = OrderViewSet.as_view({'post': 'preview'})
browser_order_view = OrderViewSet.as_view({'post': 'create'})

urlpatterns = [
    path('actions/preview/', browser_preview_view, name='browser-trading-preview'),
    path('actions/order/', browser_order_view, name='browser-trading-order'),
]
