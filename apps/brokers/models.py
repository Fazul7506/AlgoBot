from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from core.services.encryption_service import CredentialEncryptionService
from . import constants as c

choices = lambda xs: [(x, x.replace('_', ' ').title()) for x in xs]


class Broker(models.Model):
    name = models.CharField(max_length=120, unique=True)
    broker_type = models.CharField(max_length=40, choices=choices(c.BROKER_TYPES), db_index=True)
    status = models.CharField(max_length=24, choices=choices(c.BROKER_STATUSES), default='active', db_index=True)
    version = models.CharField(max_length=40, blank=True)
    api_endpoint = models.URLField(blank=True)
    websocket_endpoint = models.URLField(blank=True)
    supports_demo = models.BooleanField(default=True)
    supports_live = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.broker_type})'


class BrokerAccount(models.Model):
    TOKEN_STATUS_CHOICES = [
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('revoked', 'Revoked'),
        ('refreshing', 'Refreshing'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='multi_broker_accounts')
    broker = models.ForeignKey(Broker, on_delete=models.CASCADE, related_name='broker_accounts')
    account_id = models.CharField(max_length=120)
    currency = models.CharField(max_length=12, default='USD')
    balance = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    equity = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    margin = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    free_margin = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    status = models.CharField(max_length=24, choices=choices(c.ACCOUNT_STATUSES), default='active')
    is_preferred = models.BooleanField(default=False)
    credentials = models.JSONField(default=dict, blank=True)
    access_token = models.TextField(blank=True)
    refresh_token = models.TextField(blank=True)
    token_status = models.CharField(max_length=20, choices=TOKEN_STATUS_CHOICES, default='active', db_index=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_refresh = models.DateTimeField(null=True, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('broker', 'account_id')]
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['broker', 'is_preferred']),
            models.Index(fields=['user', 'token_status']),
        ]

    def __str__(self):
        return f'{self.broker.broker_type}:{self.account_id}'

    def set_access_token(self, token: str) -> None:
        self.access_token = CredentialEncryptionService().encrypt(token or '')

    def get_access_token(self) -> str:
        if not self.access_token:
            return ''
        return CredentialEncryptionService().decrypt(self.access_token) or ''

    def set_refresh_token(self, token: str) -> None:
        self.refresh_token = CredentialEncryptionService().encrypt(token or '')

    def get_refresh_token(self) -> str:
        if not self.refresh_token:
            return ''
        return CredentialEncryptionService().decrypt(self.refresh_token) or ''

    @property
    def is_token_expired(self) -> bool:
        return bool(self.expires_at and self.expires_at <= timezone.now())

    @property
    def credential_status(self) -> str:
        """Return a safe, non-secret readiness status for this account."""
        auth_type = str((self.broker.metadata or {}).get('auth') or '').lower()
        requires_oauth = self.broker.broker_type == 'deriv' or auth_type == 'oauth'
        if not requires_oauth:
            return 'ready'
        if self.token_status != 'active' or self.is_token_expired:
            return 'credentials_expired'
        access_token = self.get_access_token()
        if not access_token or access_token == self.access_token:
            return 'credentials_unavailable'
        return 'ready'

    @property
    def is_connection_eligible(self) -> bool:
        return (
            self.status == 'active'
            and self.broker.status == 'active'
            and self.credential_status == 'ready'
        )


class BrokerConnection(models.Model):
    # Keep broker for compatibility with existing rows and broker-level
    # queries. Account-scoped state is authoritative for user-facing status.
    broker = models.ForeignKey(Broker, on_delete=models.CASCADE, related_name='connections')
    broker_account = models.ForeignKey(
        BrokerAccount,
        on_delete=models.CASCADE,
        related_name='connections',
        null=True,
        blank=True,
    )
    status = models.CharField(max_length=24, choices=choices(c.CONNECTION_STATUSES), default='disconnected')
    latency = models.FloatField(default=0)
    last_ping = models.DateTimeField(null=True, blank=True)
    heartbeat = models.JSONField(default=dict, blank=True)
    connected_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['broker', 'status']),
            models.Index(fields=['broker_account', 'status']),
            models.Index(fields=['last_ping']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['broker_account'],
                condition=Q(broker_account__isnull=False),
                name='unique_broker_connection_per_account',
            ),
        ]


class BrokerConnectionLog(models.Model):
    broker_account = models.ForeignKey(BrokerAccount, on_delete=models.CASCADE, related_name='connection_logs')
    status = models.CharField(max_length=50)
    latency = models.FloatField(null=True, blank=True)
    event = models.CharField(max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['broker_account', '-created_at']), models.Index(fields=['event'])]


class BrokerPermission(models.Model):
    broker = models.ForeignKey(Broker, on_delete=models.CASCADE, related_name='permissions')
    permission = models.CharField(max_length=80)
    enabled = models.BooleanField(default=True)

    class Meta:
        unique_together = [('broker', 'permission')]


class Order(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='broker_orders')
    broker = models.ForeignKey(Broker, on_delete=models.PROTECT, related_name='orders')
    account = models.ForeignKey(BrokerAccount, on_delete=models.PROTECT, related_name='orders')
    strategy = models.CharField(max_length=120, blank=True)
    symbol = models.CharField(max_length=40, db_index=True)
    direction = models.CharField(max_length=16, choices=choices(c.DIRECTIONS))
    order_type = models.CharField(max_length=32, choices=choices(c.ORDER_TYPES), default='market')
    contract_type = models.CharField(max_length=40, choices=choices(c.CONTRACT_TYPES), blank=True)
    stake = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    quantity = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    price = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    status = models.CharField(max_length=32, choices=choices(c.ORDER_STATUSES), default='created', db_index=True)
    client_order_id = models.CharField(max_length=100, blank=True, db_index=True)
    broker_order_id = models.CharField(max_length=120, blank=True, db_index=True)
    routing_context = models.JSONField(default=dict, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    executed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['broker', 'status']),
            models.Index(fields=['account', 'status']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'account', 'client_order_id'],
                condition=~Q(client_order_id=''),
                name='unique_client_order_id_per_account',
            ),
        ]


class ExecutionReport(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='execution_reports')
    execution_price = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    requested_price = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    slippage = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    latency = models.FloatField(default=0)
    fees = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    status = models.CharField(max_length=32, choices=choices(c.ORDER_STATUSES), default='submitted')
    raw_report = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Position(models.Model):
    broker = models.ForeignKey(Broker, on_delete=models.PROTECT, related_name='positions')
    account = models.ForeignKey(BrokerAccount, on_delete=models.PROTECT, related_name='positions')
    symbol = models.CharField(max_length=40, db_index=True)
    direction = models.CharField(max_length=16, choices=choices(c.DIRECTIONS))
    size = models.DecimalField(max_digits=20, decimal_places=8)
    entry_price = models.DecimalField(max_digits=20, decimal_places=8)
    current_price = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    profit = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    status = models.CharField(max_length=24, default='open', db_index=True)
    opened_at = models.DateTimeField(default=timezone.now)
    closed_at = models.DateTimeField(null=True, blank=True)


class TradeReconciliation(models.Model):
    broker = models.ForeignKey(Broker, on_delete=models.CASCADE, related_name='reconciliations')
    trade = models.JSONField(default=dict, blank=True)
    matched = models.BooleanField(default=False)
    difference = models.JSONField(default=dict, blank=True)
    repaired = models.BooleanField(default=False)
    timestamp = models.DateTimeField(auto_now_add=True)
