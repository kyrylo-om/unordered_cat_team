from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from django.core.validators import FileExtensionValidator
import json


class NetworkDefinition(models.Model):
    """
    JSON-based network definition for creating warehouses and shops.
    All users created from this network share the same password.
    """
    name = models.CharField(max_length=255, unique=True)
    json_file = models.FileField(
        upload_to="network_definitions/",
        validators=[FileExtensionValidator(allowed_extensions=["json"])],
        help_text="JSON file defining warehouses and shops"
    )
    definition = models.JSONField(default=dict, blank=True)
    shared_password = models.CharField(
        max_length=255,
        default="DefaultPassword123!",
        help_text="Shared password for all users in this network"
    )
    parse_error = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.name


class Warehouse(models.Model):
    name = models.CharField(max_length=255)
    node_id = models.CharField(max_length=50)
    network_definition = models.ForeignKey(NetworkDefinition, on_delete=models.CASCADE, null=True, blank=True)
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, null=True, blank=True, unique=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [["network_definition", "node_id"]]
        indexes = [
            models.Index(fields=["user_id"]),
            models.Index(fields=["network_definition_id"]),
        ]

    def __str__(self):
        return f"{self.name} (Warehouse)"


class Shop(models.Model):
    name = models.CharField(max_length=255)
    node_id = models.CharField(max_length=50)
    network_definition = models.ForeignKey(NetworkDefinition, on_delete=models.CASCADE, null=True, blank=True)
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, null=True, blank=True, unique=True
    )
    inventory = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [["network_definition", "node_id"]]
        indexes = [
            models.Index(fields=["user_id"]),
            models.Index(fields=["network_definition_id"]),
        ]

    def __str__(self):
        return f"{self.name} (Shop)"


class WarehouseCredential(models.Model):
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE)
    username = models.CharField(max_length=150)
    password = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    def is_expired(self):
        if self.expires_at is None:
            return False  # No expiration
        return timezone.now() > self.expires_at

    def __str__(self):
        return f"{self.username} ({self.warehouse.name})"


class ShopCredential(models.Model):
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE)
    username = models.CharField(max_length=150)
    password = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    def is_expired(self):
        if self.expires_at is None:
            return False  # No expiration
        return timezone.now() > self.expires_at

    def __str__(self):
        return f"{self.username} ({self.shop.name})"
