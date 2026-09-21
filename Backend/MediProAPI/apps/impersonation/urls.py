# apps/impersonation/urls.py
from django.urls import path
from .views import (
    UserSearchView,
    SwitchUserView,
    ReturnToAdminView,
    CheckImpersonationView
)

urlpatterns = [
    path('admin/users/search/', UserSearchView.as_view(), name='user-search'),
    path('admin/switch-user/', SwitchUserView.as_view(), name='switch-user'),
    path('admin/return-to-admin/', ReturnToAdminView.as_view(), name='return-to-admin'),
    path('admin/check-impersonation/', CheckImpersonationView.as_view(), name='check-impersonation'),
]