from django.db import models

# Create your models here.
from hr.models import Employee

class SalaryComponent(models.Model):
    COMPONENT_TYPES = [
        ('earning', 'Earning'),
        ('deduction', 'Deduction'),
    ]
    
    CALCULATION_TYPES = [
        ('fixed', 'Fixed Amount'),
        ('formula', 'Formula Based'),
        ('percentage', 'Percentage'),
    ]
    
    name = models.CharField(max_length=200)
    component_type = models.CharField(max_length=20, choices=COMPONENT_TYPES)
    calculation_type = models.CharField(max_length=20, choices=CALCULATION_TYPES, default='fixed')
    value = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    formula = models.CharField(max_length=500, null=True, blank=True)
    percentage_of = models.CharField(max_length=100, null=True, blank=True)
    is_taxable = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'payroll_salarycomponent'
    
    def __str__(self):
        return self.name

class EmployeeSalary(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    effective_date = models.DateField()
    basic_salary = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    gross_salary = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    net_salary = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'payroll_employeesalary'

class EmployeeSalaryComponent(models.Model):
    employee_salary = models.ForeignKey(EmployeeSalary, on_delete=models.CASCADE)
    component = models.ForeignKey(SalaryComponent, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.CharField(max_length=100, null=True, blank=True)
    updated_by = models.CharField(max_length=100, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    
    class Meta:
        db_table = 'payroll_employeesalarycomponent'

class PayrollRun(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    name = models.CharField(max_length=200)
    payroll_year = models.IntegerField()
    payroll_month = models.IntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    total_employees = models.IntegerField(default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    processed_by = models.CharField(max_length=200, null=True, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'payroll_payrollrun'
        # unique_together = ['payroll_year', 'payroll_month']
    
    def __str__(self):
        return f"{self.name} - {self.payroll_month}/{self.payroll_year}"
    
    def get_month_name(self):
        """Get month name from month number"""
        from datetime import datetime
        return datetime(2000, self.payroll_month, 1).strftime('%B')
    
    def get_total_payslips(self):
        """Get total payslips for this payroll run"""
        return self.payslip_set.count()
    
    def get_month_name(self):
        """Get month name from month number"""
        month_names = [
            'January', 'February', 'March', 'April', 'May', 'June',
            'July', 'August', 'September', 'October', 'November', 'December'
        ]
        return month_names[self.payroll_month - 1] if 1 <= self.payroll_month <= 12 else 'Unknown'

class Payslip(models.Model):
    STATUS_CHOICES = [
        ('generated', 'Generated'),
        ('approved', 'Approved'),
        ('paid', 'Paid'),
    ]
    
    payroll_run = models.ForeignKey(PayrollRun, on_delete=models.CASCADE)
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    payslip_number = models.CharField(max_length=100, unique=True)
    basic_salary = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    gross_earnings = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_deductions = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    net_salary = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    working_days = models.IntegerField()
    paid_days = models.IntegerField()
    leave_days = models.IntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='generated')
    generated_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'payroll_payslip'

class PayslipComponent(models.Model):
    COMPONENT_TYPES = [
        ('earning', 'Earning'),
        ('deduction', 'Deduction'),
    ]
    
    payslip = models.ForeignKey(Payslip, on_delete=models.CASCADE)
    component = models.ForeignKey(SalaryComponent, on_delete=models.CASCADE)
    component_type = models.CharField(max_length=20, choices=COMPONENT_TYPES)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    calculation_note = models.TextField(null=True, blank=True)
    
    class Meta:
        db_table = 'payroll_payslipcomponent'