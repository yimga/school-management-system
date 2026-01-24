from django.urls import path

from . import views

app_name = 'emis'

urlpatterns = [
    path('', views.emis_dashboard, name='dashboard'),
    path('export/', views.export_emis_data, name='export'),
    path('download/<int:export_id>/', views.download_emis_export, name='download'),
    path('api/status/', views.emis_api_status, name='api_status'),
    path('api/compliance/<str:country_code>/', views.emis_compliance_info, name='compliance_info'),
]