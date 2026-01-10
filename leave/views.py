from decimal import Decimal
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.db.models import Count, Q ,Sum
from django.utils import timezone
from datetime import date, datetime, timedelta,time

from django.contrib import messages
from django.core.paginator import Paginator

from leave.forms import LeaveTypeForm
from .models import Leave, LeaveType, Region, Holiday ,LeaveBalance
from hr.models import Employee, Location
from calendar import monthrange

# IMPORT THE NEW SERVICES
from .services import (
    AutoLeaveBalanceService,
    LeaveValidationService, 
    ProbationService, 
    LeaveAccrualService,
    OptionalLeaveService,
    initialize_employee_leave_balances
)

def leave_dashboard(request):
    """Main dashboard view with leave statistics"""
    # Check authentication via session
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    user_role = request.session.get('user_role')
    is_hr_admin_manager = user_role in ['HR', 'Admin', 'Manager','Super Admin','BRANCH MANAGER','TL']
    
    today = timezone.now().date()
    current_year = today.year
    
    # Get logged-in user's region/location
    user_email = request.session.get('user_email')
    user_region = None
    default_region_id = None
    current_branch_manager_location = None
    
    try:
        # Try to get employee's location
        employee = Employee.objects.get(email=user_email)
        if employee.location:
            # Find matching region by location name
            region = Location.objects.filter(
                Q(name__iexact=employee.location) | 
                Q(code__iexact=employee.location),
                is_active=True
            ).first()
            if region:
                user_region = region
                default_region_id = region.id
            current_branch_manager_location = employee.location
    except Employee.DoesNotExist:
        pass
    
    # ✅ Role-based employee filtering for statistics
    if user_role in ['ADMIN', 'HR', 'SUPER ADMIN']:
        total_employees = Employee.objects.count()
    elif user_role == 'BRANCH MANAGER':
        try:
            current_branch_manager = Employee.objects.get(email=user_email)
            if current_branch_manager.location:
                total_employees = Employee.objects.filter(
                    location__iexact=current_branch_manager.location
                ).count()
            else:
                total_employees = 0
        except Employee.DoesNotExist:
            total_employees = 0
    elif user_role in ['MANAGER','TL']:
        # Get the current manager's employee record
        current_manager = Employee.objects.get(email=user_email)
           
        # Filter by reporting_manager_id OR by reporting_manager name (fallback)
        total_employees = Employee.objects.filter(
             Q(reporting_manager_id=current_manager.id) |
                Q(reporting_manager__icontains=current_manager.first_name)
            ).order_by('first_name').count()
        # Existing manager logic
        # total_employees = Employee.objects.filter(
        #     department=request.session.get('user_department')
        # ).count()
    else:
        total_employees = 0
    
    # Today Present (employees not on leave today)
    if user_role in ['ADMIN', 'HR', 'SUPER ADMIN']:
        employees_on_leave_today = Leave.objects.filter(
            start_date__lte=today,
            end_date__gte=today,
            status='approved'
        ).values_list('employee_id', flat=True)
    elif user_role == 'BRANCH MANAGER':
        try:
            current_branch_manager = Employee.objects.get(email=user_email)
            if current_branch_manager.location:
                employees_on_leave_today = Leave.objects.filter(
                    start_date__lte=today,
                    end_date__gte=today,
                    status='approved',
                    employee__location__iexact=current_branch_manager.location
                ).values_list('employee_id', flat=True)
            else:
                employees_on_leave_today = []
        except Employee.DoesNotExist:
            employees_on_leave_today = []
    elif user_role in ['MANAGER','TL']:
        try:
            # FIX: Get the current manager's employee record
            current_manager = Employee.objects.get(email=user_email)
            
            # FIX: Get team members using the SAME filter as total_employees
            manager_team_qs = Employee.objects.filter(
                Q(reporting_manager_id=current_manager.id) |
                Q(reporting_manager__icontains=current_manager.first_name)
            )
            
            # Get approved leaves for these team members today
            employees_on_leave_today = Leave.objects.filter(
                start_date__lte=today,
                end_date__gte=today,
                status='approved',
                employee__in=manager_team_qs
            ).values_list('employee_id', flat=True)
        except Employee.DoesNotExist:
            employees_on_leave_today = []
    else:
        employees_on_leave_today = []
        
    today_present = total_employees - len(set(employees_on_leave_today))
    today_present_percentage = int((today_present / total_employees) * 100) if total_employees > 0 else 0
    
    # =============================================
    # NOTICE THRESHOLD (used later)
    # =============================================
    NOTICE_THRESHOLD = timedelta(days=3)
    
    # 🔹 Handle date filtering (from query params)
    from_date = request.GET.get('from_date')
    to_date = request.GET.get('to_date')
    status_filter = request.GET.get('status', '')  # 🆕 Get status filter
    
    # Variables for display in template (DD-MM-YYYY format)
    from_date_display = from_date
    to_date_display = to_date
    filter_error = None
    show_today_filter = False
    
    # Convert DD-MM-YYYY to YYYY-MM-DD for database queries
    from_date_db = None
    to_date_db = None
    
    # 🔹 DEFAULT TO TODAY if no filters applied
    if not from_date and not to_date:
        from_date_db = today
        to_date_db = today
        from_date_display = today.strftime('%d-%m-%Y')
        to_date_display = today.strftime('%d-%m-%Y')
        show_today_filter = True
    else:
        # Parse DD-MM-YYYY format from form
        if from_date:
            try:
                from_date_db = datetime.strptime(from_date, '%d-%m-%Y').date()
            except ValueError:
                try:
                    # Fallback: try YYYY-MM-DD format
                    from_date_db = datetime.strptime(from_date, '%Y-%m-%d').date()
                    from_date_display = from_date_db.strftime('%d-%m-%Y')
                except ValueError:
                    filter_error = "Invalid From Date format. Please use DD-MM-YYYY."
        
        if to_date:
            try:
                to_date_db = datetime.strptime(to_date, '%d-%m-%Y').date()
            except ValueError:
                try:
                    # Fallback: try YYYY-MM-DD format
                    to_date_db = datetime.strptime(to_date, '%Y-%m-%d').date()
                    to_date_display = to_date_db.strftime('%d-%m-%Y')
                except ValueError:
                    filter_error = "Invalid To Date format. Please use DD-MM-YYYY."

    # Validate date range
    if from_date_db and to_date_db and not filter_error:
        if from_date_db > to_date_db:
            filter_error = "From date cannot be greater than To date"
    
    # ✅ employees_on_leave_today should also count from from_date to to_date
    if not filter_error:
        # safety: if one side is missing, default it to today (shouldn't happen with your logic)
        if not from_date_db:
            from_date_db = today
        if not to_date_db:
            to_date_db = today

        # base overlap condition for the selected range
        base_filter = Q(
            start_date__lte=to_date_db,
            end_date__gte=from_date_db,
            status='approved'
        )

        if user_role in ['ADMIN', 'HR', 'SUPER ADMIN']:
            employees_on_leave_today_qs = Leave.objects.filter(base_filter)
        elif user_role == 'BRANCH MANAGER':
            if current_branch_manager_location:
                employees_on_leave_today_qs = Leave.objects.filter(
                    base_filter,
                    employee__location__iexact=current_branch_manager_location
                )
            else:
                employees_on_leave_today_qs = Leave.objects.none()
        elif user_role in ['MANAGER','TL']:
            # FIX: Use reporting manager filter here too
            try:
                current_manager = Employee.objects.get(email=user_email)
                manager_team_qs = Employee.objects.filter(
                    Q(reporting_manager_id=current_manager.id) |
                    Q(reporting_manager__icontains=current_manager.first_name)
                )
                
                employees_on_leave_today_qs = Leave.objects.filter(
                    base_filter,
                    employee__in=manager_team_qs
                )
            except Employee.DoesNotExist:
                employees_on_leave_today_qs = Leave.objects.none()
        else:
            employees_on_leave_today_qs = Leave.objects.none()

        employees_on_leave_today = employees_on_leave_today_qs.values_list(
            'employee_id', flat=True
        )
    else:
        employees_on_leave_today = []

    today_present = total_employees - len(set(employees_on_leave_today))
    today_present_percentage = int((today_present / total_employees) * 100) if total_employees > 0 else 0
    
     # Get current user employee object for exclusion
    current_user_emp = None
    try:
        current_user_emp = Employee.objects.get(email=user_email)
    except Employee.DoesNotExist:
        pass
    
    
    # Recent leaves with role-based filtering
    recent_leaves = Leave.objects.select_related('employee', 'leave_type')
    
    # EXCLUDE CURRENT USER'S LEAVES from recent_leaves
    if current_user_emp:
        recent_leaves = recent_leaves.exclude(employee=current_user_emp)
        
        
    if user_role in ['MANAGER', 'TL']:
      
        current_manager = Employee.objects.get(email=user_email)

        manager_team_qs = Employee.objects.filter(
             Q(reporting_manager_id=current_manager.id) |
                Q(reporting_manager__icontains=current_manager.first_name)
            )
        recent_leaves = recent_leaves.filter(employee__in=list(manager_team_qs))
    elif user_role == 'BRANCH MANAGER' and current_branch_manager_location:
        recent_leaves = recent_leaves.filter(employee__location__iexact=current_branch_manager_location)

    # 🔹 UPDATED: Show pending status leaves if end date hasn't passed
    if not filter_error:
        if from_date_db and to_date_db:
            # When both dates are provided, show leaves that:
            # 1. Overlap with the date range OR
            # 2. Are pending/new AND end date hasn't passed
            recent_leaves = recent_leaves.filter(
                # Leaves that overlap with the selected date range
                Q(start_date__lte=to_date_db, end_date__gte=from_date_db) |
                # Pending/New leaves that haven't ended yet
                Q(status__in=['pending', 'new'], end_date__gte=today)
            ).distinct()
        elif from_date_db:
            # Only from_date provided - show leaves that:
            recent_leaves = recent_leaves.filter(
                Q(end_date__gte=from_date_db) |
                Q(status__in=['pending', 'new'], end_date__gte=today)
            ).distinct()
        elif to_date_db:
            # Only to_date provided - show leaves that:
            recent_leaves = recent_leaves.filter(
                Q(start_date__lte=to_date_db) |
                Q(status__in=['pending', 'new'], end_date__gte=today)
            ).distinct()
        else:
            # No date filters - show leaves that are either:
            # - Within today's date range OR
            # - Are pending/new and haven't ended yet
            recent_leaves = recent_leaves.filter(
                Q(start_date__lte=today, end_date__gte=today) |
                Q(status__in=['pending', 'new'], end_date__gte=today)
            ).distinct()
    
    branch_filter = request.GET.get('branch', '')
    # 🆕 Apply status filter to the table (if provided)
    if status_filter:
        recent_leaves = recent_leaves.filter(status=status_filter)
    if branch_filter:
        recent_leaves = recent_leaves.filter(employee__location=branch_filter)
        
    recent_leaves = recent_leaves.order_by('-applied_date')[:50]  # limit for performance

    # =============================================
    # INTEGRATED PLANNED vs SHORT-NOTICE LOGIC (FILTERED)
    # =============================================
    # Base queryset for approved leaves (role-based)
    if user_role in ['ADMIN', 'HR', 'SUPER ADMIN']:
        planned_unplanned_base = Leave.objects.filter(
            status='approved',
            applied_date__isnull=False
        )
    elif user_role == 'BRANCH MANAGER':
        try:
            current_branch_manager = Employee.objects.get(email=user_email)
            if current_branch_manager.location:
                planned_unplanned_base = Leave.objects.filter(
                    status='approved',
                    applied_date__isnull=False,
                    employee__location__iexact=current_branch_manager.location
                )
            else:
                planned_unplanned_base = Leave.objects.none()
        except Employee.DoesNotExist:
            planned_unplanned_base = Leave.objects.none()
    elif user_role in ['MANAGER','TL']:
        # FIX: Use reporting manager filter instead of department
        try:
            current_manager = Employee.objects.get(email=user_email)
            manager_team_qs = Employee.objects.filter(
                Q(reporting_manager_id=current_manager.id) |
                Q(reporting_manager__icontains=current_manager.first_name)
            )
            
            planned_unplanned_base = Leave.objects.filter(
                status='approved',
                applied_date__isnull=False,
                employee__in=manager_team_qs
            )
        except Employee.DoesNotExist:
            planned_unplanned_base = Leave.objects.none()
            
    else:
        planned_unplanned_base = Leave.objects.none()

    # Apply date overlap filters to match recent_leaves window (or today's window when no filters)
    if not filter_error:
        if from_date_db and to_date_db:
            planned_unplanned_base = planned_unplanned_base.filter(
                Q(start_date__lte=to_date_db, end_date__gte=from_date_db)
            )
        elif from_date_db:
            planned_unplanned_base = planned_unplanned_base.filter(
                Q(end_date__gte=from_date_db)
            )
        elif to_date_db:
            planned_unplanned_base = planned_unplanned_base.filter(
                Q(start_date__lte=to_date_db)
            )
        else:
            planned_unplanned_base = planned_unplanned_base.filter(
                Q(start_date__lte=today, end_date__gte=today)
            )

    # Apply branch filter if present so counts match the table's branch selection
    if branch_filter:
        planned_unplanned_base = planned_unplanned_base.filter(employee__location=branch_filter)

    # Compute planned vs unplanned using NOTICE_THRESHOLD
    planned_leaves = 0
    unplanned_leaves = 0

    for leave in planned_unplanned_base.only('start_date', 'applied_date'):
        try:
            applied_raw = leave.applied_date
            applied_date = applied_raw.date() if hasattr(applied_raw, 'date') else applied_raw

            if not applied_date or not leave.start_date:
                unplanned_leaves += 1
                continue

            delta = leave.start_date - applied_date
            if delta >= NOTICE_THRESHOLD:
                planned_leaves += 1
            else:
                unplanned_leaves += 1
        except Exception:
            unplanned_leaves += 1

    planned_leaves_percentage = int((planned_leaves / total_employees) * 100) if total_employees > 0 else 0
    unplanned_leaves_percentage = int((unplanned_leaves / total_employees) * 100) if total_employees > 0 else 0

    # =============================================
    # PENDING REQUESTS WITH DATE FILTERING + ROLE-BASED (FIXED)
    # -> Now mirrors the table's date/branch scope so counts align
    # =============================================
    if user_role in ['ADMIN', 'HR', 'SUPER ADMIN']:
        pending_base = Leave.objects.filter(
            status__in=['pending', 'new']
        ).exclude(status='withdrawn')
    elif user_role == 'BRANCH MANAGER':
        try:
            current_branch_manager = Employee.objects.get(email=user_email)
            if current_branch_manager.location:
                pending_base = Leave.objects.filter(
                    status__in=['pending', 'new'],
                    employee__location__iexact=current_branch_manager.location
                ).exclude(status='withdrawn')
            else:
                pending_base = Leave.objects.none()
        except Employee.DoesNotExist:
            pending_base = Leave.objects.none()
    elif user_role in ['MANAGER','TL']:
        current_manager = Employee.objects.get(email=user_email)
        pending_base = Leave.objects.filter(
            status__in=['pending', 'new'],
            employee__in=Employee.objects.filter(
            Q(reporting_manager_id=current_manager.id) |
            Q(reporting_manager__icontains=current_manager.first_name)
        )).exclude(status='withdrawn')
    else:
        pending_base = Leave.objects.none()

    # Apply SAME date overlap logic as recent_leaves so pending count respects selected range
    if not filter_error:
        if from_date_db and to_date_db:
            pending_base = pending_base.filter(
                Q(applied_date__date__range=(from_date_db, to_date_db)) |
                Q(start_date__lte=to_date_db, end_date__gte=from_date_db) |
                Q(end_date__gte=from_date_db)
            )
        elif from_date_db:
            pending_base = pending_base.filter(
                Q(applied_date__date__gte=from_date_db) |
                Q(end_date__gte=from_date_db)
            )
        elif to_date_db:
            pending_base = pending_base.filter(
                Q(applied_date__date__lte=to_date_db) |
                Q(start_date__lte=to_date_db)
            )
        else:
            # default -> today's window
            pending_base = pending_base.filter(
                Q(applied_date__date=today) |
                Q(start_date__lte=today, end_date__gte=today) |
                Q(end_date__gte=today)
            )

    # Apply branch filter to pending count as well
    if branch_filter:
        pending_base = pending_base.filter(employee__location=branch_filter)

    pending_requests = pending_base.distinct().count()
    pending_requests_percentage = int((pending_requests / total_employees) * 100) if total_employees > 0 else 0
    
    # =============================================
    # ADD NOTICE TYPE TO RECENT LEAVES
    # =============================================
    # Evaluate queryset to a list so we can attach computed attributes safely
    recent_leaves_list = list(recent_leaves)
    
    # Compute notice_type for each leave instance
    # Replace the problematic section with this:
    for leave in recent_leaves_list:
        notice = 'unknown'
        advance_notice_warning = False
        working_days = leave.days_requested or 0
        
        try:
            # Check if we have the necessary dates
            if getattr(leave, 'applied_date', None) and getattr(leave, 'start_date', None):
                applied_val = leave.applied_date
                if hasattr(applied_val, 'date'):
                    applied_date_val = applied_val.date()
                else:
                    applied_date_val = applied_val
                
                # Calculate days between applied date and start date
                days_until_start = (leave.start_date - applied_date_val).days
                
                # Check for short notice (less than 3 days notice)
                if days_until_start >= 0:  # Only check if applied before or on start date
                    if days_until_start < 3:  # Less than 3 days notice
                        notice = 'short_notice'
                    else:
                        notice = 'planned'
                    
                    # Check advance notice requirements for warning highlighting
                    if not leave.is_half_day and working_days >= 3 and days_until_start >= 0:
                        # For 3+ working days: need at least 7 days advance notice
                        # For 7+ working days: need at least 15 days advance notice
                        if working_days >= 7 and days_until_start < 15:
                            advance_notice_warning = True
                            print(f"WARNING: {leave.employee.first_name} - {working_days} days leave, only {days_until_start} days notice")
                        elif working_days >= 3 and working_days < 7 and days_until_start < 7:
                            advance_notice_warning = True
                            print(f"WARNING: {leave.employee.first_name} - {working_days} days leave, only {days_until_start} days notice")
                else:
                    # Applied after start date - definitely a warning
                    notice = 'late_application'
                    advance_notice_warning = True
            else:
                notice = leave.status or 'unknown'
        except Exception as e:
            print(f"Error calculating notice for leave {leave.id}: {e}")
            notice = leave.status or 'unknown'
        
        leave.notice_type = notice
        leave.advance_notice_warning = advance_notice_warning
        leave.working_days = working_days
    
    # Get all active regions with their holidays for current year
    regions = Location.objects.filter(is_active=True).prefetch_related(
        'holidays'
    ).order_by('name')
    
    # Get all holidays for current year
    holidays = Holiday.objects.filter(
        date__year=current_year
    ).select_related('region').order_by('date')
    if user_region:
        current_year_holidays_count = Holiday.objects.filter(
            date__year=current_year,
            region=user_region
        ).count()
    else:
        current_year_holidays_count = Holiday.objects.filter(
            date__year=current_year
        ).count()
    context = {
        'is_hr_admin_manager': is_hr_admin_manager,
        'employees_on_leave_today': len(set(employees_on_leave_today)),
        'today_present': today_present,
        'today_present_total': total_employees,
        'today_present_percentage': today_present_percentage,
        
        'from_date_display': from_date_display,
        'to_date_display': to_date_display,
        'status_filter': status_filter,  
        'filter_error': filter_error,
        'show_today_filter': show_today_filter,
        
        'planned_leaves': planned_leaves,
        'planned_leaves_total': total_employees,
        'planned_leaves_percentage': planned_leaves_percentage,
        
        'unplanned_leaves': unplanned_leaves,
        'unplanned_leaves_total': total_employees,
        'unplanned_leaves_percentage': unplanned_leaves_percentage,
        
        'pending_requests': pending_requests,
        'pending_requests_total': total_employees,
        'pending_requests_percentage': pending_requests_percentage,
        
        'recent_leaves': recent_leaves_list,  
        'current_year': current_year,
        'regions': regions,
        'holidays': holidays,
        'current_year_holidays_count': current_year_holidays_count,
        'user_region': user_region,
        'default_region_id': default_region_id,
        'notice_threshold_days': 3,  
        # 'advance_notice_warning':advance_notice_warning
    }
    
    
    return render(request, 'leave/leave_dashboard.html', context)

