from .models import Contract
class ContractManager:
    def active_contracts(self): return Contract.objects.exclude(status__in=['expired','sold'])
