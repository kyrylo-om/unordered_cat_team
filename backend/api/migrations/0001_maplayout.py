from django.core.validators import FileExtensionValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="MapLayout",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=120)),
                (
                    "dot_file",
                    models.FileField(
                        upload_to="map_layouts/",
                        validators=[
                            FileExtensionValidator(allowed_extensions=["dot"])
                        ],
                    ),
                ),
                ("parsed_layout", models.JSONField(blank=True, default=dict)),
                ("is_active", models.BooleanField(default=True)),
                ("parse_error", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["-updated_at"]},
        ),
    ]