def leave_list(request):
    """List all leaves with comprehensive filtering options"""
    # Check authentication
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    leaves = Leave.objects.select_related(
        'employee',
        'leave_type',
        'approved_by'
    ).all()
    
    # Filter by status
    status_filter = request.GET.get('status')
    if status_filter:
        leaves = leaves.filter(status=status_filter)
    
    # Filter by leave type
    leave_type_filter = request.GET.get('leave_type')
    if leave_type_filter:
        leaves = leaves.filter(leave_type_id=leave_type_filter)
    
    # Filter by region (using location field from Employee)
    region_filter = request.GET.get('region')
    if region_filter:
        leaves = leaves.filter(employee__location=region_filter)
    
    # Filter by department
    department_filter = request.GET.get('department')
    if department_filter:
        leaves = leaves.filter(employee__department=department_filter)
    
    # Filter by date range
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d').date()
            leaves = leaves.filter(start_date__gte=date_from_obj)
        except ValueError:
            pass
    
    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d').date()
            leaves = leaves.filter(end_date__lte=date_to_obj)
        except ValueError:
            pass
    
    # Search functionality
    search_query = request.GET.get('search')
    if search_query:
        leaves = leaves.filter(
            Q(employee__first_name__icontains=search_query) |
            Q(employee__last_name__icontains=search_query) |
            Q(employee__employee_id__icontains=search_query) |
            Q(reason__icontains=search_query)
        )
    
    # Sort functionality
    sort_by = request.GET.get('sort', '-applied_date')
    if sort_by:
        leaves = leaves.order_by(sort_by)
    
    # Pagination
    paginator = Paginator(leaves, 20)
    page_number = request.GET.get('page', 1)
    leaves_page = paginator.get_page(page_number)
    
    # Get filter options
    leave_types = LeaveType.objects.all()
    regions = Location.objects.filter(is_active=True)
    departments = Employee.objects.values_list('department', flat=True).distinct().order_by('department')
    
    context = {
        'leaves': leaves_page,
        'leave_types': leave_types,
        'regions': regions,
        'departments': departments,
        'status_choices': Leave.STATUS_CHOICES,
        
        # Current filters
        'current_status': status_filter,
        'current_leave_type': leave_type_filter,
        'current_region': region_filter,
        'current_department': department_filter,
        'date_from': date_from,
        'date_to': date_to,
        'search_query': search_query,
        'sort_by': sort_by,
        
        # Statistics
        'total_leaves': leaves.count(),
        'pending_count': Leave.objects.filter(status='pending').count(),
        'approved_count': Leave.objects.filter(status='approved').count(),
        'rejected_count': Leave.objects.filter(status='rejected').count(),
    }
    
    return render(request, 'leave/leave_list.html', context)

