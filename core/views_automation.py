from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def workflow_templates_page(request):
    return render(request, 'automation/workflow_templates.html')
