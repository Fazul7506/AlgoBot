from apps.developer.services import APIKeyService, SDKService, WebhookService


def test_api_key_generation_and_webhook_signing():
    key = APIKeyService().generate(["read", "trading"])
    assert key["key"].startswith("ak_")
    assert "Python" in SDKService.languages
    assert WebhookService().sign("secret", "payload")