def calculate_working_days_with_optional(start_date, end_date, location=None):
    """
    Calculate working days between two dates, excluding:
    - Sundays (only Sunday, not Saturday)
    - National holidays (region=None or 'National') where is_optional=False
    - State holidays for the employee's location where is_optional=False
    
    BUT INCLUDING:
    - Optional holidays (is_optional=True) - count as working days
    - Saturdays - count as working days
    
    Args:
        start_date (date): Start date
        end_date (date): End date
        location (str): Employee's location/region name
    
    Returns:
        int: Number of working days
    """
    if start_date > end_date:
        return {
            'working_days': 0,
            'optional_holidays': [],
            'mandatory_holidays': [],
            'total_calendar_days': 0
        }
    
    working_days = 0
    current_date = start_date
    
    # Get mandatory holidays (National + State, non-optional)
    mandatory_holiday_dates = set()
    
    # National mandatory holidays (holiday_type = 'National Holiday' AND is_optional = False)
    national_holidays = Holiday.objects.filter(
        Q(holiday_type__iexact='National Holiday'),
        date__gte=start_date,
        date__lte=end_date,
        is_optional=False
    ).values_list('date', flat=True)
    
    mandatory_holiday_dates.update(national_holidays)
    
    # State mandatory holidays for the specific location
    if location:
        matching_region = Location.objects.filter(
            name__iexact=location
        ).first()
        
        if matching_region:
            state_holidays = Holiday.objects.filter(
                region=matching_region,
                holiday_type__iexact='State Holiday',
                date__gte=start_date,
                date__lte=end_date,
                is_optional=False
            ).values_list('date', flat=True)
            
            mandatory_holiday_dates.update(state_holidays)
    
    # Get optional holidays (holiday_type = 'Optional Holiday' AND is_optional = True)
    optional_holidays_query = Holiday.objects.filter(
        holiday_type__iexact='Optional Holiday',
        date__gte=start_date,
        date__lte=end_date,
        is_optional=True
    )
    
    # Filter by region if location provided
    if location:
        matching_region = Location.objects.filter(name__iexact=location).first()
        if matching_region:
            optional_holidays_query = optional_holidays_query.filter(
                Q(region=matching_region) | Q(region__isnull=True)
            )
    
    optional_holidays_list = []
    optional_holiday_dates = set()
    
    for holiday in optional_holidays_query:
        optional_holidays_list.append({
            'date': holiday.date,
            'name': holiday.name,
            'region': holiday.region.name if holiday.region else 'National',
            'id': holiday.id
        })
        optional_holiday_dates.add(holiday.date)
    
    # Calculate working days (exclude Sundays and mandatory holidays)
    total_calendar_days = 0
    while current_date <= end_date:
        total_calendar_days += 1
        
        # Exclude Sundays (weekday 6) and mandatory holidays
        # Optional holidays are COUNTED as working days initially
        if current_date.weekday() != 6 and current_date not in mandatory_holiday_dates:
            working_days += 1
        
        current_date += timedelta(days=1)
    
    return {
        'working_days': working_days,
        'optional_holidays': optional_holidays_list,
        'mandatory_holidays': list(mandatory_holiday_dates),
        'total_calendar_days': total_calendar_days
    }


