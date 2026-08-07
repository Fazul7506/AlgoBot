from decimal import Decimal
from .exceptions import AllocationError
from .models import PortfolioAllocation


class AllocationService:
    def allocate(self, portfolio, targets, method="percentage"):
        if not targets:
            raise AllocationError("At least one allocation target is required.")
        if method == "equal_weight":
            weight = Decimal("100") / Decimal(len(targets))
            targets = [{**target, "allocation_percent": weight} for target in targets]
        total = sum(Decimal(str(t.get("allocation_percent", 0))) for t in targets)
        if total > Decimal("100.000001"):
            raise AllocationError("Allocation percent cannot exceed 100%.")
        created = []
        for target in targets:
            pct = Decimal(str(target.get("allocation_percent", 0)))
            capital = portfolio.net_asset_value * pct / Decimal("100")
            obj, _ = PortfolioAllocation.objects.update_or_create(
                portfolio=portfolio, strategy=target.get("strategy", ""), symbol=target.get("symbol", ""),
                defaults={"allocation_percent": pct, "allocated_capital": capital, "risk_budget": target.get("risk_budget", 0), "metadata": {"method": method}},
            )
            created.append(obj)
        return created
