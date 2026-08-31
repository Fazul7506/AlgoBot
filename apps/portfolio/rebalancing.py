"""Portfolio rebalancing service."""


class RebalancingService:
    def suggestions(self, portfolio, threshold=5):
        suggestions = []
        for allocation in portfolio.allocations.all():
            current = float(allocation.allocation_percent)
            target = float(getattr(allocation, "target_allocation_percent", current) or current)
            delta = abs(current - target)
            if delta > threshold:
                action = "sell" if current > target else "buy"
            else:
                action = "hold"
            suggestions.append({
                "symbol": allocation.symbol,
                "current": current,
                "target": target,
                "delta": delta,
                "action": "rebalance" if delta > threshold else "hold",
                "side": action if delta > threshold else "hold",
            })
        return suggestions or [{"symbol": "cash", "current": 0.0, "target": 0.0, "delta": 0.0, "action": "hold", "side": "hold"}]
