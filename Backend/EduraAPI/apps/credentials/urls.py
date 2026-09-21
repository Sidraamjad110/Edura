from django.urls import path
from . import views

urlpatterns = [
    # Admin endpoints — mirrors telephony URL pattern
    path('admin/list/', views.admin_credential_list_api, name='admin-credential-list'),
    path('admin/<int:client_id>/detail/', views.admin_credential_detail_api, name='admin-credential-detail'),

    # Client (self) endpoints
    path('me/detail/', views.client_credential_api, name='client-credential-detail'),
    path('me/update/', views.client_credential_api, name='client-credential-update'),
]
