"""
URL configuration for MediPro project.
"""
from django.contrib import admin
from django.urls import path, include
from rest_framework.authtoken.views import obtain_auth_token
from django.conf import settings
from django.conf.urls.static import static
from MediProAPI.apps.dashboard.views import DashboardOverviewAPIView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/accounts/', include('MediProAPI.apps.accounts.urls')),
    path('api/modules/', include('MediProAPI.apps.modules.urls')),
    path('api/users/', include('MediProAPI.apps.users.urls')),
    path('api/token/', obtain_auth_token, name='api_token_auth'),
    path('api/subscription/', include('MediProAPI.apps.subscription.urls')),
    path('api/', include('MediProAPI.apps.impersonation.urls')),
    path('api/dashboard/', include('MediProAPI.apps.dashboard.urls')),
    path('api/dashboard/overview/', DashboardOverviewAPIView.as_view(), name='dashboard-overview-direct'),
    path('api/credentials/', include('MediProAPI.apps.credentials.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
