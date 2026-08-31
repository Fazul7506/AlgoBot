"""Cash-flow summary helpers for portfolio accounting."""


class CashFlowService:
    def record(self, portfolio, deposit=0, withdrawal=0, fees=0, taxes=0, flow_type="adjustment", metadata=None):
        metadata = metadata or {}
        total = float(deposit) - float(withdrawal) - float(fees) - float(taxes)
        return {
            "portfolio": getattr(portfolio, "name", "Portfolio"),
            "flow_type": flow_type,
            "deposit": float(deposit),
            "withdrawal": float(withdrawal),
            "fees": float(fees),
            "taxes": float(taxes),
            "net_delta": float(total),
            "metadata": metadata,
        }
