from celery import shared_task
from .engine import PortfolioEngine
from .models import Portfolio


@shared_task
def update_portfolio_valuation(portfolio_id):
    return PortfolioEngine().portfolios.value_portfolio(Portfolio.objects.get(id=portfolio_id)).id


@shared_task
def calculate_portfolio_performance(portfolio_id, returns=None, equity_curve=None):
    return PortfolioEngine().performance.record(
        Portfolio.objects.get(id=portfolio_id),
        returns if returns is not None else [],
        equity_curve if equity_curve is not None else [],
    ).id


@shared_task
def generate_portfolio_forecast(portfolio_id, returns=None):
    return PortfolioEngine().forecasting.forecast(returns if returns is not None else [])


@shared_task
def generate_scheduled_report(portfolio_id, report_type="daily", export_format="json"):
    return PortfolioEngine().reporting.generate(Portfolio.objects.get(id=portfolio_id), report_type, export_format)