def apply_leave(request):
    user_email = request.session.get('user_email')
    user_role = request.session.get('user_role')
    
    try:
        employee = Employee.objects.get(email=user_email)
    except Employee.DoesNotExist:
        messages.error(request, 'Employee profile not found.')
        return redirect('employee_dashboard')
    
    if request.method == 'POST':
        try:
            leave_type_id = request.POST.get('leave_type')
            start_date = request.POST.get('start_date')
            end_date = request.POST.get('end_date')
            reason = request.POST.get('reason')
            
            # Get optional holidays that user wants to use
            selected_optional_holidays = request.POST.getlist('optional_holidays')
            
            # Half-day data
            is_half_day = request.POST.get('is_half_day', 'false') == 'true'
            half_day_period = request.POST.get('half_day_period', '')
            
            print(f"DEBUG Apply Leave:")
            print(f"leave_type_id: '{leave_type_id}'")
            print(f"start_date: '{start_date}'")
            print(f"end_date: '{end_date}'")
            print(f"reason: '{reason}'")
            print(f"selected_optional_holidays: {selected_optional_holidays}")
            
            # For half-day leaves, set end_date to start_date if empty
            if is_half_day and (not end_date or end_date.strip() == '' or end_date == 'DD-MM-YYYY'):
                end_date = start_date
                print(f"Half-day: Auto-set end_date to start_date: {end_date}")
            
            # Validate required fields
            missing_fields = []
            if not leave_type_id or leave_type_id.strip() == '' or leave_type_id == 'Select Leave Type':
                missing_fields.append('Leave Type')
            if not start_date or start_date.strip() == '' or start_date == 'DD-MM-YYYY':
                missing_fields.append('Start Date')
            if not end_date or end_date.strip() == '' or end_date == 'DD-MM-YYYY':
                missing_fields.append('End Date')
            if not reason or reason.strip() == '':
                missing_fields.append('Reason')
            
            if missing_fields:
                messages.error(request, f'Please fill in: {", ".join(missing_fields)}')
                return redirect('apply_leave')
            
            # Validate and parse dates
            try:
                start_date_obj = datetime.strptime(start_date, '%d-%m-%Y').date()
                end_date_obj = datetime.strptime(end_date, '%d-%m-%Y').date()
            except (ValueError, TypeError) as e:
                print(f"Date parsing error: {e}")
                messages.warning(request, 'Invalid date format. Please select valid dates.')
                return redirect('apply_leave')
            
            if start_date_obj > end_date_obj:
                messages.warning(request, 'Start date cannot be after end date.')
                return redirect('apply_leave')
            
            if start_date_obj < date.today():
                messages.warning(request, 'Cannot apply for leave in the past.')
                return redirect('apply_leave')
            
            # Check for overlapping leaves
            overlapping_leaves = Leave.objects.filter(
                employee=employee,
                status__in=['pending', 'approved'],
                start_date__lte=end_date_obj,
                end_date__gte=start_date_obj
            ).exclude(status='rejected')

            if overlapping_leaves.exists():
                overlap_details = []
                for leave in overlapping_leaves:
                    status_display = "Applied" if leave.status == 'pending' else "Approved"
                    overlap_details.append(
                        f"{leave.start_date.strftime('%d %b %Y')} to {leave.end_date.strftime('%d %b %Y')} "
                        f"({leave.leave_type.name} - {status_display})"
                    )
                
                messages.warning(
                    request,
                    f'❌ Leave date conflict! You already have leaves on these dates: {", ".join(overlap_details)}'
                )
                return redirect('apply_leave')
            
            # Validate half-day period selection
            if is_half_day and not half_day_period:
                messages.warning(request, 'Please select first half or second half for half-day leave.')
                return redirect('apply_leave')
            
            # Calculate working days
            if is_half_day:
                total_working_days = Decimal('0.5')
                days_calculation = {
                    'working_days': 0.5,
                    'optional_holidays': [],
                    'mandatory_holidays': [],
                    'total_calendar_days': 1
                }
                print(f"Half-day detected: Setting total_working_days to 0.5")
            else:
                days_calculation = calculate_working_days_with_optional(
                    start_date=start_date_obj,
                    end_date=end_date_obj,
                    location=employee.location
                )
                total_working_days = Decimal(str(days_calculation['working_days']))
                print(f"✅ Backend calculated working days: {days_calculation}")
                print(f"✅ Total working days (including optional holidays): {total_working_days}")
            
            # Final check
            if not is_half_day and total_working_days <= 0:
                messages.warning(request, 'No working days in the selected date range. Please check your dates.')
                return redirect('apply_leave')
            
            # Get requested leave type
            try:
                requested_leave_type = LeaveType.objects.get(id=leave_type_id)
            except LeaveType.DoesNotExist:
                messages.warning(request, 'Invalid leave type selected.')
                return redirect('apply_leave')
            
            # Check if requested leave type is Optional Leave
            is_optional_leave_type = 'optional' in requested_leave_type.name.lower()
            
            # ============================================
            # OPTIONAL LEAVE STRICT VALIDATION (SINGLE DAY ONLY)
            # ============================================
            if is_optional_leave_type:
                # Optional Leave must be for ONE DAY only
                if start_date_obj != end_date_obj:
                    messages.error(
                        request,
                        "❌ Optional Leave can be applied for only ONE date. "
                        "Please select a single optional holiday."
                    )
                    return redirect('apply_leave')

                # Ensure selected date is actually an optional holiday
                optional_dates = {
                    opt['date'] for opt in days_calculation.get('optional_holidays', [])
                }

                if start_date_obj not in optional_dates:
                    messages.error(
                        request,
                        "❌ The selected date is not an Optional Holiday. "
                        "Please choose a valid optional holiday."
                    )
                    return redirect('apply_leave')

            # SPECIAL VALIDATION: If Optional Leave type is selected, check if dates contain optional holidays
            if is_optional_leave_type and not is_half_day:
                # Get optional holidays for the date range
                optional_holidays_in_range = days_calculation['optional_holidays']
                optional_dates_in_range = {holiday['date'] for holiday in optional_holidays_in_range}
                
                if not optional_dates_in_range:
                    messages.error(
                        request,
                        '❌ Cannot use Optional Leave type for selected dates. '
                        'The selected date range does not contain any optional holidays. '
                        'Please select a different leave type or choose dates that include optional holidays.'
                    )
                    return redirect('apply_leave')
            
            # ============================================
            # HANDLE OPTIONAL HOLIDAYS
            # ============================================
            optional_days_count = 0
            valid_selected_holidays = []
            
            if not is_half_day and selected_optional_holidays:
                # Validate selected optional holidays
                valid_optional_dates = {opt['date'] for opt in days_calculation['optional_holidays']}
                
                for holiday_date_str in selected_optional_holidays:
                    try:
                        holiday_date = datetime.strptime(holiday_date_str, '%Y-%m-%d').date()
                        if holiday_date in valid_optional_dates:
                            valid_selected_holidays.append(holiday_date)
                    except ValueError:
                        continue
                
                optional_days_count = len(valid_selected_holidays)
                print(f"✅ Valid optional holidays selected: {optional_days_count}")
            
            # Get Optional Leave type (initialize it early so it's available in all cases)
            optional_leave_type = None
            if not is_half_day and (optional_days_count > 0 or is_optional_leave_type):
                optional_leave_type = LeaveType.objects.filter(
                    Q(name__icontains='optional') | Q(name__icontains='Optional')
                ).first()
                
                if not optional_leave_type:
                    optional_leave_type = LeaveType.objects.create(
                        name='Optional Leave',
                        description='Optional holidays leave',
                        is_active=True,
                        colour='#28a745'
                    )
                    messages.info(request, 'Created Optional Leave type automatically.')
            
            # ============================================
            # CREATE SEPARATE LEAVE APPLICATIONS
            # ============================================
            
            # Track all created leaves
            created_leaves = []
            
            # 1. Create optional leave applications (if any)
            if not is_half_day and optional_days_count > 0:
                # Check optional leave balance
                optional_balance = LeaveBalance.objects.filter(
                    employee=employee,
                    leave_type=optional_leave_type,
                    year=date.today().year
                ).first()
                
                # ============================================
                # PARTIAL PAID/UNPAID LOGIC FOR OPTIONAL LEAVES
                # ============================================
                is_optional_partial_unpaid = False
                optional_paid_days = Decimal('0.00')
                optional_unpaid_days = Decimal('0.00')
                optional_final_leave_type = optional_leave_type
                
                if optional_balance:
                    optional_available_balance = optional_balance.leaves_remaining
                    print(f"DEBUG: Optional Leave balance available: {optional_available_balance}")
                    print(f"DEBUG: Optional days requested: {optional_days_count}")
                    
                    if optional_available_balance >= optional_days_count:
                        # Sufficient optional balance
                        optional_paid_days = Decimal(str(optional_days_count))
                        optional_unpaid_days = Decimal('0.00')
                        is_optional_partial_unpaid = False
                        print(f"DEBUG: ✅ Sufficient optional balance. Fully PAID optional leave.")
                        
                    elif optional_available_balance > 0:
                        # Partial optional balance
                        optional_paid_days = optional_available_balance
                        optional_unpaid_days = Decimal(str(optional_days_count)) - optional_available_balance
                        is_optional_partial_unpaid = True
                        
                        # Get unpaid leave type for optional portion
                        unpaid_leave_type = LeaveType.objects.filter(
                            is_active=True,
                            name__icontains='unpaid'
                        ).first()
                        
                        if unpaid_leave_type:
                            # Create paid optional leave
                            paid_optional_leave = Leave(
                                employee=employee,
                                leave_type=optional_leave_type,
                                colour=getattr(optional_leave_type, 'colour', '#28a745'),
                                start_date=start_date_obj,
                                end_date=end_date_obj,
                                days_requested=optional_paid_days,
                                reason=f"{reason} - Optional holidays (Paid portion)",
                                status='pending',
                                applied_date=timezone.now(),
                                is_half_day=False,
                                half_day_period=None,
                                is_unpaid=False
                            )
                            paid_optional_leave.save()
                            created_leaves.append(paid_optional_leave)
                            
                            # Create unpaid portion for optional
                            unpaid_optional_leave = Leave(
                                employee=employee,
                                leave_type=unpaid_leave_type,
                                colour=getattr(unpaid_leave_type, 'colour', '#dc3545'),
                                start_date=start_date_obj,
                                end_date=end_date_obj,
                                days_requested=optional_unpaid_days,
                                reason=f"{reason} - Optional holidays (Unpaid portion)",
                                status='pending',
                                applied_date=timezone.now(),
                                is_half_day=False,
                                half_day_period=None,
                                is_unpaid=True
                            )
                            unpaid_optional_leave.save()
                            created_leaves.append(unpaid_optional_leave)
                            
                            messages.warning(
                                request,
                                f'⚠️ Partial optional leave balance available! '
                                f'Optional holidays split into: {optional_paid_days} days PAID + {optional_unpaid_days} days UNPAID.'
                            )
                            print(f"DEBUG: ⚠️ Partial optional balance. Split into {optional_paid_days} paid + {optional_unpaid_days} unpaid.")
                            
                        else:
                            messages.error(request, 'Unpaid leave type not configured. Please contact HR.')
                            return redirect('apply_leave')
                    else:
                        # No optional balance - fully unpaid optional leave
                        optional_paid_days = Decimal('0.00')
                        optional_unpaid_days = Decimal(str(optional_days_count))
                        is_optional_partial_unpaid = True
                else:
                    # No optional balance exists - fully unpaid optional leave
                    optional_paid_days = Decimal('0.00')
                    optional_unpaid_days = Decimal(str(optional_days_count))
                    is_optional_partial_unpaid = True
                
                # If we haven't created optional leaves yet (fully paid or fully unpaid)
                if not created_leaves or (created_leaves and not is_optional_partial_unpaid):
                    # Handle fully unpaid optional leave
                    if is_optional_partial_unpaid and optional_unpaid_days > 0:
                        unpaid_leave_type = LeaveType.objects.filter(
                            is_active=True,
                            name__icontains='unpaid'
                        ).first()
                        
                        if unpaid_leave_type:
                            optional_final_leave_type = unpaid_leave_type
                            
                            messages.warning(
                                request,
                                f'⚠️ No Optional Leave balance available. '
                                f'Optional holidays will be submitted as UNPAID LEAVE.'
                            )
                            print(f"DEBUG: ❌ No optional balance. Fully UNPAID optional leave.")
                        else:
                            messages.error(request, 'Unpaid leave type not configured. Please contact HR.')
                            return redirect('apply_leave')
                    
                    # Create optional leave application
                    if valid_selected_holidays:
                        optional_start = min(valid_selected_holidays)
                        optional_end = max(valid_selected_holidays)
                    else:
                        optional_start = start_date_obj
                        optional_end = end_date_obj

                    optional_leave = Leave(
                        employee=employee,
                        leave_type=optional_final_leave_type,
                        colour=getattr(optional_final_leave_type, 'colour', '#28a745'),
                        start_date=start_date_obj,
                        end_date=end_date_obj,
                        days_requested=Decimal(str(optional_days_count)),
                        reason=f"{reason} - Optional holidays on ({optional_start.strftime('%d-%m-%Y')})",
                        status='pending',
                        applied_date=timezone.now(),
                        is_half_day=False,
                        half_day_period=None,
                        is_unpaid=is_optional_partial_unpaid
                    )
                    optional_leave.save()
                    created_leaves.append(optional_leave)
                
                messages.info(
                    request,
                    f'✅ Created optional leave application for {optional_days_count} day(s)'
                )
            
            # 2. Calculate days for main leave application
            if is_half_day:
                # Half day leave
                main_leave_days = Decimal('0.5')
                should_create_main_leave = True
            else:
                # Calculate main leave days
                main_leave_days = total_working_days - Decimal(str(optional_days_count))
                should_create_main_leave = main_leave_days > 0
            
            # 3. Create main leave application (if needed)
            if should_create_main_leave:
                # For Optional Leave type, create the application
                if is_optional_leave_type:
                    # If user selected Optional Leave type, all days are considered optional
                    optional_days_for_leave_type = total_working_days
                    
                    # ============================================
                    # PARTIAL PAID/UNPAID LOGIC FOR OPTIONAL LEAVE TYPE
                    # ============================================
                    # Check optional leave balance
                    optional_balance = LeaveBalance.objects.filter(
                        employee=employee,
                        leave_type=optional_leave_type,
                        year=date.today().year
                    ).first()
                    
                    is_optional_partial_unpaid = False
                    optional_paid_days = Decimal('0.00')
                    optional_unpaid_days = Decimal('0.00')
                    optional_final_leave_type = optional_leave_type
                    
                    if optional_balance:
                        optional_available_balance = optional_balance.leaves_remaining
                        print(f"DEBUG: Optional Leave balance available: {optional_available_balance}")
                        print(f"DEBUG: Optional days requested: {optional_days_for_leave_type}")
                        
                        if optional_available_balance >= optional_days_for_leave_type:
                            # Sufficient optional balance
                            optional_paid_days = optional_days_for_leave_type
                            optional_unpaid_days = Decimal('0.00')
                            is_optional_partial_unpaid = False
                            print(f"DEBUG: ✅ Sufficient optional balance. Fully PAID optional leave.")
                            
                        elif optional_available_balance > 0:
                            # Partial optional balance - part paid, part unpaid
                            optional_paid_days = optional_available_balance
                            optional_unpaid_days = optional_days_for_leave_type - optional_available_balance
                            is_optional_partial_unpaid = True
                            
                            # Get unpaid leave type
                            unpaid_leave_type = LeaveType.objects.filter(
                                is_active=True,
                                name__icontains='unpaid'
                            ).first()
                            
                            if unpaid_leave_type:
                                # Create paid optional leave
                                paid_optional_leave = Leave(
                                    employee=employee,
                                    leave_type=optional_leave_type,
                                    colour=getattr(optional_leave_type, 'colour', '#28a745'),
                                    start_date=start_date_obj,
                                    end_date=end_date_obj,
                                    days_requested=optional_paid_days,
                                    reason=f"{reason} (Paid portion)",
                                    status='pending',
                                    applied_date=timezone.now(),
                                    is_half_day=False,
                                    half_day_period=None,
                                    is_unpaid=False
                                )
                                paid_optional_leave.save()
                                created_leaves.append(paid_optional_leave)
                                
                                # Create unpaid portion
                                unpaid_optional_leave = Leave(
                                    employee=employee,
                                    leave_type=unpaid_leave_type,
                                    colour=getattr(unpaid_leave_type, 'colour', '#dc3545'),
                                    start_date=start_date_obj,
                                    end_date=end_date_obj,
                                    days_requested=optional_unpaid_days,
                                    reason=f"{reason} (Unpaid portion)",
                                    status='pending',
                                    applied_date=timezone.now(),
                                    is_half_day=False,
                                    half_day_period=None,
                                    is_unpaid=True
                                )
                                unpaid_optional_leave.save()
                                created_leaves.append(unpaid_optional_leave)
                                
                                messages.warning(
                                    request,
                                    f'⚠️ Partial optional leave balance available! '
                                    f'Application split into: {optional_paid_days} days PAID + {optional_unpaid_days} days UNPAID. '
                                    f'Salary deduction will apply for {optional_unpaid_days} days.'
                                )
                                print(f"DEBUG: ⚠️ Partial optional balance. Split into {optional_paid_days} paid + {optional_unpaid_days} unpaid.")
                                
                            else:
                                messages.error(request, 'Unpaid leave type not configured. Please contact HR.')
                                return redirect('apply_leave')
                        else:
                            # No available balance - fully unpaid
                            optional_paid_days = Decimal('0.00')
                            optional_unpaid_days = optional_days_for_leave_type
                            is_optional_partial_unpaid = True
                    else:
                        # No balance exists - fully unpaid
                        optional_paid_days = Decimal('0.00')
                        optional_unpaid_days = optional_days_for_leave_type
                        is_optional_partial_unpaid = True
                    
                    # If we haven't created leaves yet (fully paid or fully unpaid)
                    if not created_leaves:
                        # Handle fully unpaid optional leave
                        if is_optional_partial_unpaid and optional_unpaid_days > 0:
                            unpaid_leave_type = LeaveType.objects.filter(
                                is_active=True,
                                name__icontains='unpaid'
                            ).first()
                            
                            if unpaid_leave_type:
                                optional_final_leave_type = unpaid_leave_type
                                
                                messages.warning(
                                    request,
                                    f'⚠️ No Optional Leave balance available. '
                                    f'Application will be submitted as UNPAID LEAVE. '
                                    f'Salary will be deducted for {optional_unpaid_days} days.'
                                )
                                print(f"DEBUG: ❌ No optional balance. Fully UNPAID optional leave.")
                            else:
                                messages.error(request, 'Unpaid leave type not configured. Please contact HR.')
                                return redirect('apply_leave')
                        
                        # Create optional leave application
                        optional_leave = Leave(
                            employee=employee,
                            leave_type=optional_final_leave_type,
                            colour=getattr(optional_final_leave_type, 'colour', '#28a745'),
                            start_date=start_date_obj,
                            end_date=end_date_obj,
                            days_requested=optional_days_for_leave_type,
                            reason=f"{reason}",
                            status='pending',
                            applied_date=timezone.now(),
                            is_half_day=False,
                            half_day_period=None,
                            is_unpaid=is_optional_partial_unpaid
                        )
                        optional_leave.save()
                        created_leaves.append(optional_leave)
                    
                    messages.success(
                        request,
                        f'✅ Optional Leave application submitted for {optional_days_for_leave_type} days!'
                    )
                else:
                    # ============================================
                    # PARTIAL PAID/UNPAID LOGIC FOR NON-OPTIONAL LEAVES
                    # ============================================
                    # Check balance for non-optional leave types
                    balance = LeaveBalance.objects.filter(
                        employee=employee,
                        leave_type=requested_leave_type,
                        year=date.today().year
                    )
                    
                    is_partial_unpaid = False
                    paid_days = Decimal('0.00')
                    unpaid_days = Decimal('0.00')
                    final_leave_type = requested_leave_type
                    leave_colour = getattr(requested_leave_type, 'colour', '#667eea')
                    
                    if balance.exists():
                        total_available_balance = sum(
                            Decimal(str(b.leaves_remaining)) for b in balance
                        )
                        
                        print(f"DEBUG: Checking balance for {requested_leave_type.name}")
                        print(f"DEBUG: Total available balance: {total_available_balance}")
                        print(f"DEBUG: Main leave days requested: {main_leave_days}")
                        
                        if total_available_balance >= main_leave_days:
                            # Sufficient balance - fully paid leave
                            paid_days = main_leave_days
                            unpaid_days = Decimal('0.00')
                            is_partial_unpaid = False
                            print(f"DEBUG: ✅ Sufficient balance. Fully PAID leave.")
                            
                        elif total_available_balance > 0:
                            # Partial balance - part paid, part unpaid
                            paid_days = total_available_balance
                            unpaid_days = main_leave_days - total_available_balance
                            is_partial_unpaid = True
                            
                            # Get unpaid leave type
                            unpaid_leave_type = LeaveType.objects.filter(
                                is_active=True,
                                name__icontains='unpaid'
                            ).first()
                            
                            if unpaid_leave_type:
                                # Create paid leave record
                                paid_leave = Leave(
                                    employee=employee,
                                    leave_type=requested_leave_type,
                                    colour=getattr(requested_leave_type, 'colour', '#667eea'),
                                    start_date=start_date_obj,
                                    end_date=end_date_obj,
                                    days_requested=paid_days,
                                    reason=f"{reason} (Paid portion)",
                                    status='pending',
                                    applied_date=timezone.now(),
                                    is_half_day=is_half_day,
                                    half_day_period=half_day_period if is_half_day else None,
                                    is_unpaid=False
                                )
                                paid_leave.save()
                                created_leaves.append(paid_leave)
                                
                                # Create unpaid leave record
                                unpaid_leave = Leave(
                                    employee=employee,
                                    leave_type=unpaid_leave_type,
                                    colour=getattr(unpaid_leave_type, 'colour', '#dc3545'),
                                    start_date=start_date_obj,
                                    end_date=end_date_obj,
                                    days_requested=unpaid_days,
                                    reason=f"{reason} (Unpaid portion)",
                                    status='pending',
                                    applied_date=timezone.now(),
                                    is_half_day=False,  # Unpaid can't be half-day
                                    half_day_period=None,
                                    is_unpaid=True
                                )
                                unpaid_leave.save()
                                created_leaves.append(unpaid_leave)
                                
                                messages.warning(
                                    request,
                                    f'⚠️ Partial balance available! '
                                    f'Application split into: {paid_days} days PAID + {unpaid_days} days UNPAID. '
                                    f'Salary deduction will apply for {unpaid_days} days.'
                                )
                                print(f"DEBUG: ⚠️ Partial balance. Split into {paid_days} paid + {unpaid_days} unpaid.")
                                
                                # Skip to final success message
                                if not is_half_day and optional_days_count > 0:
                                    messages.info(
                                        request,
                                        f'📝 Total application: {total_working_days} days '
                                        f'({optional_days_count} optional + {main_leave_days} {requested_leave_type.name})'
                                    )
                                return redirect('employee_leave_details')
                            else:
                                messages.error(request, 'Unpaid leave type not configured. Please contact HR.')
                                return redirect('apply_leave')
                        else:
                            # No available balance - fully unpaid
                            paid_days = Decimal('0.00')
                            unpaid_days = main_leave_days
                            is_partial_unpaid = True
                    else:
                        # No balance exists - fully unpaid
                        paid_days = Decimal('0.00')
                        unpaid_days = main_leave_days
                        is_partial_unpaid = True
                    
                    # If we reach here, it's either fully paid or fully unpaid (not partial)
                    if is_partial_unpaid and unpaid_days > 0:
                        # Fully unpaid leave
                        unpaid_leave_type = LeaveType.objects.filter(
                            is_active=True,
                            name__icontains='unpaid'
                        ).first()
                        
                        if unpaid_leave_type:
                            final_leave_type = unpaid_leave_type
                            leave_colour = getattr(unpaid_leave_type, 'colour', '#dc3545')
                            
                            # Ensure unpaid leave balance exists
                            unpaid_balance = AutoLeaveBalanceService.ensure_unpaid_leave_balance(employee)
                            
                            messages.warning(
                                request,
                                f'⚠️ No {requested_leave_type.name} balance available. '
                                f'Application will be submitted as UNPAID LEAVE. Salary will be deducted for {unpaid_days} days.'
                            )
                            print(f"DEBUG: ❌ No balance. Fully UNPAID leave.")
                        else:
                            messages.error(request, 'Unpaid leave type not configured. Please contact HR.')
                            return redirect('apply_leave')
                    
                    # Create the main leave application
                    main_leave = Leave(
                        employee=employee,
                        leave_type=final_leave_type,
                        colour=leave_colour,
                        start_date=start_date_obj,
                        end_date=end_date_obj,
                        days_requested=main_leave_days,
                        reason=reason,
                        status='pending',
                        applied_date=timezone.now(),
                        is_half_day=is_half_day,
                        half_day_period=half_day_period if is_half_day else None,
                        is_unpaid=is_partial_unpaid
                    )
                    main_leave.save()
                    created_leaves.append(main_leave)
                    
                    # Success message
                    if is_partial_unpaid:
                        messages.success(
                            request,
                            f'✅ Leave application submitted as UNPAID LEAVE! '
                            f'Salary deduction will apply for {main_leave_days} days. Waiting for approval.'
                        )
                    elif is_half_day:
                        period_display = "First Half" if half_day_period == "first_half" else "Second Half"
                        messages.success(
                            request,
                            f'✅ Half-day leave ({period_display}) submitted successfully!'
                        )
                    else:
                        messages.success(
                            request,
                            f'✅ Leave application for {main_leave_days} days submitted successfully!'
                        )
                    
                    # If optional leaves were also created
                    if not is_half_day and optional_days_count > 0:
                        messages.info(
                            request,
                            f'📝 Total application: {total_working_days} days '
                            f'({optional_days_count} optional + {main_leave_days} {final_leave_type.name})'
                        )
            
            return redirect('employee_leave_details')
            
        except Exception as e:
            messages.error(request, f'Error applying for leave: {str(e)}')
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Leave application error for {user_email}: {str(e)}", exc_info=True)
            return redirect('employee_leave_details')
    
    # GET request - show form (same as before)
    leave_types = LeaveType.objects.filter(is_active=True)
    
    # Get leave balances for current year
    leave_balances = LeaveBalance.objects.filter(
        employee=employee, 
        year=date.today().year
    ).select_related('leave_type')
    
    # Check probation status
    is_on_probation = ProbationService.is_on_probation(employee)
    probation_message = None
    if is_on_probation:
        probation_message = "⚠️ You are currently on probation. You have no earned leave balance. Any leave taken will be unpaid."
    
    # Get mandatory holidays for JavaScript calculation
    national_holidays = Holiday.objects.filter(
        Q(holiday_type__iexact='National Holiday'),
        date__year=date.today().year,
        is_optional=False
    ).values_list('date', flat=True)
    
    state_holidays = []
    if employee.location:
        matching_region = Location.objects.filter(name__iexact=employee.location).first()
        if matching_region:
            state_holidays = Holiday.objects.filter(
                region=matching_region,
                holiday_type__iexact='State Holiday',
                date__year=date.today().year,
                is_optional=False
            ).values_list('date', flat=True)
    
    all_mandatory_holidays = set(national_holidays) | set(state_holidays)
    holiday_dates_json = [f'"{holiday.isoformat()}"' for holiday in all_mandatory_holidays]
    
    context = {
        'leave_types': leave_types,
        'leave_balances': leave_balances,
        'today_date': date.today(),
        'min_date': date.today().strftime('%Y-%m-%d'),
        'user_name': request.session.get('user_name'),
        'user_role': user_role,
        'is_on_probation': is_on_probation,
        'probation_message': probation_message,
        'holiday_dates': f'[{",".join(holiday_dates_json)}]',
        'employee': employee,
    }
    return render(request, 'leave/apply_leave.html', context)


