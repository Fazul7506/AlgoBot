from django.db import models
from django.contrib.auth.models import User
import json


class SystemLog(models.Model):
    """System-level logs for debugging and monitoring"""
    
    LOG_LEVEL_CHOICES = [
        ('DEBUG', 'Debug'),
        ('INFO', 'Info'),
        ('WARNING', 'Warning'),
        ('ERROR', 'Error'),
        ('CRITICAL', 'Critical'),
    ]
    
    level = models.CharField(max_length=20, choices=LOG_LEVEL_CHOICES, default='INFO')
    message = models.TextField()
    module = models.CharField(max_length=255, blank=True)
    function = models.CharField(max_length=255, blank=True)
    exception = models.TextField(blank=True)
    context = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['level', '-created_at']),
            models.Index(fields=['module', '-created_at']),
        ]
    
    def __str__(self):
        return f"[{self.level}] {self.message[:100]}"


class TradeLog(models.Model):
    """Detailed logging of trade execution and lifecycle"""
    
    ACTION_CHOICES = [
        ('SIGNAL', 'Signal Generated'),
        ('OPEN', 'Trade Opened'),
        ('UPDATE', 'Trade Updated'),
        ('CLOSE', 'Trade Closed'),
        ('CANCEL', 'Trade Cancelled'),
        ('ERROR', 'Trade Error'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='trade_logs')
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    
    symbol = models.CharField(max_length=50)
    contract_type = models.CharField(max_length=20, blank=True)
    entry_price = models.FloatField(null=True, blank=True)
    exit_price = models.FloatField(null=True, blank=True)
    stake = models.FloatField(null=True, blank=True)
    pnl = models.FloatField(null=True, blank=True)
    
    strategy = models.CharField(max_length=100, blank=True)
    market_regime = models.CharField(max_length=50, blank=True)
    
    message = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['action', '-created_at']),
            models.Index(fields=['symbol', '-created_at']),
        ]
    
    def __str__(self):
        return f"[{self.user.username}] {self.action} - {self.symbol}"


class ErrorLog(models.Model):
    """Centralized error tracking with full context"""
    
    SEVERITY_CHOICES = [
        ('LOW', 'Low'),
        ('MEDIUM', 'Medium'),
        ('HIGH', 'High'),
        ('CRITICAL', 'Critical'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='error_logs')
    
    error_type = models.CharField(max_length=255)
    message = models.TextField()
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='MEDIUM')
    
    traceback = models.TextField(blank=True)
    endpoint = models.CharField(max_length=500, blank=True)
    method = models.CharField(max_length=10, blank=True)
    
    request_data = models.JSONField(default=dict, blank=True)
    context = models.JSONField(default=dict, blank=True)
    
    resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['severity', '-created_at']),
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['resolved', '-created_at']),
        ]
    
    def __str__(self):
        return f"[{self.severity}] {self.error_type} - {self.created_at}"
