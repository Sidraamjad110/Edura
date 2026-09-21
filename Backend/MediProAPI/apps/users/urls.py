from django.urls import path
from . import views
from .views import ClientsAndUsersListAPIView

urlpatterns = [
    path('localizations/', views.localization_list, name='localization_list'),
    path('localizations/bulk-fetch/', views.localization_bulk_fetch, name='localization_bulk_fetch'),
    path('localizations/create/', views.localization_create, name='localization_create'),
    path('localizations/<int:pk>/', views.localization_detail, name='localization_detail'),
    path('localizations/<int:pk>/update/', views.localization_update, name='localization_update'),
    path('localizations/<int:pk>/delete/', views.localization_delete, name='localization_delete'),

    path('languages/list/', views.language_list, name='language-list'),

    path('account/list/', views.account_list, name='account-list'),
    path('account/create/', views.account_create, name='account-create'),
    path('account/update/<int:pk>/', views.account_update, name='account-update'),
    path('account/delete/<int:pk>/', views.account_delete, name='account-delete'),
    path('account/detail/<int:pk>/', views.account_detail, name='account-detail'),
    path('account/toggle-active/<int:pk>/', views.account_toggle_active, name='account-toggle-active'),

    path('change-password/<str:user_type>/<int:pk>/', views.change_password, name='change-password'),

    path('password-reset/request/', views.password_reset_request, name='password_reset_request'),
    path('password-reset/confirm/', views.password_reset_confirm, name='password_reset_confirm'),
    path('password-reset/validate/', views.password_reset_validate_token, name='password_reset_validate_token'),
    path('clients-with-users/', ClientsAndUsersListAPIView.as_view(), name='clients-with-users'),
]
