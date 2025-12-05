from django.urls import path
from . import views

urlpatterns = [
    # Authentication
    path('', views.home, name='home'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('change-password/', views.change_password, name='change_password'),
    path('access-denied/', views.access_denied, name='access_denied'),
    
    # Dashboards
    path('dashboard/', views.dashboard, name='dashboard'),
    path('employee-dashboard/', views.employee_dashboard, name='employee_dashboard'),
    path('team-members/', views.total_team_members, name='total_team_members'),
    
    # Employee Management
    path('employees/', views.employee_page, name='employee_page'),
    path('employees/add/', views.add_employee, name='add_employee'),
    path('search-managers/', views.search_managers, name='search_managers'),
    path('search-employees/', views.search_employees, name='search_employees'),
    path('employee/<int:employee_id>/', views.employee_detail, name='employee_detail'),
    path('employee/<int:employee_id>/edit/', views.edit_employee, name='edit_employee'),
    path('delete-document/<int:document_id>/', views.delete_document, name='delete_document'),
    path('update-profile/', views.update_employee_profile, name='update_employee_profile'),
    path('employees/all/', views.all_employee, name='all_employee'),
    path('employees/active/', views.active_employee, name='active_employee'),
    path('probation-settings/', views.probation_settings, name='probation_settings'),
    path('get-designations-by-department/', views.get_designations_by_department, name='get_designations_by_department'),
    path("employees/ajax-search/", views.employee_search_ajax, name="employee_search_ajax"),
    
    # Admin Management
    path('admins/', views.admin_list, name='admin_list'),
    path('admins/create/', views.admin_create, name='admin_create'),
    path('admins/<int:pk>/update/', views.admin_update, name='admin_update'),
    path('admins/<int:pk>/delete/', views.admin_delete, name='admin_delete'),
    
    
    
    # Location Management URLs
    path('master-data/locations/', views.location_list, name='location_list'),
    path('master-data/locations/add/', views.location_create, name='location_create'),
    path('master-data/locations/<int:pk>/edit/', views.location_edit, name='location_edit'),
    path('master-data/locations/<int:pk>/delete/', views.location_delete, name='location_delete'),
    
    # Branch URLs (using location views)
    path('master-data/branches/', views.location_list, name='branch_list'),
    path('master-data/branches/add/', views.location_create, name='branch_create'),
    path('master-data/branches/<int:pk>/edit/', views.location_edit, name='branch_edit'),
    path('master-data/branches/<int:pk>/delete/', views.location_delete, name='branch_delete'),

    # Department Management URLs
    path('master-data/departments/', views.department_list, name='department_list'),
    path('master-data/departments/add/', views.department_create, name='department_create'),
    path('master-data/departments/<int:pk>/edit/', views.department_edit, name='department_edit'),
    path('master-data/departments/<int:pk>/delete/', views.department_delete, name='department_delete'),
    
    # Designation Management URLs
    path('master-data/designations/', views.designation_list, name='designation_list'),
    path('master-data/designations/add/', views.designation_create, name='designation_create'),
    path('master-data/designations/<int:pk>/edit/', views.designation_edit, name='designation_edit'),
    path('master-data/designations/<int:pk>/delete/', views.designation_delete, name='designation_delete'),

    path('master-data/roles/', views.role_list, name='role_list'),
    path('master-data/roles/create/', views.role_create, name='role_create'),
    path('master-data/roles/<int:pk>/edit/', views.role_edit, name='role_edit'),
    path('master-data/roles/<int:pk>/delete/', views.role_delete, name='role_delete'),
    
    path('employees/warnings/', views.warning_list, name='warning_list'),
    path('employees/add-warning/', views.add_warning, name='add_warning'),
    path('employees/warnings/delete/<int:warning_id>/', views.delete_warning, name='delete_warning'),
    path('master-data/warning-list/', views.warning_master_list, name='warning_master_list'),
    path('master-data/warning-remove/<int:pk>/', views.warning_master_delete, name='warning_master_delete'),
    path('master-data/message-category/edit/<int:pk>/', views.message_category_edit, name='message_category_edit'),
    path('master-data/message-category/delete/<int:pk>/', views.message_category_delete, name='message_category_delete'),
    # CATEGORY MASTER
    path('master-data/message-category/', views.message_category_list, name='message_category_list'),
    path('master-data/message-category/create/', views.message_category_create, name='message_category_create'),

    # SUBTYPE MASTER
    path('master-data/message-subtype/<int:category_id>/', views.message_subtype_list, name='message_subtype_list'),
    path('master-data/message-subtype/create/', views.message_subtype_create, name='message_subtype_create'),

    # SUBTYPE
    path('master-data/message-subtype/edit/<int:pk>/', views.message_subtype_edit, name='message_subtype_edit'),
    path('master-data/message-subtype/delete/<int:pk>/', views.message_subtype_delete, name='message_subtype_delete'),

    # AJAX
    path('ajax/load-subtypes/', views.load_subtypes, name="load_subtypes"),
    
    path('permission-center/', views.permission_center, name='permission_center'),
    path('get-roles/', views.get_roles, name='get_roles'),
    path('get-all-menus/', views.get_all_menus, name='get_all_menus'),
    path('get-assigned-permissions/', views.get_assigned_permissions, name='get_assigned_permissions'),
    path('assign-permissions/', views.assign_permissions, name='assign_permissions'),
    
    
    
    # Domain management URLs
    path('domain-management/', views.domain_management, name='domain_management'),
    path('domain-management/add/', views.add_domain, name='add_domain'),
    path('domain-management/<int:domain_id>/update/', views.update_domain, name='update_domain'),
    path('domain-management/<int:domain_id>/toggle/', views.toggle_domain_status, name='toggle_domain_status'),
    path('domain-management/<int:domain_id>/delete/', views.delete_domain, name='delete_domain'),
    path('domain-management/<int:domain_id>/details/', views.get_domain_details, name='get_domain_details'),
    path('send-celebration-wish/', views.send_celebration_wish, name='send_celebration_wish'),
    path('celebration-wishes/<int:celebrant_id>/', views.get_celebration_wishes, name='get_celebration_wishes'),
    
]