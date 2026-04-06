import csv
from io import StringIO
from datetime import datetime

from django import forms
from django.contrib import admin
from django.contrib.admin.sites import NotRegistered
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.contrib.auth.models import Group, User
from django.contrib.auth.hashers import make_password
from django.urls import path
from django.shortcuts import render
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.text import Truncator
from django.utils import timezone
from django.http import HttpResponse

from .models import (
    Warehouse,
    Shop,
    WarehouseCredential,
    ShopCredential,
    NetworkDefinition,
    Route,
)
from .user_roles import DEFAULT_ROLE, ROLE_CHOICES, get_user_role, set_user_role
from .store_account_service import StoreAccountService


class UserRoleChangeForm(UserChangeForm):
    role = forms.ChoiceField(choices=ROLE_CHOICES, required=False)

    class Meta(UserChangeForm.Meta):
        model = User
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["role"].initial = get_user_role(self.instance.pk)
        else:
            self.fields["role"].initial = DEFAULT_ROLE


class UserRoleCreationForm(UserCreationForm):
    role = forms.ChoiceField(choices=ROLE_CHOICES, required=False)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")


class UserRoleAdmin(UserAdmin):
    form = UserRoleChangeForm
    add_form = UserRoleCreationForm
    list_display = UserAdmin.list_display + ("role_display",)
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "email", "role")}),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "email", "password1", "password2", "role"),
            },
        ),
    )

    def role_display(self, obj):
        role = get_user_role(obj.pk)
        if role == "warehouse_worker":
            return "🏭 Warehouse"
        elif role == "shop_worker":
            return "🏪 Shop"
        else:
            return role

    role_display.short_description = "Role"

    def save_form(self, request, form, change):
        user = super().save_form(request, form, change)
        if form.cleaned_data.get("role"):
            set_user_role(user.id, form.cleaned_data["role"])
        return user


try:
    admin.site.unregister(User)
except NotRegistered:
    pass

