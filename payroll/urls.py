from django.urls import path
from . import views

urlpatterns = [
    # Salary Components
    path('salary-components/', views.salary_components, name='salary_components'),
    path('salary-components/add/', views.add_salary_component, name='add_salary_component'),
    path('salary-components/edit/<int:component_id>/', views.edit_salary_component, name='edit_salary_component'),
    path('salary-components/delete/<int:component_id>/', views.delete_salary_component, name='delete_salary_component'),
    path('salary-components/toggle/<int:component_id>/', views.toggle_salary_component, name='toggle_salary_component'),
    
    # Employee Salaries
    path('employee-salaries/', views.employee_salaries, name='employee_salaries'),
    path('employee-salaries/add/', views.add_employee_salary, name='add_employee_salary'),
    path('employee-salaries/edit/<int:salary_id>/', views.edit_employee_salary, name='edit_employee_salary'),
    path('employee-salaries/view/<int:salary_id>/', views.view_employee_salary, name='view_employee_salary'),
    
    # Payroll Runs
    path('payroll-runs/', views.payroll_runs, name='payroll_runs'),
    path('payroll-runs/create/', views.create_payroll_run, name='create_payroll_run'),
    path('payroll-runs/process/<int:run_id>/', views.process_payroll_run, name='process_payroll_run'),
    path('payroll-runs/view/<int:run_id>/', views.view_payroll_run, name='view_payroll_run'),
    path('payroll-runs/delete/<int:run_id>/', views.delete_payroll_run, name='delete_payroll_run'),
    
    # Payslips
    path('payslips/', views.payslips, name='payslips'),
    path('payslips/view/<int:payslip_id>/', views.view_payslip, name='view_payslip'),
    path('payslips/download/<int:payslip_id>/', views.download_payslip, name='download_payslip'),
    
    # API endpoints
    path('api/calculate-salary/', views.calculate_salary_api, name='calculate_salary_api'),
    path('api/employee-salary-data/<int:employee_id>/', views.get_employee_salary_data, name='employee_salary_data'),
]