def get_existing_leaves(request):
    user_email = request.session.get('user_email')
    
    try:
        employee = Employee.objects.get(email=user_email)
        
        # Get existing pending and approved leaves
        existing_leaves = Leave.objects.filter(
            employee=employee,
            status__in=['pending', 'approved']
        ).select_related('leave_type').values(
            'id',
            'start_date',
            'end_date',
            'leave_type__name',
            'status',
            'is_half_day',
            'half_day_period'
        )
        
        leaves_list = list(existing_leaves)
        
        # Format dates as ISO strings (YYYY-MM-DD)
        for leave in leaves_list:
            leave['leave_type_name'] = leave['leave_type__name']
            del leave['leave_type__name']
            
            # Convert date objects to ISO format strings
            leave['start_date'] = leave['start_date'].isoformat() if leave['start_date'] else None
            leave['end_date'] = leave['end_date'].isoformat() if leave['end_date'] else None
            
            # Debug log
            print(f"Existing leave: {leave['leave_type_name']} from {leave['start_date']} to {leave['end_date']} (status: {leave['status']})")
        
        return JsonResponse({
            'success': True,
            'leaves': leaves_list
        })
        
    except Employee.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Employee not found'
        })
    except Exception as e:
        print(f"Error in get_existing_leaves: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
        
def get_optional_holidays_api(request):
    """API endpoint to get optional holidays for a date range"""
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    user_email = request.session.get('user_email')
    
    try:
        employee = Employee.objects.get(email=user_email)
        
        start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        result = calculate_working_days_with_optional(
            start_date=start_date_obj,
            end_date=end_date_obj,
            location=employee.location
        )
        
        return JsonResponse({
            'success': True,
            'working_days': result['working_days'],
            'optional_holidays': result['optional_holidays'],
            'mandatory_holidays_count': len(result['mandatory_holidays']),
            'total_calendar_days': result['total_calendar_days']
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


def approve_leave(request, leave_id):
    """Approve or reject a leave application with balance management"""
    # Check authentication
    if not request.session.get('user_authenticated'):
        return redirect('login')
    try:
        updated_by = Employee.objects.get(email=request.session.get('user_email'))
    except Employee.DoesNotExist:
        messages.error(request, 'Employee profile not found.')
        return redirect('leave_dashboard')
    
    now = timezone.now()
    
    if request.method == 'POST':
        leave = get_object_or_404(Leave, id=leave_id)
        action = request.POST.get('action')
        rejection_reason = request.POST.get('rejection_reason', '')
        
        # Store previous status for balance restoration
        previous_status = leave.status
        
        if action == 'approve':
            # Check if this is unpaid leave TYPE (not just the flag)
            is_unpaid_leave = 'unpaid' in leave.leave_type.name.lower()
            
            if is_unpaid_leave:
                # UNPAID LEAVE - No balance check needed, just record it
                AutoLeaveBalanceService.record_unpaid_leave(
                    leave.employee,
                    leave.days_requested
                )
                
                leave.status = 'approved'
                leave.approved_date = now
                leave.is_unpaid = True  # Ensure flag is set
                leave.approved_by = updated_by
                leave.save()
                
                messages.success(
                    request, 
                    f'✅ Unpaid leave approved for {leave.employee.first_name} {leave.employee.last_name}. '
                    f'Salary deduction will apply for {leave.days_requested} days.'
                )
                
            else:
                # PAID LEAVE - Validate and check balance
                is_valid, errors, warnings = LeaveValidationService.validate_leave_application(
                    leave.employee, 
                    leave.leave_type, 
                    leave.start_date, 
                    leave.end_date, 
                    leave.days_requested
                )
                
                if not is_valid:
                    for error in errors:
                        messages.error(request, f"Cannot approve leave: {error}")
                    return redirect(request.META.get('HTTP_REFERER', 'leave_dashboard'))
                
                # Only deduct balance if previously not approved
                if previous_status != 'approved':
                    success = LeaveValidationService.deduct_leave_balance(
                        leave.employee,
                        leave.leave_type,
                        leave.days_requested,
                        leave.start_date.year
                    )
                    
                    if not success:
                        messages.error(
                            request, 
                            'Error deducting leave balance. Please check available balance.'
                        )
                        return redirect(request.META.get('HTTP_REFERER', 'leave_dashboard'))
                
                leave.status = 'approved'
                leave.approved_date = now
                leave.approved_by = updated_by
                leave.save()
                
                messages.success(
                    request, 
                    f'✅ Leave approved for {leave.employee.first_name} {leave.employee.last_name}'
                )
            
        elif action == 'reject':
            # If previously approved, restore the leave balance
            if previous_status == 'approved' and not leave.is_unpaid:
                success = LeaveValidationService.restore_leave_balance(
                    leave.employee,
                    leave.leave_type,
                    leave.days_requested,
                    leave.start_date.year
                )
                
                if success:
                    messages.info(request, f'Leave balance restored for {leave.days_requested} days.')
                else:
                    messages.warning(
                        request, 
                        'Leave rejected but there was an issue restoring the balance. Please check manually.'
                    )
            
            leave.status = 'rejected'
            leave.approved_date = now
            leave.approved_by = updated_by
            leave.rejection_reason = rejection_reason
            leave.save()
            
            messages.success(
                request, 
                f'Leave rejected for {leave.employee.first_name} {leave.employee.last_name}.'
            )
        
    return redirect(request.META.get('HTTP_REFERER', 'leave_dashboard'))

def update_leave_status(request, leave_id):
    """Handle leave status changes from edit page with balance management"""
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    leave = get_object_or_404(Leave, id=leave_id)
    try:
        updated_by = Employee.objects.get(email=request.session.get('user_email'))
    except Employee.DoesNotExist:
        messages.error(request, 'Employee profile not found.')
        return redirect('leave_dashboard')
    now = timezone.now()
    
    if request.method == 'POST':
        new_status = request.POST.get('status')
        rejection_reason = request.POST.get('admin_remarks', '').strip()
        
        # Store previous status for balance management
        previous_status = leave.status
        print(f"DEBUG update_leave_status: Leave ID: {leave_id}")
        print(f"DEBUG update_leave_status: Previous Status: {previous_status}")
        print(f"DEBUG update_leave_status: New Status: {new_status}")
        print(f"DEBUG update_leave_status: Is Unpaid: {leave.is_unpaid}")
        
        if new_status in ['approved', 'rejected', 'pending', 'new']:
            # Handle balance changes based on status transition
            if previous_status == 'approved' and new_status in ['rejected', 'pending', 'new']:
                # Moving from approved to other status - restore balance
        
                print(f"DEBUG: Restoring balance for leave ID {leave.id}")
                success = LeaveValidationService.restore_leave_balance(
                    leave.employee,
                    leave.leave_type,
                    leave.days_requested,
                    leave.start_date.year
                )
                    
                if success:
                    messages.info(request, f'Leave balance restored for {leave.days_requested} days.')
                    print(f"DEBUG: Balance restored successfully")
                else:
                    messages.warning(request, 'Leave status changed but there was an issue restoring the balance.')
                    print(f"DEBUG: Balance restoration failed")
            
            elif new_status == 'approved' and previous_status in ['rejected', 'pending', 'new']:
                # Moving to approved from other status - deduct balance
                
                is_valid, errors, warnings = LeaveValidationService.validate_leave_application(
                    leave.employee, 
                    leave.leave_type, 
                    leave.start_date, 
                    leave.end_date, 
                    leave.days_requested
                )
                    
                if is_valid:
                    success = LeaveValidationService.deduct_leave_balance(
                        leave.employee,
                        leave.leave_type,
                        leave.days_requested,
                        leave.start_date.year
                    )
                        
                    if success:
                        messages.info(request, f'Leave balance deducted for {leave.days_requested} days.')
                    else:
                        messages.error(request, 'Error deducting leave balance. Status not changed.')
                        return redirect('edit_leave_details', leave_id=leave_id)
                else:
                    for error in errors:
                        messages.error(request, f"Cannot approve leave: {error}")
                    return redirect('edit_leave_details', leave_id=leave_id)
            
            # Update leave record
            leave.status = new_status
            leave.rejection_reason = rejection_reason
            leave.approved_by = updated_by
            leave.approved_date = now
            
            if new_status == 'approved':
                leave.approved_date = timezone.now()
            elif new_status in ['rejected', 'pending', 'new']:
                leave.approved_date = timezone.now()
            
            leave.save()
            
            messages.success(request, f'Leave status updated to {new_status}.')
            return redirect('view_leave_detail', leave_id=leave.id)
        else:
            messages.error(request, 'Invalid status selected.')
    
    return redirect('edit_leave_details', leave_id=leave_id)


def withdraw_leave(request, leave_id):
    """Allow employees to withdraw their own leave applications"""
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    try:
        # Get current employee
        user_email = request.session.get('user_email')
        current_employee = Employee.objects.get(email=user_email)
        
        # Get the leave application
        leave = Leave.objects.get(id=leave_id)
        
        # Check if the leave belongs to the current user using ID comparison
        if leave.employee.id != current_employee.id:
            messages.error(request, 'You can only withdraw your own leave applications.')
            return redirect('employee_leave_details')
        
        # Check if leave can be withdrawn (only pending/new leaves)
        if leave.status not in ['pending', 'new','approved']:
            messages.error(request, 'You can only withdraw pending or new leave applications.')
            return redirect('employee_leave_details')
        
        # Store previous status for balance restoration
        previous_status = leave.status
        
        # If it was approved, restore the balance
        if previous_status == 'approved':
            success = LeaveValidationService.restore_leave_balance(
                leave.employee,
                leave.leave_type,
                leave.days_requested,
                leave.start_date.year
            )
            
            if success:
                messages.info(request, f'Leave balance restored for {leave.days_requested} days.')
        
        # Update leave status to withdrawn
        leave.status = 'withdrawn'
        leave.rejection_reason = "Leave withdrawn by employee"
        leave.save()
        
        messages.success(request, 'Leave application withdrawn successfully.')
        
    except (Leave.DoesNotExist, Employee.DoesNotExist):
        messages.error(request, 'Leave application or employee profile not found.')
    except Exception as e:
        messages.error(request, f'Error withdrawing leave: {str(e)}')
    
    return redirect('employee_leave_details')

# def leave_detail(request, leave_id):
#     """View details of a specific leave"""
#     # Check authentication
#     if not request.session.get('user_authenticated'):
#         return redirect('login')
    
#     leave = get_object_or_404(
#         Leave.objects.select_related(
#             'employee',
#             'leave_type',
#             'approved_by'
#         ),
#         id=leave_id
#     )
    
#     # Get regional holidays during leave period
#     holidays = []
#     if leave.employee.location:
#         region = Region.objects.filter(name__iexact=leave.employee.location).first()
#         if region:
#             holidays = Holiday.objects.filter(
#                 region=region,
#                 date__gte=leave.start_date,
#                 date__lte=leave.end_date
#             )
    
#     context = {
#         'leave': leave,
#         'holidays': holidays,
#         'working_days': leave.get_working_days(),
#     }
    
#     return render(request, 'leave/leave_detail.html', context)

def manage_regions(request):
    """Manage regions and holidays"""
    # Check authentication
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'add_region':
            name = request.POST.get('name')
            code = request.POST.get('code')
            description = request.POST.get('description', '')
            
            try:
                Location.objects.create(
                    name=name,
                    code=code.upper(),
                    description=description
                )
                messages.success(request, f'Region {name} added successfully!')
            except Exception as e:
                messages.error(request, f'Error adding region: {str(e)}')
        
        elif action == 'add_holiday':
            region_id = request.POST.get('region')
            name = request.POST.get('holiday_name')
            date = datetime.strptime(request.POST.get('holiday_date'), '%Y-%m-%d').date()
            description = request.POST.get('holiday_description', '')
            is_optional = request.POST.get('is_optional') == 'on'
            
            try:
                region = Location.objects.get(id=region_id)
                Holiday.objects.create(
                    region=region,
                    name=name,
                    date=date,
                    description=description,
                    is_optional=is_optional
                )
                messages.success(request, f'Holiday {name} added for {region.name}!')
            except Exception as e:
                messages.error(request, f'Error adding holiday: {str(e)}')
        
        return redirect('manage_regions')
    
    regions = Location.objects.prefetch_related('holidays').all()
    today = timezone.now().date()
    
    context = {
        'regions': regions,
        'current_year': today.year,
    }
    
    return render(request, 'leave/manage_regions.html', context)

def get_leave_stats_api(request):
    """API endpoint for dashboard statistics"""
    today = timezone.now().date()
    total_employees = Employee.objects.count()
    
    stats = {
        'total_employees': total_employees,
        'on_leave_today': Leave.objects.filter(
            start_date__lte=today,
            end_date__gte=today,
            status='approved'
        ).count(),
        'pending_applications': Leave.objects.filter(
            status='pending'
        ).count(),
        'approved_this_month': Leave.objects.filter(
            status='approved',
            approved_date__month=today.month,
            approved_date__year=today.year
        ).count(),
    }
    
    return JsonResponse(stats)

def leave_view(request):
    """Simple leave view - redirects to dashboard"""
    return redirect('leave_dashboard')

def calendar_events(request):
    """Return holidays and approved leaves as JSON for FullCalendar"""
    events = []

    # 1. Holidays
    holidays = Holiday.objects.all()
    for h in holidays:
        events.append({
            "title": f"Holiday: {h.name}",
            "start": h.date.strftime("%Y-%m-%d"),
            "allDay": True,
            "color": "#f87171",
        })

    # 2. Approved Leaves
    leaves = Leave.objects.filter(status="approved")
    for l in leaves:
        events.append({
            "title": f"Leave: {l.employee.first_name} {l.employee.last_name}",
            "start": l.start_date.strftime("%Y-%m-%d"),
            "end": (l.end_date + timedelta(days=1)).strftime("%Y-%m-%d"),
            "allDay": True,
            "color": "#60a5fa",
        })

    return JsonResponse(events, safe=False)
def get_region_holidays_api(request, region_id):
    """API to fetch holidays for a specific region"""
    holidays = Holiday.objects.filter(
        region_id=region_id,
        date__year=timezone.now().year
    ).values('id', 'name', 'date', 'is_optional')
    
    return JsonResponse(list(holidays), safe=False)


def add_holiday(request):
    """Add a new holiday via modal form"""
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    if request.method == 'POST':
        try:
            region_id = request.POST.get('region')
            name = request.POST.get('holiday_name')
            holiday_type = request.POST.get('holiday_type')
            date_str = request.POST.get('holiday_date')
            description = request.POST.get('holiday_description', '')
            is_optional = request.POST.get('is_optional') == 'on'
            
            # Validate required fields
            if not region_id or not name or not date_str:
                messages.error(request, 'Please fill in all required fields.')
                return redirect('leave_dashboard')
            
            # Parse date
            try:
                date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                messages.error(request, 'Invalid date format.')
                return redirect('leave_dashboard')
            
            # Check if date is not in the past
            if date < timezone.now().date():
                messages.error(request, 'Cannot add holidays for past dates.')
                return redirect('leave_dashboard')
            
            # Get region
            region = Location.objects.get(id=region_id, is_active=True)
            
            # Check for duplicate holiday
            existing = Holiday.objects.filter(
                region=region,
                name=name,
                date=date
            ).exists()
            
            if existing:
                messages.warning(request, f'Holiday "{name}" already exists for {region.name} on {date}.')
                return redirect('leave_dashboard')
            
            # Create holiday
            Holiday.objects.create(
                region=region,
                name=name,
                holiday_type =holiday_type,
                date=date,
                description=description,
                is_optional=is_optional
            )
            
            messages.success(request, f'Holiday "{name}" added successfully for {region.name}!')
            
        except Location.DoesNotExist:
            messages.error(request, 'Selected region not found.')
        except Exception as e:
            messages.error(request, f'Error adding holiday: {str(e)}')
    
    return redirect('leave_dashboard')

def add_custom_event(request):
    """Add custom event (like company meeting) via modal"""
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    if request.method == 'POST':
        try:
            event_type = request.POST.get('event_type')
            title = request.POST.get('event_title')
            start_date_str = request.POST.get('start_date')
            end_date_str = request.POST.get('end_date')
            description = request.POST.get('event_description', '')
            
            # Validate required fields
            if not event_type or not title or not start_date_str:
                messages.error(request, 'Please fill in all required fields.')
                return redirect('leave_dashboard')
            
            # Parse dates
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else start_date
            
            # Validate date range
            if end_date < start_date:
                messages.error(request, 'End date cannot be before start date.')
                return redirect('leave_dashboard')
            
            # Here you can save to a CustomEvent model or handle as needed
            # For now, we'll just show a success message
            messages.success(request, f'Event "{title}" added successfully!')
            
        except ValueError:
            messages.error(request, 'Invalid date format.')
        except Exception as e:
            messages.error(request, f'Error adding event: {str(e)}')
    
    return redirect('leave_dashboard')


def edit_holiday(request):
    if request.method == 'POST':
        try:
            # Check permission
            user_role = request.session.get('user_role', '')
            if user_role not in ['ADMIN', 'HR', 'SUPER ADMIN']:
                return JsonResponse({'error': 'Permission denied'}, status=403)
            
            holiday_id = request.POST.get('holiday_id')
            holiday = get_object_or_404(Holiday, id=holiday_id)
            
            # Update holiday fields
            holiday.name = request.POST.get('holiday_name')
            holiday.holiday_type = request.POST.get('holiday_type')
            holiday.date = request.POST.get('holiday_date')
            holiday.description = request.POST.get('holiday_description', '')
            holiday.is_optional = request.POST.get('is_optional') == 'on'
            
            # Check if region changed
            region_id = request.POST.get('region')
            if region_id and str(holiday.region.id) != region_id:
                from .models import Region  # Import here to avoid circular import
                region = get_object_or_404(Region, id=region_id)
                holiday.region = region
            
            holiday.save()
            
            return JsonResponse({
                'success': True,
                'message': 'Holiday updated successfully'
            })
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

def delete_holiday(request):
    if request.method == 'POST':
        try:
            # Check permission
            user_role = request.session.get('user_role', '')
            if user_role not in ['ADMIN', 'HR', 'SUPER ADMIN']:
                return JsonResponse({'error': 'Permission denied'}, status=403)
            
            holiday_id = request.POST.get('holiday_id')
            holiday = get_object_or_404(Holiday, id=holiday_id)
            holiday_name = holiday.name
            holiday.delete()
            
            return JsonResponse({
                'success': True,
                'message': f'Holiday "{holiday_name}" deleted successfully'
            })
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

def employee_leave_details(request):
    """Employee-specific leave details page with strict rules information"""
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    # Get employee email from session
    user_email = request.session.get('user_email')
    if not user_email:
        messages.error(request, 'Session expired. Please log in again.')
        return redirect('login')

    try:
        employee = Employee.objects.get(email=user_email)
        current_employee_id = employee.id
    except Employee.DoesNotExist:
        messages.error(request, 'Employee profile not found.')
        return redirect('leave_dashboard')
    
    # Current date and month calculations
    today = timezone.now().date()
    current_year = today.year
    current_month = today.month
    
    # NEW: Get probation status
    is_on_probation = ProbationService.is_on_probation(employee)
    probation_end_date = employee.probation_end_date
    
    # Get all leave balances with detailed information
    leave_balances = LeaveBalance.objects.filter(
        employee=employee,
        year=current_year
    ).select_related('leave_type')
    
    # FIX: Get carry forward from annual leave only (not sum of all types)
    annual_balance = leave_balances.filter(leave_type__name__icontains='Annual').first()
    carry_forward = annual_balance.carry_forward if annual_balance else Decimal('0.00')
    
    # Calculate statistics for each leave type
    leave_stats = {}
    comp_off_expiration_info = None
    comp_off_valid_until = None
    
    for balance in leave_balances:
        # Check if this is comp off
        is_comp_off = any(keyword in balance.leave_type.name.lower() 
                         for keyword in ['comp off', 'compensatory', 'compoff', 'comp-off'])
        
        if is_comp_off:
            # Get expiration info from the balance itself
            days_remaining = balance.days_remaining if hasattr(balance, 'days_remaining') else 0
            is_expired = balance.is_expired if hasattr(balance, 'is_expired') else False
            
            # Calculate days remaining if we have valid_until
            if hasattr(balance, 'valid_until') and balance.valid_until:
                days_remaining = (balance.valid_until - today).days
                is_expired = balance.is_expired or (balance.valid_until < today)
                comp_off_valid_until = balance.valid_until  # STORE THIS
            
            leave_stats[balance.leave_type.name] = {
                'total': balance.total_leaves,
                'taken': balance.leaves_taken,
                'remaining': balance.leaves_remaining,
                'carry_forward': balance.carry_forward,
                'max_carry_forward': balance.leave_type.max_carry_forward,
                'is_optional': balance.leave_type.is_optional,
                'is_comp_off': True,
                'days_remaining': days_remaining,
                'expiring_soon': 0 < days_remaining <= 7,
                'valid_until': balance.valid_until if hasattr(balance,'valid_until') else None,
                'is_expired': is_expired,
                'earned_date': balance.earned_date if hasattr(balance,'earned_date') else None
            }
            # Store comp off info for the template
            comp_off_expiration_info = {
                'balance': balance.leaves_remaining,
                'total': balance.total_leaves,
                'days_remaining': days_remaining,
                'expiring_soon': 0 < days_remaining <= 7,
                'valid_until': balance.valid_until if hasattr(balance, 'valid_until') else None,
                'is_expired': is_expired,
                'earned_date': balance.earned_date if hasattr(balance, 'earned_date') else None
            }
        else:
            leave_stats[balance.leave_type.name] = {
                'total': balance.total_leaves,
                'taken': balance.leaves_taken,
                'remaining': balance.leaves_remaining,
                'carry_forward': balance.carry_forward,
                'is_comp_off': False
            }
    
    # Optional leave specific rules
    optional_leave_info = None
    if 'Optional' in leave_stats:
        optional_info = leave_stats['Optional']
        optional_leave_info = {
            'annual_allocation': 4,
            'max_usable': 2,
            'used': optional_info['taken'],
            'remaining_usable': max(0, 2 - optional_info['taken']),
            'will_lose': optional_info['remaining'] - max(0, 2 - optional_info['taken'])
        }
    
    # Earned leave accrual information - USE THE CORRECT CARRY FORWARD
    annual_leave_info = None
    if 'Earned' in leave_stats:
        annual_info = leave_stats['Earned']
        annual_leave_info = {
            'monthly_accrual': 1.5,
            'max_carry_forward': 12,
            'current_carry_forward': carry_forward,  # Use the corrected carry forward
        }
    
    # Pending leaves
    pending_leaves = Leave.objects.filter(
        employee=employee,
        status__in=['pending', 'new']
    ).count()
    
    # Get leave history
    leave_history = Leave.objects.filter(
        employee=employee
    ).select_related('leave_type').order_by('-applied_date')
    
    context = {
        'employee': employee,
        'current_employee_id': current_employee_id,
        'is_on_probation': is_on_probation,
        'probation_end_date': probation_end_date,
        'leave_stats': leave_stats,
        'optional_leave_info': optional_leave_info,
        'annual_leave_info': annual_leave_info,
        'pending_leaves': pending_leaves,
        'leave_history': leave_history,
        'current_year': current_year,
        'today_date': today,
        'user_email': user_email,
        'can_withdraw': True,  # Since this is employee's own page
        'comp_off_expiration_info': comp_off_expiration_info,
        'valid_until': comp_off_valid_until, 
    }
    
    return render(request, 'leave/emp_leave_details.html', context)

def view_leave_detail(request, leave_id):
    """Return JSON data for a specific leave (for modal display)"""
    leave = get_object_or_404(Leave, id=leave_id)

    context = {
        'leave': leave,
        'employee_name': f"{leave.employee.first_name} {leave.employee.last_name}",
        'department': leave.employee.department if hasattr(leave.employee, 'department') else None,
        'profile_image': leave.employee.profile_image.url if getattr(leave.employee, 'profile_image', None) else None,
    }

    return render(request, 'leave/view_leave_details.html',context)

def edit_leave_details(request, leave_id):
    """Admin can view and update leave status with proper balance management"""
    leave = get_object_or_404(Leave, id=leave_id)

    if request.method == 'POST':
        # Use the new function that handles balance management
        return update_leave_status(request, leave_id)

    context = {
        'leave': leave,
        'employee_name': f"{leave.employee.first_name} {leave.employee.last_name}",
        'department': getattr(leave.employee, 'department', None),
        'profile_image': leave.employee.profile_image.url if getattr(leave.employee, 'profile_image', None) else None,
    }
    return render(request, 'leave/edit_leave_details.html', context)


def leave_balance_summary(request):
    user_role = request.session.get('user_role')          
    user_department = request.session.get('user_department')
    user_email = request.session.get('user_email')
    
    # Get base queryset
    leave_balances = LeaveBalance.objects.select_related('employee', 'leave_type')
    
    # ✅ Role-based filtering for leave balances
    if user_role in ['ADMIN', 'HR', 'SUPER ADMIN']:
        leave_balances = leave_balances  # No additional filter for admin
    elif user_role == 'BRANCH MANAGER':
        try:
            current_branch_manager = Employee.objects.get(email=user_email)
            if current_branch_manager.location:
                leave_balances = leave_balances.filter(
                    employee__location__iexact=current_branch_manager.location
                )
            else:
                leave_balances = leave_balances.none()
        except Employee.DoesNotExist:
            leave_balances = leave_balances.none()
    elif user_role == 'MANAGER' and user_department:
        leave_balances = leave_balances.filter(employee__department=user_department)
    else:
        leave_balances = leave_balances.none()
    
    # Get all balances at once
    all_balances = list(leave_balances)
    
    # ✅ Role-based employee filtering
    if user_role in ['ADMIN', 'HR', 'SUPER ADMIN']:
        employees = Employee.objects.filter(status='active').order_by('first_name')
    elif user_role == 'BRANCH MANAGER':
        try:
            current_branch_manager = Employee.objects.get(email=user_email)
            if current_branch_manager.location:
                employees = Employee.objects.filter(
                    status='active',
                    location__iexact=current_branch_manager.location
                ).order_by('first_name')
            else:
                employees = Employee.objects.none()
        except Employee.DoesNotExist:
            employees = Employee.objects.none()
    elif user_role == 'MANAGER' and user_department:
        employees = Employee.objects.filter(department=user_department, status='active').order_by('first_name')
    else:
        employees = Employee.objects.none()
        
    # NEW: Get unpaid leave counts from Leave model
    unpaid_counts = {}
    for employee in employees:
        # Count unpaid leaves for this employee in current year
        unpaid_count = Leave.objects.filter(
            employee=employee,
            is_unpaid=True,
            status='approved',
            start_date__year=date.today().year
        ).aggregate(total_unpaid=Sum('days_requested'))['total_unpaid'] or Decimal('0.00')
        
        unpaid_counts[employee.id] = unpaid_count
    # NEW: Get paid leave counts (exclude unpaid leaves from taken count)
    paid_leave_counts = {}
    for employee in employees:
        # Count only paid leaves (non-unpaid) for this employee in current year
        paid_count = Leave.objects.filter(
            employee=employee,
            is_unpaid=False,  # Only paid leaves
            status='approved',
            start_date__year=date.today().year
        ).aggregate(total_paid=Sum('days_requested'))['total_paid'] or Decimal('0.00')
        
        paid_leave_counts[employee.id] = paid_count
    
    # Prepare balances list
    balances = []
    
    for employee in employees:
        # Initialize counters
        total_leaves = 0
        leaves_taken = 0
        carry_forward = 0
        optional_total = 0
        optional_taken = 0
        
        # Find balances for this employee
        for balance in all_balances:
            if balance.employee.id == employee.id:
                if 'optional' in balance.leave_type.name.lower():
                    # Optional leave
                    optional_total += balance.total_leaves or 0
                    optional_taken += balance.leaves_taken or 0
                else:
                    # Regular leave
                    total_leaves += balance.total_leaves or 0
                    leaves_taken += balance.leaves_taken or 0
                    carry_forward += balance.carry_forward or 0
        
        #This ensures we're only counting paid leaves in the "taken" column
        actual_paid_taken = paid_leave_counts.get(employee.id, Decimal('0.00'))
        
        # Calculate remaining leaves
        leaves_remaining = total_leaves - actual_paid_taken
        optional_remaining = optional_total - optional_taken
        
        # Get unpaid count for this employee
        unpaid_taken = unpaid_counts.get(employee.id, Decimal('0.00'))
        
        # Add to balances list
        balances.append({
            'employee__id': employee.id,
            'employee__first_name': employee.first_name,
            'employee__last_name': employee.last_name,
            'total_leaves': total_leaves,
            'leaves_taken': actual_paid_taken,
            'leaves_remaining': leaves_remaining,
            'carry_forward': carry_forward,
            'optional_total': optional_total,
            'optional_taken': optional_taken,
            'optional_remaining': optional_remaining,
            'unpaid_taken': unpaid_taken
        })
    
    # Get data for modal dropdowns
    leave_types = LeaveType.objects.filter(is_active=True)
    current_year = date.today().year
    years = range(current_year - 2, current_year + 3)

    context = {
        'balances': balances,
        'employees': employees,
        'leave_types': leave_types,
        'years': years,
        'current_year': current_year,
        'user_role': user_role,  # ✅ Pass user role to template
    }
    
    return render(request, 'leave/leave_balance_summary.html', context)

def add_leave_balance(request):
    """Handle adding new leave balance"""
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    if request.method == 'POST':
        try:
            employee_id = request.POST.get('employee')
            leave_type_id = request.POST.get('leave_type')
            total_leaves = int(request.POST.get('total_leaves', 0))
            carry_forward = int(request.POST.get('carry_forward', 0))
            year = int(request.POST.get('year'))
            
            # Validate required fields
            if not employee_id or not leave_type_id or not year:
                messages.error(request, 'Please fill in all required fields.')
                return redirect('leave_balance_list')
            
            # Get employee and leave type
            try:
                employee = Employee.objects.get(id=employee_id)
                leave_type = LeaveType.objects.get(id=leave_type_id)
            except (Employee.DoesNotExist, LeaveType.DoesNotExist):
                messages.error(request, 'Invalid employee or leave type selected.')
                return redirect('leave_balance_list')
            
            # Check if balance already exists
            # existing_balance = LeaveBalance.objects.filter(
            #     employee=employee,
            #     leave_type=leave_type,
            #     year=year
            # ).first()
            
            # if existing_balance:
            #     messages.warning(
            #         request, 
            #         f'Leave balance already exists for {employee.first_name} {employee.last_name} '
            #         f'- {leave_type.name} ({year}).'
            #     )
            #     return redirect('leave_balance_list')
            
             # Debug: Print leave type info
            print(f"DEBUG: Processing leave type: '{leave_type.name}' (ID: {leave_type.id})")
            
            # Check if this is Comp Off leave
            comp_off_keywords = ['comp off', 'compensatory', 'compoff', 'comp-off']
            leave_type_lower = leave_type.name.lower()
            is_comp_off = any(keyword in leave_type_lower for keyword in comp_off_keywords)
            
            print(f"DEBUG: Is Comp Off: {is_comp_off}")
            
            # For Comp Off: Update existing balance if exists, otherwise create new WITH EXPIRATION
            if is_comp_off:
                today = timezone.now().date()
                valid_until = today + timedelta(days=45)  # 45-day validity
                
                existing_balance = LeaveBalance.objects.filter(
                    employee=employee,
                    leave_type=leave_type,
                    year=year
                ).first()
                
                if existing_balance:
                    # Update existing Comp Off balance
                    existing_balance.total_leaves += total_leaves
                    existing_balance.leaves_remaining += total_leaves + carry_forward
                    existing_balance.carry_forward += carry_forward
                    
                    # Update expiration date (extend if not expired)
                    if not existing_balance.is_expired:
                        existing_balance.valid_until = valid_until
                        if not existing_balance.earned_date:
                            existing_balance.earned_date = today
                            
                    existing_balance.save()
                    
                    messages.success(
                        request, 
                        f'Comp Off balance updated for {employee.first_name} {employee.last_name} '
                        f'- Added {total_leaves} days to existing balance ({year})'
                    )
                else:
                    # Create new Comp Off balance
                    leaves_remaining = total_leaves + carry_forward
                    LeaveBalance.objects.create(
                        employee=employee,
                        leave_type=leave_type,
                        total_leaves=total_leaves,
                        leaves_taken=0,
                        leaves_remaining=leaves_remaining,
                        carry_forward=carry_forward,
                        year=year,
                        earned_date=today,
                        valid_until=valid_until,
                        is_expired=False
                    )
                    
                    messages.success(
                        request, 
                        f'Comp Off balance created for {employee.first_name} {employee.last_name} '
                        f'- {total_leaves} days ({year})'
                        f'Valid until {valid_until.strftime("%d-%m-%Y")}'
                    )
            
            else:
                # For non-Comp Off leaves: Check for duplicates
                existing_balance = LeaveBalance.objects.filter(
                    employee=employee,
                    leave_type=leave_type,
                    year=year
                ).first()
                
                if existing_balance:
                    messages.warning(
                        request, 
                        f'Leave balance already exists for {employee.first_name} {employee.last_name} '
                        f'- {leave_type.name} ({year}). Only Comp Off leave can be added multiple times.'
                    )
                    return redirect('leave_balance_list')
                
                # Calculate remaining leaves
                leaves_remaining = total_leaves + carry_forward
                
                # Create new leave balance
                LeaveBalance.objects.create(
                    employee=employee,
                    leave_type=leave_type,
                    total_leaves=total_leaves,
                    leaves_taken=0,
                    leaves_remaining=leaves_remaining,
                    carry_forward=carry_forward,
                    year=year
                )
                
                messages.success(
                    request, 
                    f'Leave balance added successfully for {employee.first_name} {employee.last_name} '
                    f'- {leave_type.name} ({year})'
                )
                
        except ValueError:
            messages.error(request, 'Invalid numeric values provided.')
        except Exception as e:
            messages.error(request, f'Error adding leave balance: {str(e)}')
    
    return redirect('leave_balance_list')
def edit_leave_balance(request):
    """Handle editing carry forward - add to total_leaves column"""
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    if request.method == 'POST':
        try:
            employee_id = request.POST.get('employee_id')
            carry_forward = request.POST.get('carry_forward', '0')
            year = int(request.POST.get('year'))
            
            # Validate required fields
            if not employee_id or not year:
                messages.error(request, 'Please fill in all required fields.')
                return redirect('leave_balance_list')
            
            # Convert to Decimal
            from decimal import Decimal
            carry_forward_decimal = Decimal(carry_forward)
            
            # Get employee
            try:
                employee = Employee.objects.get(id=employee_id)
            except Employee.DoesNotExist:
                messages.error(request, 'Invalid employee selected.')
                return redirect('leave_balance_list')
            
            # Get the primary leave balance (first one found)
            primary_leave_balance = LeaveBalance.objects.filter(
                employee=employee,
                year=year
            ).first()

            if primary_leave_balance:
                # ADD to total_leaves instead of carry_forward field
                # Convert 1.5 to Decimal before adding
                primary_leave_balance.total_leaves = carry_forward_decimal + Decimal('1.5')
               
                
                # Recalculate remaining leaves based on new total
                primary_leave_balance.leaves_remaining = (
                    primary_leave_balance.total_leaves - 
                    primary_leave_balance.leaves_taken
                )
                
                primary_leave_balance.carry_forward = carry_forward_decimal
                
                primary_leave_balance.save()
                
                # For other leave types, just reset their carry_forward to 0
                other_balances = LeaveBalance.objects.filter(
                    employee=employee,
                    year=year
                ).exclude(id=primary_leave_balance.id)
                
                for balance in other_balances:
                    balance.carry_forward = Decimal('0.00')
                    # Recalculate remaining for other leave types
                    balance.leaves_remaining = balance.total_leaves - balance.leaves_taken
                    balance.save()
                
                messages.success(
                    request, 
                    f'Carry forward {carry_forward} added to total leaves for {employee.first_name} {employee.last_name} ({year})'
                )
            else:
                messages.error(request, 'No leave balances found for this employee and year.')
            
        except ValueError as e:
            messages.error(request, f'Invalid numeric values provided: {str(e)}')
        except Exception as e:
            messages.error(request, f'Error updating carry forward: {str(e)}')
    
    return redirect('leave_balance_list')



def add_leave_type(request):
    if request.method == 'POST':
        form = LeaveTypeForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Leave type added successfully!")
            return redirect('add_leave_type')
    else:
        form = LeaveTypeForm()

    leave_types = LeaveType.objects.all()
    return render(request, 'leave/master_data/add_leave_type.html', {
        'form': form,
        'leave_types': leave_types
    })
    
    
def update_leave_type(request, pk):
    leave_type = get_object_or_404(LeaveType, pk=pk)
    if request.method == 'POST':
        form = LeaveTypeForm(request.POST, instance=leave_type)
        if form.is_valid():
            form.save()
            messages.success(request, "Leave type updated successfully!")
    return redirect('add_leave_type')


def delete_leave_type(request, pk):
    leave_type = get_object_or_404(LeaveType, pk=pk)
    leave_type.delete()
    messages.success(request, "Leave type deleted successfully!")
    return redirect('add_leave_type')