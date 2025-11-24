# leave/admin.py
from django.contrib import admin
from .models import Leave, LeaveType, Region, Holiday
from hr.models import Employee

@admin.register(LeaveType)
class LeaveTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'max_days']
    search_fields = ['name']
    ordering = ['name']
    
    def get_name_display(self, obj):
        return obj.get_name_display()
    get_name_display.short_description = 'Leave Type'

@admin.register(Leave)
class LeaveAdmin(admin.ModelAdmin):
    list_display = ['employee', 'leave_type', 'start_date', 'end_date', 'days_requested', 'status', 'applied_date']
    list_filter = ['status', 'leave_type', 'start_date', 'applied_date']
    search_fields = ['employee__first_name', 'employee__last_name', 'employee__employee_id', 'reason']
    date_hierarchy = 'start_date'
    ordering = ['-applied_date']
    
    fieldsets = (
        ('Employee Information', {
            'fields': ('employee', 'leave_type')
        }),
        ('Leave Details', {
            'fields': ('start_date', 'end_date', 'days_requested', 'reason')
        }),
        ('Approval Information', {
            'fields': ('status', 'approved_by', 'approved_date', 'rejection_reason')
        }),
    )
    
    readonly_fields = ['applied_date']
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('employee', 'leave_type', 'approved_by')
    
    def save_model(self, request, obj, form, change):
        if obj.status in ['approved', 'rejected'] and not obj.approved_by:
            obj.approved_by = request.user
            from django.utils import timezone
            obj.approved_date = timezone.now()
        super().save_model(request, obj, form, change)

@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'code', 'description']
    ordering = ['name']
    
    fieldsets = (
        ('Region Information', {
            'fields': ('name', 'code', 'description', 'is_active')
        }),
    )

@admin.register(Holiday)
class HolidayAdmin(admin.ModelAdmin):
    list_display = ['name', 'region', 'date', 'is_optional', 'created_at']
    list_filter = ['region', 'is_optional', 'date']
    search_fields = ['name', 'description', 'region__name']
    date_hierarchy = 'date'
    ordering = ['date']
    
    fieldsets = (
        ('Holiday Information', {
            'fields': ('region', 'name', 'date', 'is_optional', 'description')
        }),
    )
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('region')