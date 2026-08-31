"""Portfolio manager helpers."""


class PortfolioManager:
    def __init__(self, portfolio=None):
        self.portfolio = portfolio

    def current_state(self):
        if self.portfolio is None:
            return {}
        return {
            "name": getattr(self.portfolio, "name", "Portfolio"),
            "nav": float(getattr(self.portfolio, "net_asset_value", 0) or 0),
            "equity": float(getattr(self.portfolio, "equity", 0) or 0),
        }
