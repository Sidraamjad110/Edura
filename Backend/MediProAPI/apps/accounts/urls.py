# apps/accounts/urls.py

from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import LoginAPIView, RegisterAPIView

urlpatterns = [
    path('login/', LoginAPIView.as_view(), name='login'),
    path('register/', RegisterAPIView.as_view(), name='register'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]