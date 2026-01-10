# views.py
import os
from hrms import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.db import models
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.db.models import Q
from datetime import date, timedelta, datetime
from django.utils import timezone
from .models import ExitInterview, NoDueCertificate, Resignation, ResignationChecklist, ResignationDocument
from hr.models import Employee
from django.template.loader import render_to_string
from xhtml2pdf import pisa
from fpdf import FPDF

import io
import html

# ----------------- Module-level configuration for PDF layout -----------------
PAGE_LEFT_MARGIN = 15
PAGE_RIGHT_MARGIN = 15
PAGE_TOP_MARGIN = 15
PAGE_BOTTOM_MARGIN = 18

# Exit Interview answer fixed-size box settings
WORDS_PER_ANSWER = 50         # fixed word limit for each text area
AVG_WORDS_PER_LINE = 8       # used to estimate lines from words
LINE_HEIGHT = 4.5              # mm per line (matches your earlier usage)
ANSWER_LINES = max(2, int((WORDS_PER_ANSWER / AVG_WORDS_PER_LINE) + 0.5))
ANSWER_BOX_HEIGHT = ANSWER_LINES * LINE_HEIGHT + 4  # adds tiny padding

SIG_IMG_WIDTH = 40
SIG_IMG_BOX_HEIGHT = 22
SIG_LABEL_GAP = 6
SIGNATURE_BLOCK_HEIGHT = SIG_IMG_BOX_HEIGHT + SIG_LABEL_GAP + 12

# Reserve this much vertical space for footer (must be >= the space used in footer())
# Your footer uses set_y(-22) and some extra content; 28 mm is a safe reserve.
FOOTER_RESERVED = 28
# ------------------------------------------------------------------------------

def check_resignation_access(request, resignation):
    """Check if user has access to view this resignation"""
    user_role = request.session.get('user_role')
    user_email = request.session.get('user_email')
    
    if user_role == 'EMPLOYEE' and resignation.employee.email != user_email:
        return False
    return True

def resignation_dashboard(request):
    """Comprehensive resignation dashboard with WOW features"""
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    user_role = request.session.get('user_role')
    user_email = request.session.get('user_email')
    
    # Statistics
    total_resignations = Resignation.objects.filter(status__in=['applied', 'accepted']).count()
    pending_resignations = Resignation.objects.filter(status='applied').count()
    active_notice = Resignation.objects.filter(status='accepted', exit_status='serving_notice').count()
    completed_this_month = Resignation.objects.filter(
        status='completed',
        created_at__month=date.today().month,
        created_at__year=date.today().year
    ).count()
    
    if user_role in ["MANAGER", "TL"]:
        try:
            current_user_emp = Employee.objects.get(email=user_email)
            print(f"Current user: {current_user_emp.first_name} {current_user_emp.last_name}")
            
            # Check how many team members report to this manager
            team_members = Employee.objects.filter(
                Q(reporting_manager_id=current_user_emp.id) |
                Q(reporting_manager__icontains=current_user_emp.first_name)
            )
            print(f"Team members count: {team_members.count()}")
            
            # CORRECTED: Use __in to filter by list of employee IDs
            recent_resignations = Resignation.objects.filter(
                employee_id__in=team_members.values_list('id', flat=True)
            ).exclude(employee=current_user_emp).select_related('employee').order_by('-created_at')[:10]
            
            print(f"Team resignations found: {recent_resignations.count()}")
            
        except Employee.DoesNotExist:
            print("Current user not found in Employee table")
            recent_resignations = Resignation.objects.none()
    else:
        # For non-manager roles, exclude current user's resignation
        try:
            current_user_emp = Employee.objects.get(email=user_email)
            recent_resignations = Resignation.objects.exclude(
                employee=current_user_emp
            ).select_related('employee').order_by('-created_at')[:10]
        except Employee.DoesNotExist:
            recent_resignations = Resignation.objects.select_related('employee').order_by('-created_at')[:10]
    
    # For employees, show only their resignation
    my_resignation = None
    if user_role != 'SUPER ADMIN':
        try:
            employee = Employee.objects.get(email=user_email)
            # my_resignation = Resignation.objects.filter(employee=employee).first()
            my_resignation = Resignation.objects.filter(employee=employee).order_by('-created_at')
        except Employee.DoesNotExist:
            pass
    
    context = {
        'total_resignations': total_resignations,
        'pending_resignations': pending_resignations,
        'active_notice': active_notice,
        'completed_this_month': completed_this_month,
        'recent_resignations': recent_resignations,
        'my_resignation': my_resignation,
        'user_role': user_role,
        'today_date': date.today(),
    }
    return render(request, 'resignation/dashboard.html', context)

def submit_resignation(request):
    """Employee submits resignation with automatic calculations"""
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    # Check if user already has an active resignation
    try:
        employee = Employee.objects.get(email=request.session.get('user_email'))
        
        # Check for existing resignations
        existing_resignations = Resignation.objects.filter(employee=employee)
        
        # Block if any active resignation exists (not withdrawn or completed)
        active_resignations = existing_resignations.exclude(
            status__in=['withdrawn', 'rejected', 'completed']
        )
        
        if active_resignations.exists():
            messages.error(request, 
                'You already have an active resignation request. '
                'Please wait for it to be processed or withdraw it first.'
            )
            return redirect('resignation:dashboard')
        
        # Optional: Limit resignation frequency (e.g., once per 30 days)
        recent_resignations = existing_resignations.filter(
            created_at__gte=timezone.now() - timedelta(days=0)
        )
        if recent_resignations.exists():
            messages.error(request,
                'You have submitted a resignation recently. '
                'Please wait 30 days before submitting another resignation request.'
            )
            return redirect('resignation:dashboard')
            
    except Employee.DoesNotExist:
        messages.error(request, 'Employee profile not found.')
        return redirect('resignation:dashboard')
    
    if request.method == 'POST':
        try:
            employee = Employee.objects.get(email=request.session.get('user_email'))
            resignation_date = request.POST.get('resignation_date')
            reason = html.escape(request.POST.get('reason', ''))
            
            # Convert date
            resignation_date_obj = datetime.strptime(resignation_date, '%Y-%m-%d').date()
            
            # Calculate last_working_date automatically (resignation_date + notice_period)
            employee_notice_period = getattr(employee, 'notice_period_days', 60)
            if employee_notice_period is None:
                employee_notice_period = 60
                
            last_working_date_obj = resignation_date_obj + timedelta(days=employee_notice_period)
            
            # Get reporting manager safely
            applied_to = None
            if hasattr(employee, 'reporting_manager_id') and employee.reporting_manager_id:
                try:
                    applied_to = Employee.objects.get(employee_id=employee.reporting_manager_id)
                except Employee.DoesNotExist:
                    pass
            
            # If no reporting manager found, try to get from reporting_manager field
            if not applied_to and hasattr(employee, 'reporting_manager') and employee.reporting_manager:
                try:
                    manager_name = employee.reporting_manager
                    if ' (' in manager_name:
                        manager_name = manager_name.split(' (')[0]
                    
                    name_parts = manager_name.split(' ')
                    if len(name_parts) >= 2:
                        applied_to = Employee.objects.filter(
                            first_name=name_parts[0],
                            last_name=name_parts[1],
                            status='active'
                        ).first()
                except:
                    pass
            
            # Final fallback - get any HR/Admin user
            if not applied_to:
                try:
                    applied_to = Employee.objects.filter(
                        role__in=['HR', 'ADMIN', 'SUPER ADMIN'],
                        status='active'
                    ).first()
                except:
                    applied_to = None
            
            resignation = Resignation(
                employee=employee,
                resignation_date=resignation_date_obj,
                last_working_date=last_working_date_obj,
                reason=reason,
                applied_to=applied_to,
                notice_period_days=employee_notice_period,
                actual_notice_days=employee_notice_period,
                notice_period_start=resignation_date_obj,
                notice_period_end=last_working_date_obj
            )
            resignation.save()
            
            # Auto-create comprehensive checklist
            create_resignation_checklist(resignation)
            
            messages.success(request, ' Resignation submitted successfully! HR will review your application.')
            return redirect('resignation:dashboard')
            
        except Exception as e:
            messages.error(request, f'Error submitting resignation: {str(e)}')
    
    # GET request - show form
    try:
        employee = Employee.objects.get(email=request.session.get('user_email'))
        employee_notice_period = getattr(employee, 'notice_period_days', 60)
        if employee_notice_period is None:
            employee_notice_period = 60
            
        min_date = (date.today()).strftime('%Y-%m-%d')
    except Employee.DoesNotExist:
        min_date = date.today().strftime('%Y-%m-%d')
        employee_notice_period = 60
    
    context = {
        'min_date': min_date,
        'notice_period': employee_notice_period,
        'user_name': request.session.get('user_name'),
        'user_role': request.session.get('user_role'),
        'today_date': date.today(),
    }
    return render(request, 'resignation/submit_resignation.html', context)

