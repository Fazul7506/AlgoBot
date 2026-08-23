from django.conf import settings
from django.db import models
from .constants import ACCOUNT_STATUS, PORTFOLIO_STATUS


class Portfolio(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="portfolios")
    name = models.CharField(max_length=160)
    currency = models.CharField(max_length=12, default="USD")
    initial_balance = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    current_balance = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    equity = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    net_asset_value = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    status = models.CharField(max_length=24, choices=PORTFOLIO_STATUS, default="active", db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "status"]), models.Index(fields=["currency", "status"])]

    def __str__(self):
        return f"{self.name} ({self.currency})"


class PortfolioAccount(models.Model):
    portfolio = models.ForeignKey(Portfolio, on_delete=models.CASCADE, related_name="accounts")
    broker = models.ForeignKey("brokers.Broker", on_delete=models.PROTECT, related_name="portfolio_accounts")
    broker_account = models.ForeignKey("brokers.BrokerAccount", on_delete=models.PROTECT, related_name="portfolio_links")
    balance = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    equity = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    currency = models.CharField(max_length=12, default="USD")
    status = models.CharField(max_length=24, choices=ACCOUNT_STATUS, default="active")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("portfolio", "broker_account")]
        indexes = [models.Index(fields=["portfolio", "status"]), models.Index(fields=["broker", "currency"])]


class PortfolioAllocation(models.Model):
    portfolio = models.ForeignKey(Portfolio, on_delete=models.CASCADE, related_name="allocations")
    strategy = models.CharField(max_length=160, blank=True, db_index=True)
    symbol = models.CharField(max_length=40, blank=True, db_index=True)
    allocation_percent = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    allocated_capital = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    risk_budget = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = [("portfolio", "strategy", "symbol")]


class PortfolioPerformance(models.Model):
    portfolio = models.ForeignKey(Portfolio, on_delete=models.CASCADE, related_name="performance")
    daily_return = models.DecimalField(max_digits=14, decimal_places=8, default=0)
    weekly_return = models.DecimalField(max_digits=14, decimal_places=8, default=0)
    monthly_return = models.DecimalField(max_digits=14, decimal_places=8, default=0)
    yearly_return = models.DecimalField(max_digits=14, decimal_places=8, default=0)
    cumulative_return = models.DecimalField(max_digits=14, decimal_places=8, default=0)
    drawdown = models.DecimalField(max_digits=14, decimal_places=8, default=0)
    sharpe = models.DecimalField(max_digits=14, decimal_places=8, default=0)
    sortino = models.DecimalField(max_digits=14, decimal_places=8, default=0)
    metrics = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [models.Index(fields=["portfolio", "timestamp"])]


class PortfolioExposure(models.Model):
    portfolio = models.ForeignKey(Portfolio, on_delete=models.CASCADE, related_name="exposures")
    market = models.CharField(max_length=80, blank=True, db_index=True)
    symbol = models.CharField(max_length=40, blank=True, db_index=True)
    strategy = models.CharField(max_length=160, blank=True, db_index=True)
    exposure = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    risk = models.DecimalField(max_digits=14, decimal_places=8, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("portfolio", "market", "symbol", "strategy")]


class PortfolioForecast(models.Model):
    portfolio = models.ForeignKey(Portfolio, on_delete=models.CASCADE, related_name="forecasts")
    forecast_period = models.CharField(max_length=40)
    expected_return = models.DecimalField(max_digits=14, decimal_places=8, default=0)
    expected_drawdown = models.DecimalField(max_digits=14, decimal_places=8, default=0)
    confidence = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    payload = models.JSONField(default=dict, blank=True)
    generated_at = models.DateTimeField(auto_now_add=True, db_index=True)


class CashFlow(models.Model):
    portfolio = models.ForeignKey(Portfolio, on_delete=models.CASCADE, related_name="cashflows")
    deposit = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    withdrawal = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    fees = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    taxes = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    flow_type = models.CharField(max_length=40, default="adjustment")
    metadata = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
