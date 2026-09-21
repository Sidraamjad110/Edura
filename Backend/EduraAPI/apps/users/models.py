from django.db import models
from django.contrib.auth import get_user_model
import base64
from django.core.files.base import ContentFile

User = get_user_model()


class Language(models.Model):
    # id is automatically created by Django as AutoField primary key
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=10, unique=True)  # e.g., 'en', 'es', 'fr'
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'languages'

    def __str__(self):
        return self.name


class Localization(models.Model):
    """Localization entries for multilingual text"""
    # id is automatically created by Django as AutoField primary key
    code = models.CharField(max_length=255, help_text="Unique identifier for the text")
    text = models.TextField(help_text="Translated text")
    language = models.ForeignKey(
        Language,
        on_delete=models.CASCADE,
        related_name='localizations',
        to_field='code',
        db_column='language_code'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_localizations'
    )
    # FIX: Changed from module_id to module (Django creates module_id column automatically)
    module = models.ForeignKey(
        'modules.Module',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='module_id',
        related_name='localizations'
    )

    class Meta:
        db_table = 'localizations'
        # FIX: Changed module_id to module in unique_together
        unique_together = [['code', 'language', 'module']]
        verbose_name = 'Localization'
        verbose_name_plural = 'Localizations'

    def __str__(self):
        return f"{self.code} ({self.language.code})"


class Client(models.Model):
    """
    Client users created by Admin
    These are the main account holders who can create their own users
    """
    # EXPLICITLY ADD ID FIELD
    id = models.AutoField(primary_key=True, db_column='id')

    # Link to Django's auth_user table
    auth_user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='client_profile',
        db_column='auth_user_id'
    )

    # Custom fields
    phone = models.CharField(max_length=20, blank=True, null=True)

    # CHANGED: Store avatar as Base64 in TextField for database storage
    avatar_base64 = models.TextField(blank=True, null=True, help_text="Avatar image stored as Base64")
    avatar_filename = models.CharField(max_length=255, blank=True, null=True, help_text="Original filename")
    avatar_content_type = models.CharField(max_length=100, blank=True, null=True, help_text="Image MIME type")

    language = models.ForeignKey(
        Language,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='clients',
        db_column='language_id'
    )

    # Business fields
    company_name = models.CharField(max_length=200, blank=True, null=True)

    # Audit fields
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_clients',
        db_column='created_by_id'
    )

    class Meta:
        db_table = 'clients'

    def __str__(self):
        return f"Client: {self.auth_user.username} - {self.auth_user.get_full_name()}"

    @property
    def first_name(self):
        return self.auth_user.first_name

    @property
    def last_name(self):
        return self.auth_user.last_name

    @property
    def email(self):
        return self.auth_user.email

    @property
    def username(self):
        return self.auth_user.username

    @property
    def avatar(self):
        """Return Base64 data URI for avatar"""
        if self.avatar_base64:
            content_type = self.avatar_content_type or 'image/jpeg'
            return f"data:{content_type};base64,{self.avatar_base64}"
        return None

    def set_avatar_from_file(self, uploaded_file):
        """Set avatar from uploaded file"""
        if uploaded_file:
            # Read file content
            file_content = uploaded_file.read()
            # Convert to base64
            self.avatar_base64 = base64.b64encode(file_content).decode('utf-8')
            self.avatar_filename = uploaded_file.name
            self.avatar_content_type = uploaded_file.content_type
            self.save()


class AdminProfile(models.Model):
    id = models.AutoField(primary_key=True, db_column='id')
    auth_user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='admin_profile',
        db_column='auth_user_id'
    )
    phone = models.CharField(max_length=20, blank=True, null=True)
    avatar_base64 = models.TextField(blank=True, null=True)
    avatar_filename = models.CharField(max_length=255, blank=True, null=True)
    avatar_content_type = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'admin_profiles'

    @property
    def avatar(self):
        if self.avatar_base64:
            content_type = self.avatar_content_type or 'image/jpeg'
            return f"data:{content_type};base64,{self.avatar_base64}"
        return None


class CustomUser(models.Model):
    """
    Regular users created by Clients
    These users belong to a client account
    """
    # EXPLICITLY ADD ID FIELD
    id = models.AutoField(primary_key=True, db_column='id')

    # Link to Django's auth_user table
    auth_user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='custom_profile',
        db_column='auth_user_id'
    )

    # Link to client (who owns this user)
    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name='users',
        db_column='client_id'
    )

    # Custom fields
    phone = models.CharField(max_length=20, blank=True, null=True)

    # CHANGED: Store avatar as Base64 in TextField for database storage
    avatar_base64 = models.TextField(blank=True, null=True, help_text="Avatar image stored as Base64")
    avatar_filename = models.CharField(max_length=255, blank=True, null=True, help_text="Original filename")
    avatar_content_type = models.CharField(max_length=100, blank=True, null=True, help_text="Image MIME type")

    language = models.ForeignKey(
        Language,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='custom_users',
        db_column='language_id'
    )

    # Audit fields
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_custom_users',
        db_column='created_by_id'
    )

    class Meta:
        db_table = 'custom_users'

    def __str__(self):
        return f"User: {self.auth_user.username} (Client: {self.client.auth_user.username})"

    @property
    def first_name(self):
        return self.auth_user.first_name

    @property
    def last_name(self):
        return self.auth_user.last_name

    @property
    def email(self):
        return self.auth_user.email

    @property
    def username(self):
        return self.auth_user.username

    @property
    def avatar(self):
        """Return Base64 data URI for avatar"""
        if self.avatar_base64:
            content_type = self.avatar_content_type or 'image/jpeg'
            return f"data:{content_type};base64,{self.avatar_base64}"
        return None

    def set_avatar_from_file(self, uploaded_file):
        """Set avatar from uploaded file"""
        if uploaded_file:
            # Read file content
            file_content = uploaded_file.read()
            # Convert to base64
            self.avatar_base64 = base64.b64encode(file_content).decode('utf-8')
            self.avatar_filename = uploaded_file.name
            self.avatar_content_type = uploaded_file.content_type
            self.save()