def create_resignation_checklist(resignation):
    """Auto-create comprehensive exit checklist"""
    checklist_items = [
        {'task': 'Exit Interview Scheduling', 'department': 'HR', 'days': 2},
        {'task': 'Knowledge Transfer Documentation', 'department': 'Department', 'days': 7},
        {'task': 'Project Handover', 'department': 'Department', 'days': 5},
        {'task': 'Laptop & Asset Return', 'department': 'IT', 'days': 1},
        {'task': 'ID Card Surrender', 'department': 'HR', 'days': 1},
        {'task': 'Email Account Deactivation', 'department': 'IT', 'days': 0},
        {'task': 'Access Card Deactivation', 'department': 'Admin', 'days': 0},
        {'task': 'Final Salary Processing', 'department': 'Finance', 'days': 3},
        {'task': 'Experience Letter Preparation', 'department': 'HR', 'days': 5},
        {'task': 'Clear Dues from Departments', 'department': 'Finance', 'days': 2},
    ]
    
    for item in checklist_items:
        ResignationChecklist.objects.create(
            resignation=resignation,
            task_name=item['task'],
            department=item['department'],
            due_date=resignation.last_working_date - timedelta(days=item['days'])
        )

def all_resignations(request):
    """View all resignations with advanced filters"""
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    user_role = request.session.get('user_role')
    user_email = request.session.get('user_email')
    
    # Base queryset - apply role-based filtering
    if user_role in ['ADMIN', 'HR', 'SUPER ADMIN']:
        # Super users can see all resignations except their own
        try:
            current_user_emp = Employee.objects.get(email=user_email)
            resignations = Resignation.objects.select_related('employee', 'applied_to', 'approved_by').exclude(employee=current_user_emp)
        except Employee.DoesNotExist:
            resignations = Resignation.objects.select_related('employee', 'applied_to', 'approved_by').all()
            
    elif user_role in ['MANAGER', 'TL']:
        # Managers/TLs can only see their team members' resignations (excluding their own)
        try:
            current_user_emp = Employee.objects.get(email=user_email)
            print(f"Current user: {current_user_emp.first_name} {current_user_emp.last_name}")
            
            # Check how many team members report to this manager
            team_members = Employee.objects.filter(
                Q(reporting_manager_id=current_user_emp.id) |
                Q(reporting_manager__icontains=current_user_emp.first_name)
            )
            print(f"Team members count: {team_members.count()}")
            
            # Filter resignations to only team members, excluding own resignation
            resignations = Resignation.objects.filter(
                employee_id__in=team_members.values_list('id', flat=True)
            ).exclude(employee=current_user_emp).select_related('employee', 'applied_to', 'approved_by')
            
            print(f"Team resignations found: {resignations.count()}")
            
        except Employee.DoesNotExist:
            print("Current user not found in Employee table")
            resignations = Resignation.objects.none()
            
    elif user_role == 'BRANCH MANAGER':
        # Branch Managers can see resignations from their location
        try:
            current_user_emp = Employee.objects.get(email=user_email)
            branch_manager_location = current_user_emp.location
            
            if branch_manager_location:
                # Get all employees from the same location
                location_employees = Employee.objects.filter(
                    location__iexact=branch_manager_location
                )
                print(f"Branch Manager Location: {branch_manager_location}")
                print(f"Employees in location: {location_employees.count()}")
                
                # Filter resignations to only employees from this location, excluding own resignation
                resignations = Resignation.objects.filter(
                    employee_id__in=location_employees.values_list('id', flat=True)
                ).exclude(employee=current_user_emp).select_related('employee', 'applied_to', 'approved_by')
                
                print(f"Location resignations found: {resignations.count()}")
            else:
                print("Branch manager location not set")
                resignations = Resignation.objects.none()
                
        except Employee.DoesNotExist:
            print("Branch manager profile not found")
            resignations = Resignation.objects.none()
                    
    else:
        # Regular employees can only see their own resignations
        try:
            employee = Employee.objects.get(email=user_email)
            resignations = Resignation.objects.filter(employee=employee).select_related('employee', 'applied_to', 'approved_by')
        except Employee.DoesNotExist:
            resignations = Resignation.objects.none()
    
    # Advanced filters (applied after role-based filtering)
    status_filter = request.GET.get('status')
    department_filter = request.GET.get('department')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    if status_filter:
        resignations = resignations.filter(status=status_filter)
    if department_filter:
        resignations = resignations.filter(employee__department=department_filter)
    if date_from:
        resignations = resignations.filter(resignation_date__gte=date_from)
    if date_to:
        resignations = resignations.filter(resignation_date__lte=date_to)
    
    # Search
    search_query = request.GET.get('search')
    if search_query:
        resignations = resignations.filter(
            Q(employee__first_name__icontains=search_query) |
            Q(employee__last_name__icontains=search_query) |
            Q(employee__employee_id__icontains=search_query) |
            Q(reason__icontains=search_query)
        )
    total_resignations = resignations.filter(status__in=['applied', 'accepted']).count()
    context = {
        'resignations': resignations.order_by('-created_at'),
        'total_resignations': total_resignations,
        'status_choices': Resignation.RESIGNATION_STATUS,
        'departments': Employee.objects.values_list('department', flat=True).distinct(),
        'user_name': request.session.get('user_name'),
        'user_role': user_role,
        'today_date': date.today(),
    }
    return render(request, 'resignation/all_resignations.html', context)

