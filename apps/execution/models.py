from django.conf import settings
from django.db import models
from django.utils import timezone
from . import constants as c


class Order(models.Model):
    ORDER_TYPE_CHOICES = [(v, v.replace('_', ' ').title()) for v in c.ORDER_TYPES]
    DIRECTION_CHOICES = [(v, v.title()) for v in c.DIRECTIONS]
    STATUS_CHOICES = [(v, v.replace('_', ' ').title()) for v in [c.ORDER_STATUS_DRAFT, c.ORDER_STATUS_VALIDATED, c.ORDER_STATUS_QUEUED, c.ORDER_STATUS_SENT, c.ORDER_STATUS_ACCEPTED, c.ORDER_STATUS_EXECUTED, c.ORDER_STATUS_ARCHIVED, c.ORDER_STATUS_FAILED, c.ORDER_STATUS_CANCELLED]]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='execution_orders')
    broker_account = models.ForeignKey('brokers.BrokerAccount', on_delete=models.PROTECT, related_name='execution_orders')
    symbol = models.CharField(max_length=40)
    strategy = models.CharField(max_length=120, blank=True)
    direction = models.CharField(max_length=12, choices=DIRECTION_CHOICES)
    order_type = models.CharField(max_length=32, choices=ORDER_TYPE_CHOICES, default='market')
    contract_type = models.CharField(max_length=40, blank=True)
    duration = models.PositiveIntegerField(null=True, blank=True)
    duration_unit = models.CharField(max_length=1, blank=True)
    stake = models.DecimalField(max_digits=18, decimal_places=8)
    price = models.DecimalField(max_digits=18, decimal_places=8, null=True, blank=True)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=c.ORDER_STATUS_DRAFT)
    broker_reference = models.CharField(max_length=160, blank=True, db_index=True)
    client_request_id = models.CharField(max_length=80, blank=True, db_index=True)
    validation_context = models.JSONField(default=dict, blank=True)
    broker_payload = models.JSONField(default=dict, blank=True)
    broker_response = models.JSONField(default=dict, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    executed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['user', 'status']), models.Index(fields=['broker_account', 'symbol']), models.Index(fields=['broker_account', 'contract_type'])]
        constraints = [models.UniqueConstraint(fields=['user', 'client_request_id'], condition=~models.Q(client_request_id=''), name='unique_execution_client_request')]
    def __str__(self): return f'{self.symbol} {self.direction} {self.stake}'


class ExecutionLog(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='logs')
    event = models.CharField(max_length=120)
    status = models.CharField(max_length=32)
    latency = models.FloatField(null=True, blank=True)
    message = models.TextField(blank=True)
    broker_response = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['order', '-created_at']), models.Index(fields=['event', 'status'])]


class ExecutionQueue(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='queue_entry')
    priority = models.PositiveSmallIntegerField(default=5)
    attempts = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(max_length=24, default=c.QUEUE_STATUS_PENDING)
    queue_type = models.CharField(max_length=24, default='priority')
    next_retry = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['priority', 'created_at']
        indexes = [models.Index(fields=['status', 'next_retry', 'priority'])]
    def mark_retry(self, delay_seconds=30):
        self.status = c.QUEUE_STATUS_RETRY; self.attempts += 1; self.next_retry = timezone.now() + timezone.timedelta(seconds=delay_seconds); self.save(update_fields=['status', 'attempts', 'next_retry', 'updated_at']); return self


class ReconciliationEvent(models.Model):
    STATUS_OPEN = 'open'
    STATUS_REVIEWED = 'reviewed'
    STATUS_CHOICES = [(STATUS_OPEN, 'Open'), (STATUS_REVIEWED, 'Reviewed')]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reconciliation_events')
    broker_account = models.ForeignKey('brokers.BrokerAccount', on_delete=models.PROTECT, related_name='reconciliation_events')
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_OPEN, db_index=True)
    discrepancy_type = models.CharField(max_length=64, db_index=True)
    broker_reference = models.CharField(max_length=160, blank=True, db_index=True)
    symbol = models.CharField(max_length=40, blank=True)
    summary = models.CharField(max_length=255)
    details = models.JSONField(default=dict, blank=True)
    detected_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='reviewed_reconciliation_events')
    class Meta:
        ordering = ['-detected_at']
        indexes = [models.Index(fields=['broker_account', 'status', '-detected_at']), models.Index(fields=['user', 'status', '-detected_at'])]
    def mark_reviewed(self, user):
        self.status = self.STATUS_REVIEWED; self.reviewed_at = timezone.now(); self.reviewed_by = user; self.save(update_fields=['status', 'reviewed_at', 'reviewed_by']); return self


class BrokerTradeHistory(models.Model):
    """Immutable broker-fact cache for the authenticated account's trade history."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="broker_trade_history")
    broker_account = models.ForeignKey("brokers.BrokerAccount", on_delete=models.PROTECT, related_name="broker_trade_history")
    broker_contract_id = models.CharField(max_length=160, null=True, blank=True, db_index=True)
    broker_transaction_id = models.CharField(max_length=160, null=True, blank=True, db_index=True)
    broker_order_id = models.CharField(max_length=160, null=True, blank=True)
    reference_id = models.CharField(max_length=160, null=True, blank=True)
    symbol = models.CharField(max_length=80, null=True, blank=True)
    display_name = models.CharField(max_length=160, null=True, blank=True)
    instrument_type = models.CharField(max_length=80, null=True, blank=True)
    contract_type = models.CharField(max_length=80, null=True, blank=True)
    direction = models.CharField(max_length=32, null=True, blank=True)
    duration = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    duration_unit = models.CharField(max_length=8, null=True, blank=True)
    barrier = models.CharField(max_length=160, null=True, blank=True)
    buy_price = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    entry_price = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    sell_price = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    exit_price = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    stake = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    payout = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    profit_loss = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    currency = models.CharField(max_length=12, null=True, blank=True)
    status = models.CharField(max_length=40, default="unknown")
    purchase_time = models.DateTimeField(null=True, blank=True)
    execution_time = models.DateTimeField(null=True, blank=True)
    settlement_time = models.DateTimeField(null=True, blank=True)
    expiry_time = models.DateTimeField(null=True, blank=True)
    broker_timestamp = models.DateTimeField(null=True, blank=True)
    raw_data = models.JSONField(default=dict, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-broker_timestamp", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["broker_account", "broker_contract_id"], condition=~models.Q(broker_contract_id=""), name="unique_trade_contract_per_account"),
            models.UniqueConstraint(fields=["broker_account", "broker_transaction_id"], condition=~models.Q(broker_transaction_id=""), name="unique_trade_transaction_per_account"),
        ]
        indexes = [
            models.Index(fields=["broker_account", "broker_timestamp"], name="execution_t_account_time_idx"),
            models.Index(fields=["broker_account", "symbol", "status"], name="exec_t_acct_sym_status_idx"),
        ]
