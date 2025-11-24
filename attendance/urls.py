from django.urls import path
from . import views

app_name = 'attendance'

urlpatterns = [
    path('dashboard/', views.attendance_dashboard, name='dashboard'),
    path('all/', views.all_attendance, name='all_attendance'),
    path('report/', views.attendance_report, name='report'),
    path('download_report_excel/', views.download_attendance_report_excel, name='download_report_excel'),
    path('download-admin-report/', views.download_admin_attendance_report, name='download_admin_report'),
    path('upload-excel/', views.upload_admin_attendance_excel, name='upload_admin_attendance_excel'),
    
]