def my_resignation(request):
    """Employee views their own resignation(s)"""
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    try:
        employee = Employee.objects.get(email=request.session.get('user_email'))
        # Get ALL resignations for this employee, ordered by most recent first
        resignations = Resignation.objects.filter(employee=employee).order_by('-created_at')
        
        # Get resignation_id from URL parameter to show specific resignation
        resignation_id = request.GET.get('resignation_id')
        
        if resignation_id:
            # Show specific resignation
            current_resignation = get_object_or_404(Resignation, id=resignation_id, employee=employee)
        elif resignations.exists():
            # Show most recent resignation by default
            current_resignation = resignations.first()
        else:
            current_resignation = None
        
        # Get data for the current resignation being viewed
        checklist = ResignationChecklist.objects.filter(resignation=current_resignation) if current_resignation else []
        documents = ResignationDocument.objects.filter(resignation=current_resignation) if current_resignation else []
        
        # Get progress data
        notice_progress = current_resignation.get_notice_period_progress() if current_resignation else None
        exit_status = current_resignation.get_exit_process_status() if current_resignation else None
        status_timeline = current_resignation.get_status_timeline() if current_resignation else None
        
    except Employee.DoesNotExist:
        resignations = []
        current_resignation = None
        checklist = []
        documents = []
        notice_progress = None
        exit_status = None
        status_timeline = None
        
    # Check if logged-in user is HR/Admin AND is the resigning employee
    user_role = request.session.get('user_role')
    user_email = request.session.get('user_email')
    employee_email = current_resignation.employee.email if current_resignation else None
    
    # Determine if this is a self-resignation for HR/Admin
    is_self_resignation = (
        user_role in ['HR', 'ADMIN', 'SUPER ADMIN'] and 
        user_email == employee_email
    )   
    
    context = {
        'resignations': resignations,  # All resignations for dropdown
        'current_resignation': current_resignation,  # The one being viewed
        'checklist': checklist,
        'documents': documents,
        'notice_progress': notice_progress,
        'exit_status': exit_status,
        'status_timeline': status_timeline,
        'user_name': request.session.get('user_name'),
        'user_role': request.session.get('user_role'),
        'today_date': date.today(),
        'is_self_resignation':is_self_resignation,
    }
    return render(request, 'resignation/my_resignation.html', context)

def resignation_detail(request, resignation_id):
    """Detailed view of resignation with full workflow"""
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    resignation = get_object_or_404(
        Resignation.objects.select_related('employee', 'applied_to', 'approved_by', 'exit_interview_conducted_by'),
        id=resignation_id
    )
    
    # Check permissions
    if not check_resignation_access(request, resignation):
        messages.error(request, 'You can only view your own resignation details.')
        return redirect('resignation:dashboard')
    
    checklist = ResignationChecklist.objects.filter(resignation=resignation).select_related('assigned_to')
    documents = ResignationDocument.objects.filter(resignation=resignation)
    
    # Get progress data
    notice_progress = resignation.get_notice_period_progress()
    exit_status = resignation.get_exit_process_status()
    status_timeline = resignation.get_status_timeline()
    
    context = {
        'resignation': resignation,
        'checklist': checklist,
        'documents': documents,
        'notice_progress': notice_progress,
        'exit_status': exit_status,
        'status_timeline': status_timeline,
        'user_name': request.session.get('user_name'),
        'user_role': request.session.get('user_role'),
        'today_date': date.today(),
    }
    return render(request, 'resignation/resignation_detail.html', context)

def approve_resignation(request, resignation_id):
    """Approve/reject resignation with workflow"""
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    resignation = get_object_or_404(Resignation, id=resignation_id)
    user_role = request.session.get('user_role')
    user_email = request.session.get('user_email')
    
    # Check permissions - only HR/Admin/Manager can approve
    if user_role not in ['ADMIN', 'HR', 'SUPER ADMIN']:
        messages.error(request, 'You do not have permission to approve resignations.')
        return redirect('resignation:resignation_detail', resignation_id=resignation_id)
    
    # Verify approver employee exists
    try:
        approver = Employee.objects.get(email=user_email)
    except Employee.DoesNotExist:
        messages.error(request, 'Your employee profile was not found. Please contact HR.')
        return redirect('resignation:resignation_detail', resignation_id=resignation_id)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        remarks = html.escape(request.POST.get('remarks', ''))
        
        try:
            if action == 'approve':
                resignation.status = 'accepted'
                resignation.approved_by = approver
                resignation.approved_date = date.today()
                resignation.feedback = remarks
                resignation.exit_status = 'serving_notice'
                messages.success(request, ' Resignation approved successfully!')
                
            elif action == 'reject':
                resignation.status = 'rejected'
                resignation.feedback = remarks
                messages.success(request, 'L Resignation rejected!')
            
            resignation.save()
            return redirect('resignation:resignation_detail', resignation_id=resignation_id)
            
        except Exception as e:
            messages.error(request, f'Error processing resignation: {str(e)}')
    
    # GET request - show approval form
    context = {
        'resignation': resignation,
        'user_name': request.session.get('user_name'),
        'user_role': user_role,
        'today_date': date.today(),
    }
    return render(request, 'resignation/approve_resignation.html', context)

def withdraw_resignation(request, resignation_id):
    """Employee withdraws resignation with cooldown period"""
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    if request.method == 'POST':
        resignation = get_object_or_404(Resignation, id=resignation_id)
        withdrawal_reason = html.escape(request.POST.get('withdrawal_reason', ''))
        
        # Check if employee owns this resignation
        user_email = request.session.get('user_email')
        if resignation.employee.email != user_email:
            messages.error(request, 'You can only withdraw your own resignation.')
            return redirect('resignation:dashboard')
        
        # Check if resignation can be withdrawn
        if resignation.status not in ['applied', 'under_review','accepted']:
            messages.error(request, 'Resignation cannot be withdrawn at this stage.')
            return redirect('resignation:resignation_detail', resignation_id=resignation_id)
        
        try:
            resignation.status = 'withdrawn'
            resignation.withdrawal_requested = True
            resignation.withdrawal_reason = withdrawal_reason
            resignation.withdrawal_requested_at = timezone.now()
            resignation.save()
            
            # 2️⃣ DELETE checklist items
            ResignationChecklist.objects.filter(
                resignation=resignation
            ).delete()
            
            messages.success(request, 
                ' Resignation withdrawn successfully! '
                'You can reapply after 30 days if needed.'
            )
            return redirect('resignation:dashboard')
            
        except Exception as e:
            messages.error(request, f'Error withdrawing resignation: {str(e)}')
    
    return redirect('resignation:resignation_detail', resignation_id=resignation_id)

