from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("modules", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Language",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100)),
                ("code", models.CharField(max_length=10, unique=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "languages",
            },
        ),
        migrations.CreateModel(
            name="Client",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False, db_column="id")),
                ("phone", models.CharField(blank=True, max_length=20, null=True)),
                ("avatar_base64", models.TextField(blank=True, help_text="Avatar image stored as Base64", null=True)),
                ("avatar_filename", models.CharField(blank=True, help_text="Original filename", max_length=255, null=True)),
                ("avatar_content_type", models.CharField(blank=True, help_text="Image MIME type", max_length=100, null=True)),
                ("company_name", models.CharField(blank=True, max_length=200, null=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "auth_user",
                    models.OneToOneField(
                        db_column="auth_user_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="client_profile",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        db_column="created_by_id",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_clients",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "language",
                    models.ForeignKey(
                        blank=True,
                        db_column="language_id",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="clients",
                        to="users.language",
                    ),
                ),
            ],
            options={
                "db_table": "clients",
            },
        ),
        migrations.CreateModel(
            name="AdminProfile",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False, db_column="id")),
                ("phone", models.CharField(blank=True, max_length=20, null=True)),
                ("avatar_base64", models.TextField(blank=True, null=True)),
                ("avatar_filename", models.CharField(blank=True, max_length=255, null=True)),
                ("avatar_content_type", models.CharField(blank=True, max_length=100, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "auth_user",
                    models.OneToOneField(
                        db_column="auth_user_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="admin_profile",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "admin_profiles",
            },
        ),
        migrations.CreateModel(
            name="CustomUser",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False, db_column="id")),
                ("phone", models.CharField(blank=True, max_length=20, null=True)),
                ("avatar_base64", models.TextField(blank=True, help_text="Avatar image stored as Base64", null=True)),
                ("avatar_filename", models.CharField(blank=True, help_text="Original filename", max_length=255, null=True)),
                ("avatar_content_type", models.CharField(blank=True, help_text="Image MIME type", max_length=100, null=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "auth_user",
                    models.OneToOneField(
                        db_column="auth_user_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="custom_profile",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "client",
                    models.ForeignKey(
                        db_column="client_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="users",
                        to="users.client",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        db_column="created_by_id",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_custom_users",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "language",
                    models.ForeignKey(
                        blank=True,
                        db_column="language_id",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="custom_users",
                        to="users.language",
                    ),
                ),
            ],
            options={
                "db_table": "custom_users",
            },
        ),
        migrations.CreateModel(
            name="Localization",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(help_text="Unique identifier for the text", max_length=255)),
                ("text", models.TextField(help_text="Translated text")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_localizations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "language",
                    models.ForeignKey(
                        db_column="language_code",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="localizations",
                        to="users.language",
                        to_field="code",
                    ),
                ),
                (
                    "module",
                    models.ForeignKey(
                        blank=True,
                        db_column="module_id",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="localizations",
                        to="modules.module",
                    ),
                ),
            ],
            options={
                "verbose_name": "Localization",
                "verbose_name_plural": "Localizations",
                "db_table": "localizations",
                "unique_together": {("code", "language", "module")},
            },
        ),
    ]
