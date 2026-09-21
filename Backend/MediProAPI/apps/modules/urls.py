from django.urls import path
from .views import (
    ModuleListView,
    UserModulesAPIView,
    CurrentUserModulesAPIView,
    CheckModuleAccessAPIView,
    ModuleIconListAPIView,
    UpdateModuleSequenceAPIView,
    UpdateModuleSideBarVisibilityAPIView,
    assigned_modules_list,
    assign_modules,
    unassign_module,
    update_module_assignment,
    update_hierarchy,
)

urlpatterns = [
    # ── Existing ──────────────────────────────────────────────
    path('list',                        ModuleListView.as_view(),             name='module-list'),
    path('user/<int:user_id>/',         UserModulesAPIView.as_view(),         name='user-modules'),
    path('my-modules/',                 CurrentUserModulesAPIView.as_view(),  name='my-modules'),
    path('check/<str:module_code>/',    CheckModuleAccessAPIView.as_view(),   name='check-module-access'),
    path('icons/',                      ModuleIconListAPIView.as_view(),      name='module-icons'),
    path('update-sequence/',            UpdateModuleSequenceAPIView.as_view(),name='update-module-sequence'),

    path('batch-update-visibility/',    UpdateModuleSideBarVisibilityAPIView.as_view(), name='batch-update-module-visibility'),

    # ── Assignment ────────────────────────────────────────────
    path('assigned/',                   assigned_modules_list,                name='modules-assigned-list'),
    path('assign/',                     assign_modules,                       name='modules-assign'),
    path('unassign/',                   unassign_module,                      name='modules-unassign'),
    path('assign/update/',              update_module_assignment,             name='modules-assign-update'),
    path('assign/hierarchy/',           update_hierarchy,                     name='modules-assign-hierarchy'),
]