def update_checklist(request, checklist_id):
    """Update checklist item status"""
    if not request.session.get('user_authenticated'):
        return JsonResponse({'success': False, 'error': 'Not authenticated'})
    
    if request.method == 'POST':
        try:
            checklist_item = get_object_or_404(ResignationChecklist, id=checklist_id)
            completed = request.POST.get('completed') == 'true'
            remarks = request.POST.get('remarks', '')
            
            checklist_item.completed = completed
            checklist_item.completed_date = date.today() if completed else None
            checklist_item.remarks = remarks
            checklist_item.save()
            
            return JsonResponse({'success': True, 'completed': completed})
            
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid method'})

def resignation_analytics(request):
    """Advanced analytics for resignations"""
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    # Monthly trends
    current_year = date.today().year
    monthly_data = []
    for month in range(1, 13):
        count = Resignation.objects.filter(
            created_at__year=current_year,
            created_at__month=month
        ).count()
        monthly_data.append(count)
    
    # Department-wise analysis
    dept_data = []
    departments = Employee.objects.values_list('department', flat=True).distinct()
    for dept in departments:
        if dept:
            count = Resignation.objects.filter(employee__department=dept).count()
            dept_data.append({'department': dept, 'count': count})
    
    # Reason analysis
    reasons = Resignation.objects.values('reason').annotate(count=models.Count('id')).order_by('-count')[:10]
    
    # Calculate totals for templates
    total_reasons = sum(reason['count'] for reason in reasons)
    total_dept_count = sum(dept['count'] for dept in dept_data)
    
    context = {
        'monthly_data': monthly_data,
        'dept_data': dept_data,
        'reasons': reasons,
        'total_reasons': total_reasons,
        'total_dept_count': total_dept_count,
        'user_name': request.session.get('user_name'),
        'user_role': request.session.get('user_role'),
        'today_date': date.today(),
    }
    return render(request, 'resignation/analytics.html', context)

def resignation_history(request):
    """View employee's resignation history"""
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    try:
        employee = Employee.objects.get(email=request.session.get('user_email'))
        resignations = Resignation.objects.filter(employee=employee).order_by('-created_at')
        active_notice = resignations.filter(status__in=['applied', 'under_review', 'accepted']
).count()

        withdrawn_count = resignations.filter(status='withdrawn').count()

        completed_count = resignations.filter(status='accepted').count()
        
        context = {
            'resignations': resignations,
            'active_notice': active_notice,
            'active_count': active_notice,
            'withdrawn_count': withdrawn_count,
            'completed_count': completed_count,
            'user_name': request.session.get('user_name'),
            'user_role': request.session.get('user_role'),
            'today_date': date.today(),
        }
        return render(request, 'resignation/resignation_history.html', context)
        
    except Employee.DoesNotExist:
        messages.error(request, 'Employee profile not found.')
        return redirect('resignation:dashboard')

def no_due_certificate(request, resignation_id):
    """Generate and manage No Due Certificate"""
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    resignation = get_object_or_404(Resignation, id=resignation_id)
    
    # Check permissions
    if not check_resignation_access(request, resignation):
        messages.error(request, 'You do not have access to this certificate.')
        return redirect('resignation:dashboard')
    
    # Get or create No Due Certificate
    no_due_cert, created = NoDueCertificate.objects.get_or_create(
        resignation=resignation,
        defaults={
            'final_settlement_amount': resignation.final_settlement,
            'settlement_date': resignation.last_working_date,
        }
    )
    # Check if logged-in user is HR/Admin AND is the resigning employee
    user_role = request.session.get('user_role')
    user_email = request.session.get('user_email')
    employee_email = resignation.employee.email if resignation.employee else None
    
    # Determine if this is a self-resignation for HR/Admin
    is_self_resignation = (
        user_role in ['HR', 'ADMIN', 'SUPER ADMIN'] and 
        user_email == employee_email
    )
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'employee_sign':
            # Employee digital signature
            signature_data = request.POST.get('signature_data')
            if signature_data:
                no_due_cert.employee_signature = signature_data
                no_due_cert.employee_signed_at = timezone.now()
                no_due_cert.employee_ip_address = get_client_ip(request)
                no_due_cert.save()
                messages.success(request, ' Digital signature submitted successfully!')
                
        elif action == 'hr_approve':
            # HR approval and signature
            if request.session.get('user_role') in ['HR', 'ADMIN', 'SUPER ADMIN']:
                signature_data = request.POST.get('hr_signature_data')
                if signature_data:
                    try:
                        hr_employee = Employee.objects.get(email=request.session.get('user_email'))
                        no_due_cert.hr_signature = signature_data
                        no_due_cert.hr_signed_at = timezone.now()
                        no_due_cert.hr_approved_by = hr_employee
                        no_due_cert.is_completed = True
                        no_due_cert.generate_certificate_number()
                        no_due_cert.save()
                        messages.success(request, ' No Due Certificate approved and completed!')
                    except Employee.DoesNotExist:
                        messages.error(request, 'HR employee not found.')
        
        elif action == 'update_settlement':
            # Update settlement details
            settlement_amount = request.POST.get('settlement_amount')
            settlement_date = request.POST.get('settlement_date')
            settlement_mode = request.POST.get('settlement_mode')
            
            if settlement_amount:
                no_due_cert.final_settlement_amount = settlement_amount
            if settlement_date:
                no_due_cert.settlement_date = settlement_date
            if settlement_mode:
                no_due_cert.settlement_mode = settlement_mode
            no_due_cert.save()
            messages.success(request, 'Settlement details updated!')
        
        return redirect('resignation:no_due_certificate', resignation_id=resignation_id)
    
    context = {
        'resignation': resignation,
        'no_due_cert': no_due_cert,
        'user_name': request.session.get('user_name'),
        'user_role': request.session.get('user_role'),
        'today_date': date.today(),
        'is_self_resignation': is_self_resignation,
    }
    return render(request, 'resignation/no_due_certificate.html', context)

# --------------------- PDF helpers and generators ---------------------

class BaseStyledPDF(FPDF):
    """Utility: page break guard that is aware of bottom margin."""
    def check_page_break(self, needed_height):
        bottom_limit = self.h - self.b_margin
        if (self.get_y() + needed_height) > bottom_limit:
            self.add_page()

