from django.urls import path

from .views import DashboardOverviewAPIView

urlpatterns = [
    path("overview/", DashboardOverviewAPIView.as_view(), name="dashboard-overview"),
]
