from .models import Contract
class ContractRepository:
    def create(self, **data): return Contract.objects.create(**data)
    def active(self): return Contract.objects.exclude(status__in=['expired','sold'])