class NoDueCertificatePDF(BaseStyledPDF):
    def __init__(self):
        super().__init__(orientation="P", unit="mm", format="A4")
        font_path = os.path.join(settings.BASE_DIR, "static", "fonts", "DejaVuSans.ttf")
        self.add_font("DejaVu", "", font_path, uni=True)
        self.add_font("DejaVu", "B", font_path, uni=True)
        self.add_font("DejaVu", "I", font_path, uni=True)

        # tighter bottom margin to reduce height
        self.set_auto_page_break(auto=True, margin=16)

    def header(self):
        logo_path = os.path.join(settings.BASE_DIR, "static", "img", "ikontellogot.png")
        try:
            img_w = 28  # smaller logo
            x_pos = self.w - self.r_margin - img_w
            self.image(logo_path, x=x_pos, y=8, w=img_w)
        except Exception:
            pass

        self.set_xy(self.l_margin, 10)
        self.set_font("DejaVu", "B", 15)
        self.cell(0, 7, "NO DUE CERTIFICATE", ln=True)
        self.ln(3)

    def footer(self):
        self.set_y(-20)
        self.set_font("DejaVu", "", 8)
        self.set_text_color(120, 120, 120)
        self.set_draw_color(200, 200, 200)
        self.line(10, self.get_y(), self.w - 10, self.get_y())
        self.ln(3)
        self.multi_cell(
            0,
            4,
            "IKONTEL SOLUTIONS PVT LTD | NO.72, 73 & 74, 1ST FLOOR AMRBP BUILDING, "
            "MARGOSA ROAD, 17TH CROSS RD, MALLESWARAM, BENGALURU, KARNATAKA",
            align="C",
        )

    def section_box(self, title):
        self.set_font("DejaVu", "B", 11)
        self.cell(0, 6, title, ln=True)
        self.set_draw_color(220, 220, 220)
        y = self.get_y()
        self.line(self.l_margin, y, self.w - self.r_margin, y)
        self.ln(4)

    def cell_pair(self, label, value, label_w=110, value_line_height=6):
        self.check_page_break(18)
        page_w = self.w - self.l_margin - self.r_margin
        value_w = page_w - label_w

        self.set_font("DejaVu", "B", 9)
        self.cell(label_w, value_line_height, f"{label}:", ln=False)

        x = self.get_x()
        y = self.get_y()

        self.set_font("DejaVu", "", 9)
        self.multi_cell(value_w, value_line_height, value or "N/A")

        h = self.get_y() - y
        self.set_draw_color(210, 210, 210)
        self.rect(x - 1, y - 1, value_w + 2, h + 2)

        self.set_xy(self.l_margin, y + h + 4)

    def declaration_content(self, text):
        self.set_font("DejaVu", "", 10)
        self.multi_cell(0, 6, text)
        self.ln(6)

class ExitInterviewPDF(BaseStyledPDF):
    def __init__(self):
        super().__init__()
        font_path = os.path.join(settings.BASE_DIR, "static", "fonts", "DejaVuSans.ttf")
        self.add_font("DejaVu", "", font_path, uni=True)
        self.add_font("DejaVu", "B", font_path, uni=True)
        # keep footer closer using smaller margin
        self.set_auto_page_break(auto=True, margin=PAGE_BOTTOM_MARGIN)

    def header(self):
        # place logo consistently and ensure consistent header->content spacing
        logo_path = os.path.join(settings.BASE_DIR, "static", "img", "ikontellogot.png")
        try:
            img_w = 34
            x_pos = self.w - self.r_margin - img_w
            self.image(logo_path, x=x_pos, y=10, w=img_w)
        except Exception:
            pass
        self.set_xy(self.l_margin, 12)
        self.set_font("DejaVu", "B", 16)
        self.cell(0, 7, "EXIT INTERVIEW FORM", ln=True, align="L")
        # **Important:** small consistent gap so first section doesn't get too close to header
        self.ln(4)

    def footer(self):
        self.set_y(-22)
        self.set_font("DejaVu", "", 8)
        self.set_text_color(128, 128, 128)
        footer_text = (
            "IKONTEL SOLUTIONS PVT LTD | "
            "NO.72, 73 & 74, 1ST FLOOR AMRBP BUILDING, MARGOSA ROAD, 17TH CROSS RD, "
            "MALLESWARAM, BENGALURU, KARNATAKA"
        )
        self.set_draw_color(200, 200, 200)
        self.line(10, self.get_y(), self.w - 10, self.get_y())
        self.ln(3)
        self.multi_cell(0, 4, footer_text, align="C")

    def section_box(self, title):
        self.set_font("DejaVu", "B", 11)
        self.cell(0, 6, title, ln=True)
        self.ln(2)
        self.set_draw_color(220, 220, 220)
        line_y = self.get_y()
        self.line(self.l_margin, line_y, self.w - self.r_margin, line_y)
        self.ln(4)

    def cell_pair(self, label, value, label_w=120, value_w=None, value_line_height=6):
        self.check_page_break(20)
        page_inner_w = self.w - self.l_margin - self.r_margin
        if value_w is None:
            value_w = page_inner_w - label_w
        self.set_font("DejaVu", "B", 9)
        self.cell(label_w, value_line_height, f"{label}:", ln=False)
        x_before = self.get_x()
        y_before = self.get_y()
        self.set_xy(x_before, y_before)
        self.set_font("DejaVu", "", 9)
        self.multi_cell(value_w, value_line_height, value or "N/A")
        y_after = self.get_y()
        box_h = y_after - y_before
        self.set_xy(x_before - 1, y_before - 1)
        self.set_draw_color(210, 210, 210)
        try:
            self.rect(x_before - 1, y_before - 1, value_w + 2, box_h + 2)
        except Exception:
            pass
        self.set_xy(self.l_margin, y_after + 6)

    def boxed_text(self, text, words_limit=WORDS_PER_ANSWER, box_height=ANSWER_BOX_HEIGHT, padding=3):
        """
        Draw a bordered box with a fixed height and put the (trimmed) text inside.
        - Trims text to words_limit (appends " ..." if trimmed).
        - Ensures the box has fixed height (box_height) so layout stays consistent.
        - Uses check_page_break to ensure the box won't overflow the page bottom.
        """
        if text is None:
            text = ""
        # trim by words
        words = text.split()
        if len(words) > words_limit:
            display_text = " ".join(words[:words_limit]) + " ..."
        else:
            display_text = " ".join(words)

        # ensure page has room for this fixed box
        self.check_page_break(box_height + 6)

        box_w = self.w - self.l_margin - self.r_margin
        x = self.get_x()
        y = self.get_y()

        # Draw border rectangle
        self.set_draw_color(210, 210, 210)
        try:
            self.rect(x, y, box_w, box_height)
        except Exception:
            pass

        # Print text inside with small padding
        pad_x = padding
        pad_y = padding
        inner_x = x + pad_x
        inner_w = box_w - 2 * pad_x
        inner_y = y + pad_y

        self.set_xy(inner_x, inner_y)
        self.set_font("DejaVu", "", 9)
        # limit lines that can be printed to avoid text spilling visually beyond the box
        max_lines = int((box_height - 2 * pad_y) / LINE_HEIGHT)
        # Use multi_cell to print wrapped text; even if it expands cursor, we'll restore to box bottom
        self.multi_cell(inner_w, LINE_HEIGHT, display_text)
        # Reset cursor to bottom of the box (so next content always starts after the fixed box)
        self.set_xy(self.l_margin, y + box_height + 6)

# --------------------- PDF generation endpoints ---------------------

