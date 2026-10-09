from decimal import Decimal, InvalidOperation, ROUND_DOWN

from django.db import transaction

from .exceptions import AllocationError
from .models import PortfolioAllocation


class AllocationService:
    METHODS = {"percentage", "equal_weight"}

    @staticmethod
    def _decimal(value, field, *, maximum=None):
        try:
            result = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise AllocationError(f"{field} must be a finite number.") from exc
        if not result.is_finite() or result < 0 or (maximum is not None and result > maximum):
            bound = f" between 0 and {maximum}" if maximum is not None else " greater than or equal to 0"
            raise AllocationError(f"{field} must be{bound}.")
        return result

    def allocate(self, portfolio, targets, method="percentage"):
        if method not in self.METHODS:
            raise AllocationError("Unsupported allocation method.")
        if not isinstance(targets, (list, tuple)) or not targets:
            raise AllocationError("At least one allocation target is required.")
        if any(not isinstance(target, dict) for target in targets):
            raise AllocationError("Each allocation target must be an object.")

        clean_targets = []
        seen = set()
        for index, target in enumerate(targets):
            strategy = target.get("strategy", "")
            symbol = target.get("symbol", "")
            if not isinstance(strategy, str) or not isinstance(symbol, str):
                raise AllocationError("Strategy and symbol must be text.")
            strategy, symbol = strategy.strip(), symbol.strip()
            if len(strategy) > 160 or len(symbol) > 40:
                raise AllocationError("Strategy or symbol exceeds the supported length.")
            identity = (strategy, symbol)
            if identity in seen:
                raise AllocationError("Duplicate strategy/symbol allocation targets are not allowed.")
            seen.add(identity)
            pct = self._decimal(target.get("allocation_percent", 0), f"targets[{index}].allocation_percent", maximum=Decimal("100"))
            pct = pct.quantize(Decimal("0.000001"))
            risk_budget = self._decimal(target.get("risk_budget", 0), f"targets[{index}].risk_budget", maximum=Decimal("100"))
            risk_budget = risk_budget.quantize(Decimal("0.000001"))
            clean_targets.append({
                "strategy": strategy,
                "symbol": symbol,
                "allocation_percent": pct,
                "risk_budget": risk_budget,
            })

        if method == "equal_weight":
            quantum = Decimal("0.000001")
            weight = (Decimal("100") / Decimal(len(clean_targets))).quantize(quantum, rounding=ROUND_DOWN)
            for target in clean_targets[:-1]:
                target["allocation_percent"] = weight
            clean_targets[-1]["allocation_percent"] = Decimal("100") - weight * Decimal(len(clean_targets) - 1)

        total = sum(target["allocation_percent"] for target in clean_targets)
        if total > Decimal("100.000001"):
            raise AllocationError("Allocation percent cannot exceed 100%.")

        created = []
        with transaction.atomic():
            for target in clean_targets:
                pct = target["allocation_percent"]
                capital = portfolio.net_asset_value * pct / Decimal("100")
                obj, _ = PortfolioAllocation.objects.update_or_create(
                    portfolio=portfolio,
                    strategy=target["strategy"],
                    symbol=target["symbol"],
                    defaults={
                        "allocation_percent": pct,
                        "allocated_capital": capital,
                        "risk_budget": target["risk_budget"],
                        "metadata": {"method": method},
                    },
                )
                created.append(obj)
        return created
