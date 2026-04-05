from django import forms
from django.contrib import admin
from django.contrib.admin.sites import NotRegistered
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.contrib.auth.models import Group, User
from django.utils.text import Truncator

from .models import MapLayout
from .user_roles import DEFAULT_ROLE, ROLE_CHOICES, get_user_role, set_user_role


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
        return get_user_role(obj.pk)

    role_display.short_description = "Role"

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.pk:
            set_user_role(obj.pk, form.cleaned_data.get("role", DEFAULT_ROLE))


try:
    admin.site.unregister(Group)
except NotRegistered:
    pass

try:
    admin.site.unregister(User)
except NotRegistered:
    pass

admin.site.register(User, UserRoleAdmin)


@admin.register(MapLayout)
class MapLayoutAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "updated_at", "layout_size", "parse_status")
    list_filter = ("is_active",)
    search_fields = ("name",)
    readonly_fields = (
        "created_at",
        "updated_at",
        "parse_error",
        "layout_size",
    )

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "name",
                    "dot_file",
                    "is_active",
                )
            },
        ),
        (
            "Parse Result",
            {"fields": ("layout_size", "parse_error", "created_at", "updated_at")},
        ),
    )

    def layout_size(self, obj):
        if not obj.parsed_layout or not isinstance(obj.parsed_layout, dict):
            return "Nodes: 0, Edges: 0"
        nodes = len(obj.parsed_layout.get("nodes", []))
        edges = len(obj.parsed_layout.get("edges", []))
        return f"Nodes: {nodes}, Edges: {edges}"

    layout_size.short_description = "Layout Size"

    def parse_status(self, obj):
        if not obj.parse_error:
            return "OK"
        return Truncator(obj.parse_error).chars(40)

    parse_status.short_description = "Parse Status"
