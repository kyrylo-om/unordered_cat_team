from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0001_maplayout"),
    ]

    operations = [
        migrations.RunSQL(
            sql="ALTER TABLE auth_user ADD COLUMN role varchar(32) NOT NULL DEFAULT 'manager';",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="UPDATE auth_user SET role = 'manager' WHERE role IS NULL OR TRIM(role) = '';",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
