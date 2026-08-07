from decimal import Decimal
from django.db import transaction
from .analytics import AnalyticsService
from .models import CashFlow, Portfolio, PortfolioPerformance


class PortfolioService:
    @transaction.atomic
    def create_portfolio(self, user, name, initial_balance=0, currency="USD"):
        value = Decimal(str(initial_balance))
        return Portfolio.objects.create(user=user, name=name, currency=currency, initial_balance=value, current_balance=value, equity=value, net_asset_value=value)

    def value_portfolio(self, portfolio):
        totals = portfolio.accounts.aggregate_balance if hasattr(portfolio.accounts, "aggregate_balance") else None
        balance = sum(a.balance for a in portfolio.accounts.all()) if portfolio.pk else portfolio.current_balance
        equity = sum(a.equity for a in portfolio.accounts.all()) if portfolio.pk else portfolio.equity
        portfolio.current_balance = balance or portfolio.current_balance
        portfolio.equity = equity or portfolio.equity
        portfolio.net_asset_value = portfolio.equity
        portfolio.save(update_fields=["current_balance", "equity", "net_asset_value", "updated_at"])
        return portfolio


class PerformanceService:
    def record(self, portfolio, returns=None, equity_curve=None):
        metrics = AnalyticsService().calculate(returns=returns, equity_curve=equity_curve)
        return PortfolioPerformance.objects.create(
            portfolio=portfolio,
            daily_return=metrics["daily_return"], weekly_return=metrics["weekly_return"], monthly_return=metrics["monthly_return"],
            yearly_return=metrics["annual_return"], cumulative_return=metrics["roi"], drawdown=metrics["maximum_drawdown"],
            sharpe=metrics["sharpe_ratio"], sortino=metrics["sortino_ratio"], metrics=metrics,
        )


class CashFlowService:
    def record(self, portfolio, deposit=0, withdrawal=0, fees=0, taxes=0, flow_type="adjustment", metadata=None):
        flow = CashFlow.objects.create(portfolio=portfolio, deposit=deposit, withdrawal=withdrawal, fees=fees, taxes=taxes, flow_type=flow_type, metadata=metadata or {})
        portfolio.current_balance = portfolio.current_balance + flow.deposit - flow.withdrawal - flow.fees - flow.taxes
        portfolio.equity = portfolio.current_balance
        portfolio.net_asset_value = portfolio.equity
        portfolio.save(update_fields=["current_balance", "equity", "net_asset_value", "updated_at"])
        return flow
