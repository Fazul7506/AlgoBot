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
    stake = models.DecimalField(max_digits=18, decimal_places=8)
    price = models.DecimalField(max_digits=18, decimal_places=8, null=True, blank=True)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=c.ORDER_STATUS_DRAFT)
    broker_reference = models.CharField(max_length=160, blank=True, db_index=True)
    client_request_id = models.CharField(max_length=80, blank=True, db_index=True)
    validation_context = models.JSONField(default=dict, blank=True)
    broker_payload = models.JSONField(default=dict, blank=True)
    broker_response = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['user', 'status']), models.Index(fields=['broker_account', 'symbol'])]
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