admin.site.register(User, UserRoleAdmin)


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ("name", "node_id", "inventory", "network_definition", "get_username")
    list_filter = ("network_definition__name",)
    search_fields = ("name", "node_id")
    readonly_fields = ("created_at", "updated_at", "get_credentials_display")

    fieldsets = (
        (None, {"fields": ("name", "node_id", "inventory", "network_definition", "user")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
        ("Credentials", {"fields": ("get_credentials_display",), "classes": ("collapse",)}),
    )

    def get_username(self, obj):
        return obj.user.username if obj.user else "—"

    get_username.short_description = "Username"

    def get_credentials_display(self, obj):
        if not obj.pk:
            return "—"

        credentials = (
            WarehouseCredential.objects.filter(warehouse=obj)
            .order_by("-created_at")
            .first()
        )
        if not credentials:
            return "No credentials found"

        html = f"""
        <div style='padding: 10px; background-color: #f0f0f0; border-radius: 5px;'>
            <p><strong>Username:</strong> {credentials.username}</p>
            <p><strong>Password (Shared):</strong>
                <code id="pwd_{obj.pk}" style='display: none;'>{credentials.password}</code>
                <span id="pwd_masked_{obj.pk}">••••••••</span>
                <button onclick="togglePassword({obj.pk})" style='margin-left: 10px; padding: 5px 10px;'>Show</button>
                <button onclick="copyPassword({obj.pk})" style='margin-left: 5px; padding: 5px 10px;'>Copy</button>
            </p>
            <p style='color: green; font-size: 0.9em;'><strong>✓ Active</strong> (No expiration)</p>
        </div>
        <script>
            function togglePassword(objId) {{
                const pwd = document.getElementById('pwd_' + objId);
                const masked = document.getElementById('pwd_masked_' + objId);
                const btn = event.target;
                if (pwd.style.display === 'none') {{
                    pwd.style.display = 'inline';
                    masked.style.display = 'none';
                    btn.textContent = 'Hide';
                }} else {{
                    pwd.style.display = 'none';
                    masked.style.display = 'inline';
                    btn.textContent = 'Show';
                }}
            }}
            function copyPassword(objId) {{
                const pwd = document.getElementById('pwd_' + objId);
                navigator.clipboard.writeText(pwd.textContent);
                alert('Password copied to clipboard!');
            }}
        </script>
        """
        return mark_safe(html)

    get_credentials_display.short_description = "Credentials"


@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "node_id",
        "inventory",
        "target",
        "demand_rate",
        "network_definition",
        "get_username",
    )
    list_filter = ("network_definition__name",)
    search_fields = ("name", "node_id")
    readonly_fields = ("created_at", "updated_at", "get_credentials_display")

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "name",
                    "node_id",
                    "inventory",
                    "target",
                    "demand_rate",
                    "network_definition",
                    "user",
                )
            },
        ),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
        ("Credentials", {"fields": ("get_credentials_display",), "classes": ("collapse",)}),
    )

    def get_username(self, obj):
        return obj.user.username if obj.user else "—"

    get_username.short_description = "Username"

    def get_credentials_display(self, obj):
        if not obj.pk:
            return "—"

        credentials = (
            ShopCredential.objects.filter(shop=obj)
            .order_by("-created_at")
            .first()
        )
        if not credentials:
            return "No credentials found"

        html = f"""
        <div style='padding: 10px; background-color: #f0f0f0; border-radius: 5px;'>
            <p><strong>Username:</strong> {credentials.username}</p>
            <p><strong>Password (Shared):</strong>
                <code id="pwd_{obj.pk}" style='display: none;'>{credentials.password}</code>
                <span id="pwd_masked_{obj.pk}">••••••••</span>
                <button onclick="togglePassword({obj.pk})" style='margin-left: 10px; padding: 5px 10px;'>Show</button>
                <button onclick="copyPassword({obj.pk})" style='margin-left: 5px; padding: 5px 10px;'>Copy</button>
            </p>
            <p style='color: green; font-size: 0.9em;'><strong>✓ Active</strong> (No expiration)</p>
        </div>
        <script>
            function togglePassword(objId) {{
                const pwd = document.getElementById('pwd_' + objId);
                const masked = document.getElementById('pwd_masked_' + objId);
                const btn = event.target;
                if (pwd.style.display === 'none') {{
                    pwd.style.display = 'inline';
                    masked.style.display = 'none';
                    btn.textContent = 'Hide';
                }} else {{
                    pwd.style.display = 'none';
                    masked.style.display = 'inline';
                    btn.textContent = 'Show';
                }}
            }}
            function copyPassword(objId) {{
                const pwd = document.getElementById('pwd_' + objId);
                navigator.clipboard.writeText(pwd.textContent);
                alert('Password copied to clipboard!');
            }}
        </script>
        """
        return mark_safe(html)

    get_credentials_display.short_description = "Credentials"


@admin.register(Route)
class RouteAdmin(admin.ModelAdmin):
    list_display = (
        "edge_id",
        "source_node_id",
        "target_node_id",
        "travel_time",
        "transport_cost",
        "network_definition",
        "is_active",
    )
    list_filter = ("network_definition__name", "is_active")
    search_fields = ("edge_id", "source_node_id", "target_node_id")


