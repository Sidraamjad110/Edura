from django.urls import path
from . import views

urlpatterns = [
    # ================ SUBSCRIPTION PLANS ================
    path('plans/', views.subscription_plan_list, name='subscription-plan-list'),
    path('plans/create/', views.subscription_plan_create, name='subscription-plan-create'),
    path('plans/<int:plan_id>/', views.subscription_plan_detail, name='subscription-plan-detail'),
    path('plans/<int:plan_id>/update/', views.subscription_plan_update, name='subscription-plan-update'),
    path('plans/<int:plan_id>/delete/', views.subscription_plan_delete, name='subscription-plan-delete'),
    path('subscription-plans/set-status/', views.subscription_plan_set_active_status, name='subscription-plan-set-status'),
    # ================ SUBSCRIPTION MANAGEMENT ================
    path('assign/', views.subscription_assign, name='subscription-assign'),
    path('trial/', views.trial_subscription_create, name='trial-subscription-create'),
    path('list/', views.subscription_list, name='subscription-list'),
    path('expiring/', views.expiring_subscriptions, name='expiring-subscriptions'),
    path('<int:subscription_id>/activate/', views.subscription_activate, name='subscription-activate'),
    path('<int:subscription_id>/end/', views.subscription_end, name='subscription-end'),
    path('update-payment-status/', views.update_payment_status, name='update-payment-status'),

    # ================ CLIENT SUBSCRIPTIONS ================
    path('client/<int:client_id>/', views.client_subscription_detail, name='client-subscription-detail'),
    path('client/<int:client_id>/overview/', views.client_subscription_overview, name='client-subscription-overview'),
    path('client/<int:client_id>/access-status/', views.client_access_status, name='client-access-status'),
    path('client/<int:client_id>/emergency-activate/', views.client_emergency_activate, name='client-emergency-activate'),
    # Make sure this matches the view function name
    path('clients/', views.clients_with_subscriptions, name='clients-with-subscriptions'),

    # ================ INVOICES ================
    path('invoices/<int:invoice_id>/', views.invoice_detail, name='invoice-detail'),
    path('invoices/<int:invoice_id>/download/', views.invoice_download_pdf, name='invoice-download-pdf'),
    path('invoices/<int:invoice_id>/regenerate/', views.invoice_regenerate_pdf, name='invoice-regenerate-pdf'),
    path('invoices/<int:invoice_id>/mark-paid/', views.invoice_mark_paid, name='invoice-mark-paid'),
    path('<int:subscription_id>/invoices/', views.subscription_invoices, name='subscription-invoices'),
    path('client/<int:client_id>/invoices/', views.client_invoices, name='client-invoices'),

    # ================ ALERTS & STATISTICS ================
    path('invoices/overdue/', views.overdue_invoices, name='overdue-invoices'),
    path('invoices/send-overdue-alerts/', views.send_overdue_alerts, name='send-overdue-alerts'),
    path('invoices/send-reminders/', views.send_invoice_reminders, name='send-invoice-reminders'),
    path('invoices/statistics/', views.invoice_statistics, name='invoice-statistics'),
]