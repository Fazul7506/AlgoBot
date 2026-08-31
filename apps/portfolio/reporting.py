"""Portfolio reporting model."""


class ReportingService:
    def generate(self, portfolio, report_type="executive", export_format="json"):
        nav = float(getattr(portfolio, "net_asset_value", 0) or 0)
        equity = float(getattr(portfolio, "equity", nav) or nav)
        balance = float(getattr(portfolio, "current_balance", balance) or 0)
        initial_balance = float(getattr(portfolio, "initial_balance", 0) or 0)
        total_return = ((nav - initial_balance) / initial_balance) if initial_balance else 0.0

        return {
            "portfolio_name": getattr(portfolio, "name", "Portfolio"),
            "report_type": report_type,
            "format": export_format,
            "nav": nav,
            "equity": equity,
            "balance": balance,
            "total_return": total_return,
            "allocation_count": portfolio.allocations.count() if hasattr(portfolio, "allocations") else 0,
            "performance": getattr(portfolio.performance.first(), "metrics", {}) if hasattr(portfolio, "performance") else {},
        }
