from django.http import JsonResponse
from django.shortcuts import render
from .services import DeveloperPlatformService, SDKService, SandboxService, DocumentationService

def dashboard(request): return render(request, "developer/dashboard.html", DeveloperPlatformService().dashboard())
def keys(request): return JsonResponse({"keys": []})
def plugins(request): return JsonResponse({"plugins": []})
def install_plugin(request): return JsonResponse({"status": "queued"})
def webhooks(request): return JsonResponse({"webhooks": []})
def sdk(request): return JsonResponse({"sdks": SDKService.languages})
def docs(request): return JsonResponse(DocumentationService().publish().payload)
def sandbox(request): return JsonResponse(SandboxService().provision())
