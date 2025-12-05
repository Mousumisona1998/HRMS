from django.urls import path
from . import views

urlpatterns = [
    path('', views.leave_dashboard, name='leave_dashboard'),
    path('list/', views.leave_list, name='leave_list'),
    path('apply/', views.apply_leave, name='apply_leave'),
    path('approve/<int:leave_id>/', views.approve_leave, name='approve_leave'),
    # path('detail/<int:leave_id>/', views.leave_detail, name='leave_detail'),
    path('regions/', views.manage_regions, name='manage_regions'),
    path('api/stats/', views.get_leave_stats_api, name='leave_stats_api'),
    path('calendar-events/', views.calendar_events, name='calendar_events'),
    path('holiday/add/', views.add_holiday, name='add_holiday'),
    path('event/add/', views.add_custom_event, name='add_custom_event'),
    path('leave_details',views.employee_leave_details,name='employee_leave_details'),
    path('leave/detail/<int:leave_id>/', views.view_leave_detail, name='view_leave_detail'),
    path('leave/<int:leave_id>/edit/', views.edit_leave_details, name='edit_leave_details'),
    path('leave-balances/', views.leave_balance_summary, name='leave_balance_list'),
    path('add-leave-balance/', views.add_leave_balance, name='add_leave_balance'),
    path('edit-leave-balance/', views.edit_leave_balance, name='edit_leave_balance'),
    path('withdraw-leave/<int:leave_id>/', views.withdraw_leave, name='withdraw_leave'),
    path('get-region-holidays/', views.get_region_holidays_api, name='get_region_holidays'),
    path('api/optional-holidays/', views.get_optional_holidays_api, name='get_optional_holidays_api'),
    path('master_data/add-leave-type/', views.add_leave_type, name='add_leave_type'),
    path('master_data/leave-type/update/<int:pk>/', views.update_leave_type, name='update_leave_type'),
    path('master_data/leave-type/delete/<int:pk>/', views.delete_leave_type, name='delete_leave_type'),
    
]