from importlib import import_module

from .models import BrokerAccount


class BrokerManager:
    """Factory for broker adapters; keeps vendor dependencies at the edge."""

    adapter_paths = {
        "paper": "apps.broker.adapters.PaperBrokerAdapter",
    }

    def register_adapter(self, slug: str, dotted_path: str) -> None:
        self.adapter_paths[slug] = dotted_path

    def get_adapter(self, account: BrokerAccount):
        dotted_path = self.adapter_paths.get(account.broker.slug)
        if not dotted_path:
            raise ValueError(f"Unsupported broker: {account.broker.slug}")
        module_path, class_name = dotted_path.rsplit(".", 1)
        adapter_cls = getattr(import_module(module_path), class_name)
        return adapter_cls(broker=account.broker, account=account, credentials=getattr(account, "credentials", {}))
