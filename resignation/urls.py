from django.urls import path
from . import views

app_name = 'resignation'

urlpatterns = [
    path('dashboard/', views.resignation_dashboard, name='dashboard'),
    path('submit/', views.submit_resignation, name='submit_resignation'),
    path('all/', views.all_resignations, name='all_resignations'),
    path('my-resignation/', views.my_resignation, name='my_resignation'),
    path('history/', views.resignation_history, name='resignation_history'),
    path('detail/<int:resignation_id>/', views.resignation_detail, name='resignation_detail'),
    path('approve/<int:resignation_id>/', views.approve_resignation, name='approve_resignation'),
    path('withdraw/<int:resignation_id>/', views.withdraw_resignation, name='withdraw_resignation'),
    path('checklist/<int:checklist_id>/update/', views.update_checklist, name='update_checklist'),
    path('analytics/', views.resignation_analytics, name='analytics'),
    path('certificate/<int:resignation_id>/', views.no_due_certificate, name='no_due_certificate'),
    path('certificate/<int:resignation_id>/download/', views.download_no_due_certificate, name='download_no_due_certificate'),
    path('exit-interview/<int:resignation_id>/', views.exit_interview, name='exit_interview'),
    path('exit-interview/<int:resignation_id>/download/', views.download_exit_interview, name='download_exit_interview'),
    path('upload-form/<int:resignation_id>/', views.upload_document, name='upload_document'),
    path('delete-form/<int:document_id>/', views.delete_document, name='delete_document'),
]