@admin.register(NetworkDefinition)
class NetworkDefinitionAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "updated_at", "parse_status", "account_count")
    list_filter = ("is_active",)
    search_fields = ("name",)
    readonly_fields = (
        "created_at",
        "updated_at",
        "parse_error",
        "definition",
        "credentials_table",
    )
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "name",
                    "json_file",
                    "shared_password",
                    "is_active",
                )
            },
        ),
        (
            "Parse Result",
            {"fields": ("parse_error", "definition", "created_at", "updated_at")},
        ),
        (
            "Generated Accounts",
            {
                "description": "Warehouses and shops created from this network definition. "
                "All users share the same password.",
                "fields": ("credentials_table",),
                "classes": ("collapse",),
            },
        ),
    )

    def parse_status(self, obj):
        if not obj.parse_error:
            return "✓ OK"
        return Truncator(obj.parse_error).chars(40)

    parse_status.short_description = "Status"

    def account_count(self, obj):
        warehouses = Warehouse.objects.filter(network_definition=obj).count()
        shops = Shop.objects.filter(network_definition=obj).count()
        return f"{warehouses}W + {shops}S"

    account_count.short_description = "Accounts"

    def credentials_table(self, obj):
        if not obj.pk:
            return "Accounts created after saving"

        warehouses = Warehouse.objects.filter(network_definition=obj).select_related("user")
        shops = Shop.objects.filter(network_definition=obj).select_related("user")

        if not warehouses.exists() and not shops.exists():
            return "No accounts created yet"

        # Get fresh credentials
        credentials_list = []

        for warehouse in warehouses:
            cred = (
                WarehouseCredential.objects.filter(warehouse=warehouse)
                .order_by("-created_at")
                .first()
            )
            if cred:
                credentials_list.append(("warehouse", warehouse, cred))

        for shop in shops:
            cred = (
                ShopCredential.objects.filter(shop=shop)
                .order_by("-created_at")
                .first()
            )
            if cred:
                credentials_list.append(("shop", shop, cred))

        if not credentials_list:
            return "No credentials found"

        # Build HTML table
        html = f"""
        <table style='width: 100%; border-collapse: collapse;'>
            <thead>
                <tr style='background-color: #f0f0f0; border-bottom: 1px solid #ccc;'>
                    <th style='padding: 8px; text-align: left;'>Name</th>
                    <th style='padding: 8px; text-align: left;'>Type</th>
                    <th style='padding: 8px; text-align: left;'>Username</th>
                    <th style='padding: 8px; text-align: left;'>Shared Password</th>
                    <th style='padding: 8px; text-align: left;'>Status</th>
                </tr>
            </thead>
            <tbody>
        """

        for location_type, location, cred in credentials_list:
            status = '<span style="color: green;">✓ Active</span>'
            pwd_display = f'<code>{cred.password}</code> <button onclick="copyToClipboard(\'{cred.password}\')" style="padding: 2px 8px; font-size: 0.85em;">Copy</button>'

            html += f"""
                <tr style='border-bottom: 1px solid #e0e0e0;'>
                    <td style='padding: 8px;'>{location.name}</td>
                    <td style='padding: 8px;'><strong>{location_type.upper()}</strong></td>
                    <td style='padding: 8px;'><code>{cred.username}</code></td>
                    <td style='padding: 8px;'>{pwd_display}</td>
                    <td style='padding: 8px;'>{status}</td>
                </tr>
            """

        html += """
            </tbody>
        </table>
        <div style='margin-top: 15px;'>
            <button onclick="downloadNetworkCSV()" style='padding: 8px 16px; background-color: #0066cc; color: white; border: none; border-radius: 4px; cursor: pointer;'>
                📥 Download Credentials CSV
            </button>
        </div>
        <script>
            function copyToClipboard(text) {
                navigator.clipboard.writeText(text);
                alert('Password copied to clipboard!');
            }
            function downloadNetworkCSV() {
                window.location.href = '""" + f"/admin/api/networkdefinition/{obj.pk}/download-credentials/" + """';
            }
        </script>
        """

        html += '<p style="margin-top: 15px; color: green; font-size: 0.9em;"><strong>ℹ Note:</strong> All users share the same password. Users can change it in the frontend.</p>'

        return mark_safe(html)

    credentials_table.short_description = "Generated Credentials"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:networkdefinition_id>/download-credentials/",
                self.admin_site.admin_view(self.download_credentials_csv),
                name="networkdefinition-download-credentials",
            ),
        ]
        return custom_urls + urls

    def download_credentials_csv(self, request, networkdefinition_id):
        """Generate and download credentials as CSV."""
        try:
            network = NetworkDefinition.objects.get(pk=networkdefinition_id)
        except NetworkDefinition.DoesNotExist:
            return HttpResponse("NetworkDefinition not found", status=404)

        # Create CSV
        output = StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow(["Name", "Type", "Username", "Password", "Node ID"])

        # Write warehouse credentials
        for warehouse in Warehouse.objects.filter(network_definition=network):
            cred = (
                WarehouseCredential.objects.filter(warehouse=warehouse)
                .order_by("-created_at")
                .first()
            )
            if cred:
                writer.writerow(
                    [
                        warehouse.name,
                        "Warehouse",
                        cred.username,
                        cred.password,
                        warehouse.node_id,
                    ]
                )

        # Write shop credentials
        for shop in Shop.objects.filter(network_definition=network):
            cred = (
                ShopCredential.objects.filter(shop=shop)
                .order_by("-created_at")
                .first()
            )
            if cred:
                writer.writerow(
                    [
                        shop.name,
                        "Shop",
                        cred.username,
                        cred.password,
                        shop.node_id,
                    ]
                )

        # Return CSV file
        response = HttpResponse(output.getvalue(), content_type="text/csv")
        filename = f"credentials_{network.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
