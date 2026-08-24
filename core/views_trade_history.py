from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def trade_history_page(request):
    return render(request, 'core/trade_history.html')