def download_no_due_certificate(request, resignation_id):
    resignation = get_object_or_404(Resignation, id=resignation_id)
    no_due_cert = get_object_or_404(NoDueCertificate, resignation=resignation)

    try:
        pdf = NoDueCertificatePDF()
        pdf.add_page()

        # Declaration
        pdf.section_box("Declaration")
        paragraphs = [
            "Received my salary towards my full and final settlement through online/NEFT/Transfer. "
            "All my dues from IKONTEL Solutions Pvt Ltd are cleared.",
            "I have received all my dues pertaining to earned leave encashment, notice pay, "
            "service compensation, leave or any other claim in connection with my employment.",
            "I have no further claim or demand for reinstatement or re-employment.",
            "I will not raise any claim or demand whatsoever against the Company.",
        ]
        for p in paragraphs:
            pdf.declaration_content(p)
        pdf.ln(15)
        # Employee details
        pdf.section_box("Employee Details")
        pdf.cell_pair(
            "Employee Name",
            f"{resignation.employee.first_name} {resignation.employee.last_name}",
        )
        pdf.ln(2)
        pdf.cell_pair("Employee ID", resignation.employee.employee_id)
        pdf.ln(2)
        pdf.cell_pair("Department", resignation.employee.department or "N/A")
        pdf.ln(2)
        pdf.cell_pair("Region", resignation.employee.location or "N/A")

        pdf.ln(70)

        # =========================
        # SIGNATURE BLOCK
        # =========================
        pdf.check_page_break(50)
        pdf.set_font("DejaVu", "", 9)

        sign_w = 55      # reduced width
        sign_h = 14      # reduced height
        gap = 80

        left_x = pdf.l_margin
        right_x = left_x + sign_w + gap
        y = pdf.get_y()

        # HR SIGNATURE (LEFT)
        if no_due_cert.hr_signature:
            pdf.image(no_due_cert.hr_signature, x=left_x +15, y=y, w=sign_w, h=sign_h)
        pdf.set_xy(left_x, y + sign_h + 1)
        
        pdf.set_x(left_x)
        pdf.cell(sign_w, 5, "HR Signature", align="C")

        # EMPLOYEE SIGNATURE (RIGHT)
        if no_due_cert.employee_signature:
            pdf.image(
                no_due_cert.employee_signature,
                x=right_x +15,
                y=y,
                w=sign_w,
                h=sign_h,
            )

        pdf.set_xy(right_x, y + sign_h + 1)
        pdf.set_x(right_x)
        pdf.cell(sign_w, 5, "Employee Signature", align="C")
        
        # Place & Date under employee sign only
        settlement_date = (
            no_due_cert.settlement_date.strftime("%d %b %Y")
            if no_due_cert.settlement_date
            else datetime.now().strftime("%d %b %Y")
        )

        pdf.ln(10)
        pdf.set_x(right_x -1)
        pdf.set_font("DejaVu", "", 9)
        pdf.cell(sign_w, 5, "Place: Bangalore", align="C")
        pdf.ln(6)
        pdf.set_x(right_x)
        pdf.cell(sign_w, 5, f"Date: {settlement_date}", align="C")

        # Output
        buffer = io.BytesIO()
        pdf.output(buffer)
        buffer.seek(0)

        response = HttpResponse(buffer, content_type="application/pdf")
        filename = f"No_Due_Certificate_{resignation.employee.employee_id}.pdf"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return HttpResponse("Error generating PDF")

def download_no_due_certificate_fallback(request, resignation_id):
    resignation = get_object_or_404(Resignation, id=resignation_id)
    no_due_cert = get_object_or_404(NoDueCertificate, resignation=resignation)
    context = {
        'resignation': resignation,
        'no_due_cert': no_due_cert,
        'today_date': datetime.now().strftime('%d-%b-%Y')
    }
    html_string = render_to_string('resignation/certificate_pdf_fallback.html', context)
    result = io.BytesIO()
    pdf = pisa.pisaDocument(io.BytesIO(html_string.encode("UTF-8")), result)
    if not pdf.err:
        response = HttpResponse(result.getvalue(), content_type='application/pdf')
        filename = f"no_due_certificate_{resignation.employee.employee_id}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    else:
        return HttpResponse('Error generating PDF')

