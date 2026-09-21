from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class Module(models.Model):
    """
    System modules table — a flat catalogue of available modules.

    There is NO hierarchy here. Modules are just entries with a code, description,
    URL and icon. All parent/child relationships are managed per-user on UserModule.
    """
    code        = models.CharField(max_length=100, unique=True)
    description = models.CharField(max_length=500, blank=True, null=True)
    url         = models.CharField(max_length=255, blank=True, null=True)
    icon        = models.CharField(max_length=100, blank=True, null=True)
    is_active   = models.BooleanField(default=True)

    class Meta:
        db_table   = 'modules'
        verbose_name        = 'Module'
        verbose_name_plural = 'Modules'

    def __str__(self):
        return self.code


class UserModule(models.Model):
    """
    User-module assignment table.

    Records which modules are assigned to which user and defines the
    PER-USER module hierarchy via `parent_id`.

    `parent_id` stores the module_id of the parent module in this user's
    personal sidebar tree.  This allows each user to have a completely
    different hierarchy from every other user.

    Examples:
        parent_id = NULL  → top-level in this user's sidebar
        parent_id = 20    → appears under module 20 in this user's sidebar
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='user_modules',
        db_column='user_id',
    )
    module = models.ForeignKey(
        Module,
        on_delete=models.CASCADE,
        related_name='user_assignments',
        db_column='module_id',
    )
    is_active  = models.BooleanField(default=True)
    is_default = models.BooleanField(
        default=False,
        verbose_name='Is Default Module',
        help_text='Indicates if this is the default module for the user',
    )
    sequence = models.IntegerField(
        default=0,
        verbose_name='Display Sequence',
        help_text='Order in which modules are displayed (lower numbers first)',
    )
    # Per-user parent: stores the module_id of the parent in this user's tree.
    # NULL = top-level. Plain IntegerField (not FK) so each user can freely
    # restructure their own tree without global constraint.
    parent_id = models.IntegerField(
        null=True,
        blank=True,
        default=None,
        verbose_name='Parent Module ID (per-user)',
        help_text=(
            "The module_id of the parent module in this user's sidebar tree. "
            "NULL means this module is top-level for this user."
        ),
    )

    show_in_sidebar = models.BooleanField(
        default=True,
        verbose_name='Show in Sidebar',
        help_text='If true, this module appears in the sidebar. If false, it is hidden from sidebar navigation.',
    )

    class Meta:
        db_table       = 'user_modules'
        unique_together = ['user', 'module']
        verbose_name        = 'User Module'
        verbose_name_plural = 'User Modules'

    def __str__(self):
        default_marker = ' [DEFAULT]' if self.is_default else ''
        parent_marker  = f' (child of module {self.parent_id})' if self.parent_id else ''
        visibility_marker = ' [HIDDEN]' if not self.show_in_sidebar else ''
        return f'{self.user.username} - {self.module.code}{default_marker}{parent_marker}'