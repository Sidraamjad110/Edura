# apps/impersonation/models.py
from django.db import models
from django.conf import settings
from django.utils import timezone
import json


class ImpersonationLog(models.Model):
    """Log all impersonation activities"""
    admin_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='impersonations_initiated'
    )
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='impersonations_received'
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    class Meta:
        db_table = 'impersonation_logs'
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.admin_user.username} → {self.target_user.username} at {self.timestamp}"