def get_client_ip(request):
    """Get client IP address"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def exit_interview(request, resignation_id):
    """Exit Interview form with digital signature"""
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    resignation = get_object_or_404(Resignation, id=resignation_id)
    
    # Check permissions
    if not check_resignation_access(request, resignation):
        messages.error(request, 'You do not have access to this exit interview.')
        return redirect('resignation:dashboard')
    
    # Get or create Exit Interview
    exit_interview_obj, created = ExitInterview.objects.get_or_create(
        resignation=resignation
    )
    # Check if logged-in user is HR/Admin AND is the resigning employee
    user_role = request.session.get('user_role')
    user_email = request.session.get('user_email')
    employee_email = resignation.employee.email if resignation.employee else None
    
    # Determine if this is a self-resignation for HR/Admin
    is_self_resignation = (
        user_role in ['HR', 'ADMIN', 'SUPER ADMIN'] and 
        user_email == employee_email
    )
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'save_interview':
            # Save all interview responses
            exit_interview_obj.reason_for_leaving = html.escape(request.POST.get('reason_for_leaving', ''))
            exit_interview_obj.concerns_shared_prior = html.escape(request.POST.get('concerns_shared_prior', ''))
            exit_interview_obj.single_event_responsible = html.escape(request.POST.get('single_event_responsible', ''))
            exit_interview_obj.new_company_offer = html.escape(request.POST.get('new_company_offer', ''))
            exit_interview_obj.valued_about_company = html.escape(request.POST.get('valued_about_company', ''))
            exit_interview_obj.disliked_about_company = html.escape(request.POST.get('disliked_about_company', ''))
            exit_interview_obj.relationship_with_manager = html.escape(request.POST.get('relationship_with_manager', ''))
            exit_interview_obj.supervisor_improvement = html.escape(request.POST.get('supervisor_improvement', ''))
            exit_interview_obj.liked_about_job = html.escape(request.POST.get('liked_about_job', ''))
            exit_interview_obj.disliked_about_job = html.escape(request.POST.get('disliked_about_job', ''))
            exit_interview_obj.job_improvement_suggestions = html.escape(request.POST.get('job_improvement_suggestions', ''))
            exit_interview_obj.resources_support = html.escape(request.POST.get('resources_support', ''))
            exit_interview_obj.employee_morale = html.escape(request.POST.get('employee_morale', ''))
            exit_interview_obj.clear_goals = html.escape(request.POST.get('clear_goals', ''))
            exit_interview_obj.performance_feedback = html.escape(request.POST.get('performance_feedback', ''))
            exit_interview_obj.quality_commitment = html.escape(request.POST.get('quality_commitment', ''))
            exit_interview_obj.career_development = html.escape(request.POST.get('career_development', ''))
            exit_interview_obj.workplace_recommendations = html.escape(request.POST.get('workplace_recommendations', ''))
            exit_interview_obj.policies_fairness = html.escape(request.POST.get('policies_fairness', ''))
            exit_interview_obj.success_qualities = html.escape(request.POST.get('success_qualities', ''))
            exit_interview_obj.replacement_qualities = html.escape(request.POST.get('replacement_qualities', ''))
            exit_interview_obj.compensation_feedback = html.escape(request.POST.get('compensation_feedback', ''))
            exit_interview_obj.future_considerations = html.escape(request.POST.get('future_considerations', ''))
            exit_interview_obj.recommend_company = html.escape(request.POST.get('recommend_company', ''))
            exit_interview_obj.additional_comments = html.escape(request.POST.get('additional_comments', ''))
            
            # Set interview date if conducted by HR
            if request.session.get('user_role') in ['HR', 'ADMIN', 'SUPER ADMIN']:
                exit_interview_obj.interview_date = date.today()
                try:
                    exit_interview_obj.conducted_by = Employee.objects.get(email=request.session.get('user_email'))
                except Employee.DoesNotExist:
                    pass
            
            exit_interview_obj.save()
            messages.success(request, ' Exit Interview responses saved successfully!')
            
        elif action == 'employee_sign':
            # Employee digital signature
            signature_data = request.POST.get('signature_data')
            if signature_data:
                exit_interview_obj.employee_signature = signature_data
                exit_interview_obj.employee_signed_at = timezone.now()
                exit_interview_obj.save()
                messages.success(request, ' Digital signature submitted successfully!')
                
        elif action == 'hr_sign':
            # HR digital signature
            if request.session.get('user_role') in ['HR', 'ADMIN', 'SUPER ADMIN']:
                signature_data = request.POST.get('hr_signature_data')
                if signature_data:
                    exit_interview_obj.hr_signature = signature_data
                    exit_interview_obj.hr_signed_at = timezone.now()
                    exit_interview_obj.is_completed = True
                    exit_interview_obj.save()
                    messages.success(request, ' Exit Interview completed and signed!')
        
        return redirect('resignation:exit_interview', resignation_id=resignation_id)
    
    context = {
        'resignation': resignation,
        'exit_interview': exit_interview_obj,
        'user_name': request.session.get('user_name'),
        'user_role': request.session.get('user_role'),
        'today_date': date.today(),
        'is_self_resignation': is_self_resignation,
    }
    return render(request, 'resignation/exit_interview.html', context)

def download_exit_interview(request, resignation_id):
    if not request.session.get('user_authenticated'):
        return redirect('login')

    resignation = get_object_or_404(Resignation, id=resignation_id)
    exit_interview = get_object_or_404(ExitInterview, resignation=resignation)

    try:
        pdf = ExitInterviewPDF()
        pdf.add_page()

        # Employee Information
        pdf.section_box("Employee Information")
        pdf.cell_pair("Employee Name", f"{resignation.employee.first_name} {resignation.employee.last_name}")
        pdf.cell_pair("Employee ID", resignation.employee.employee_id)
        pdf.cell_pair("Department", resignation.employee.department or "N/A")
        pdf.cell_pair("Region", resignation.employee.location or "N/A")

        pdf.ln(6)

        # Questions
        pdf.section_box("Exit Interview Questions & Answers")
        questions = [
            ("1. Why have you decided to leave the company?", exit_interview.reason_for_leaving),
            ("2. Have you shared your concerns with anyone in the company prior to deciding to leave?", exit_interview.concerns_shared_prior),
            ("3. Was a single event responsible for your decision to leave?", exit_interview.single_event_responsible),
            ("4. What does your new company offer that encouraged you to accept their offer and leave this company?", exit_interview.new_company_offer),
            ("5. What do you value about the company?", exit_interview.valued_about_company),
            ("6. What did you dislike about the company?", exit_interview.disliked_about_company),
            ("7. How was your relationship with your manager?", exit_interview.relationship_with_manager),
            ("8. What could your supervisor do to improve his/her management style and skill?", exit_interview.supervisor_improvement),
            ("9. What did you like most about your job?", exit_interview.liked_about_job),
            ("10. What did you dislike about your job? What would you change in that?", exit_interview.disliked_about_job),
            ("11. Do you feel you had the resources and support necessary to accomplish your job?", exit_interview.resources_support),
            ("12. What is your experience of employee morale and motivation in the company?", exit_interview.employee_morale),
            ("13. Did you have clear goals and know what was expected of you in your job?", exit_interview.clear_goals),
            ("14. Did you receive adequate feedback about your performance?", exit_interview.performance_feedback),
            ("15. Describe your experience of the company's commitment to quality and customer service.", exit_interview.quality_commitment),
            ("16. Did the management help you accomplish your personal and professional development?", exit_interview.career_development),
            ("17. What would you recommend to help us create a better workplace?", exit_interview.workplace_recommendations),
            ("18. Do the policies and procedures help create a fair workplace?", exit_interview.policies_fairness),
            ("19. Describe the qualities of person who is most likely to succeed in this company.", exit_interview.success_qualities),
            ("20. What are the key qualities we should seek in your replacement?", exit_interview.replacement_qualities),
            ("21. Any recommendations regarding our compensation and benefits?", exit_interview.compensation_feedback),
            ("22. What would make you consider working for this company again?", exit_interview.future_considerations),
            ("23. Additional comments:", exit_interview.additional_comments),
        ]

        # Render each question with a fixed-size box below it.
        for q, a in questions:
            # Question label
            pdf.set_font("DejaVu", "B", 9)
            pdf.multi_cell(0, LINE_HEIGHT, q)
            pdf.ln(2)
            # Boxed (fixed height) trimmed text
            pdf.boxed_text(a or "", words_limit=WORDS_PER_ANSWER, box_height=ANSWER_BOX_HEIGHT)

        # ----------------------------
        # SIGNATURE SECTION (IMAGE ON TOP, LABEL BELOW) - Integrated placement
        # Always align to content area and place on the last page just above the footer.
        # ----------------------------
        if exit_interview.employee_signature or exit_interview.hr_signature:
            # set font for labels
            try:
                pdf.set_font("DejaVu", "B", 10)
            except Exception:
                pdf.set_font("Helvetica", "B", 10)

            # Temporarily disable auto page break to compute exact positions precisely
            pdf.set_auto_page_break(False)
            try:
                page_height = pdf.h
                # bottom reserved space for footer: use a safe value large enough not to overlap footer
                bottom_reserved = max(getattr(pdf, "b_margin", PAGE_BOTTOM_MARGIN), FOOTER_RESERVED)

                # compute top coordinate for signature block so the block bottom stays above reserved footer
                sig_top_target = page_height - bottom_reserved - SIGNATURE_BLOCK_HEIGHT

                current_y = pdf.get_y()
                # if current cursor is lower (i.e., too close to bottom/reserved area), add a new page
                if current_y > sig_top_target:
                    pdf.add_page()
                    # recompute (page dimensions unchanged)
                    sig_top_target = page_height - bottom_reserved - SIGNATURE_BLOCK_HEIGHT

                # set Y to target (so signature images sit in consistent position)
                pdf.set_y(sig_top_target)

                # compute horizontal positions aligned with content area (l_margin..w-r_margin)
                content_x = pdf.l_margin
                content_w = pdf.w - pdf.l_margin - pdf.r_margin
                half_w = content_w / 2
                emp_x = content_x + 6
                hr_x = content_x + half_w + 6

                # Employee Signature (Left)
                if exit_interview.employee_signature:
                    try:
                        pdf.image(exit_interview.employee_signature, x=emp_x, y=sig_top_target, w=SIG_IMG_WIDTH)
                    except Exception:
                        # fallback placeholder rectangle + text
                        pdf.rect(emp_x, sig_top_target, SIG_IMG_WIDTH, SIG_IMG_BOX_HEIGHT)
                        pdf.set_xy(emp_x, sig_top_target + 6)
                        pdf.set_font("DejaVu", "", 9)
                        pdf.cell(SIG_IMG_WIDTH, SIG_IMG_BOX_HEIGHT - 6, "Digitally signed", ln=False)
                else:
                    # placeholder rectangle
                    pdf.rect(emp_x, sig_top_target, SIG_IMG_WIDTH, SIG_IMG_BOX_HEIGHT)
                    pdf.set_xy(emp_x, sig_top_target + 6)
                    pdf.set_font("DejaVu", "", 9)
                    pdf.cell(SIG_IMG_WIDTH, SIG_IMG_BOX_HEIGHT - 6, "No signature", ln=False)

                # label under employee signature
                pdf.set_xy(emp_x, sig_top_target + SIG_IMG_BOX_HEIGHT + SIG_LABEL_GAP)
                pdf.set_font("DejaVu", "B", 9)
                pdf.cell(SIG_IMG_WIDTH, LINE_HEIGHT, "Employee Signature:", ln=False, align="L")

                # HR Signature (Right)
                if exit_interview.hr_signature:
                    try:
                        pdf.image(exit_interview.hr_signature, x=hr_x, y=sig_top_target, w=SIG_IMG_WIDTH)
                    except Exception:
                        pdf.rect(hr_x, sig_top_target, SIG_IMG_WIDTH, SIG_IMG_BOX_HEIGHT)
                        pdf.set_xy(hr_x, sig_top_target + 6)
                        pdf.set_font("DejaVu", "", 9)
                        pdf.cell(SIG_IMG_WIDTH, SIG_IMG_BOX_HEIGHT - 6, "Digitally signed", ln=False)
                else:
                    pdf.rect(hr_x, sig_top_target, SIG_IMG_WIDTH, SIG_IMG_BOX_HEIGHT)
                    pdf.set_xy(hr_x, sig_top_target + 6)
                    pdf.set_font("DejaVu", "", 9)
                    pdf.cell(SIG_IMG_WIDTH, SIG_IMG_BOX_HEIGHT - 6, "No signature", ln=False)

                # label under HR signature
                pdf.set_xy(hr_x, sig_top_target + SIG_IMG_BOX_HEIGHT + SIG_LABEL_GAP)
                pdf.set_font("DejaVu", "B", 9)
                pdf.cell(SIG_IMG_WIDTH, LINE_HEIGHT, "HR Signature:", ln=False, align="L")

                # move cursor below signature block and add small spacing
                pdf.set_y(sig_top_target + SIGNATURE_BLOCK_HEIGHT + 6)
                pdf.ln(2)

            finally:
                # restore auto page break and bottom margin behavior
                pdf.set_auto_page_break(True, margin=PAGE_BOTTOM_MARGIN)

        # Output PDF
        pdf_buffer = io.BytesIO()
        pdf.output(pdf_buffer)
        pdf_buffer.seek(0)

        response = HttpResponse(pdf_buffer, content_type="application/pdf")
        employee_name_safe = f"{resignation.employee.first_name}_{resignation.employee.last_name}".replace(" ", "_")
        filename = f"Exit_Interview_{employee_name_safe}_{datetime.now().strftime('%b_%Y')}.pdf"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    except Exception:
        return download_exit_interview_fallback(request, resignation_id)

def download_exit_interview_fallback(request, resignation_id):
    resignation = get_object_or_404(Resignation, id=resignation_id)
    exit_interview = get_object_or_404(ExitInterview, resignation=resignation)
    context = {
        'resignation': resignation,
        'exit_interview': exit_interview,
        'today_date': datetime.now().strftime('%d-%b-%Y')
    }
    html_string = render_to_string('resignation/exit_interview_pdf_fallback.html', context)
    result = io.BytesIO()
    pdf = pisa.pisaDocument(io.BytesIO(html_string.encode("UTF-8")), result)
    if not pdf.err:
        response = HttpResponse(result.getvalue(), content_type='application/pdf')
        filename = f"exit_interview_{resignation.employee.employee_id}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    else:
        return HttpResponse('Error generating PDF')
    
    
def upload_document(request, resignation_id):
    """Sirf Exit Interview aur No Due Certificate upload ke liye"""
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    resignation = get_object_or_404(Resignation, id=resignation_id)
    
    # Permission check
    user_email = request.session.get('user_email')
    if user_email != resignation.employee.email and request.session.get('user_role') not in ['HR', 'ADMIN']:
        messages.error(request, 'You can only upload documents for your own resignation.')
        return redirect('resignation:dashboard')
    
    # Get current employee
    try:
        employee = Employee.objects.get(email=user_email)
    except Employee.DoesNotExist:
        messages.error(request, 'Employee profile not found.')
        return redirect('resignation:dashboard')
    
    if request.method == 'POST':
        try:
            document_type = request.POST.get('document_type')
            document_file = request.FILES.get('document_file')
            description = request.POST.get('description', '')
            
            # File validation - sirf PDF allow karein
            if not document_file.name.lower().endswith('.pdf'):
                messages.error(request, 'Only PDF files are allowed.')
                return redirect('resignation:upload_document', resignation_id=resignation_id)
            
            # File size check (5MB max)
            if document_file.size > 5 * 1024 * 1024:
                messages.error(request, 'File size must be less than 5MB.')
                return redirect('resignation:upload_document', resignation_id=resignation_id)
            
            # Document name automatically generate karein
            document_name = f"{document_type.replace('_', ' ').title()} - {resignation.employee.first_name}"
            
            # Save document
            document = ResignationDocument(
                resignation=resignation,
                document_type=document_type,
                document_name=document_name,
                document_file=document_file,
                uploaded_by=employee,
                description=description
            )
            document.save()
            
            messages.success(request, f' {document_type.replace("_", " ").title()} uploaded successfully!')
            return redirect('resignation:resignation_detail', resignation_id=resignation_id)
            
        except Exception as e:
            messages.error(request, f'Error uploading document: {str(e)}')
    
    context = {
        'resignation': resignation,
        'user_name': request.session.get('user_name'),
        'user_role': request.session.get('user_role'),
    }
    return render(request, 'resignation/document_upload.html', context)

def delete_document(request, document_id):
    """Document delete karne ke liye"""
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    document = get_object_or_404(ResignationDocument, id=document_id)
    resignation_id = document.resignation.id
    
    # Permission check
    user_email = request.session.get('user_email')
    user_role = request.session.get('user_role')
    
    if user_role not in ['HR', 'ADMIN'] and document.uploaded_by.email != user_email:
        messages.error(request, 'You can only delete your own documents.')
        return redirect('resignation:resignation_detail', resignation_id=resignation_id)
    
    try:
        document.delete()
        messages.success(request, ' Document deleted successfully!')
    except Exception as e:
        messages.error(request, f'Error deleting document: {str(e)}')
    
    return redirect('resignation:resignation_detail', resignation_id=resignation_id)
