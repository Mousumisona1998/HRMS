from django.db import models
from hr.models import Employee
from datetime import date 
from django.utils import timezone
from datetime import timedelta
from django.core.exceptions import ValidationError

class Resignation(models.Model):
    RESIGNATION_STATUS = [
        ('applied', 'Applied'),
        ('under_review', 'Under Review'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('withdrawn', 'Withdrawn'),
        ('completed', 'Completed'),
    ]
    
    EXIT_STATUS = [
        ('serving_notice', 'Serving Notice Period'),
        ('notice_completed', 'Notice Period Completed'),
        ('immediate', 'Immediate Exit'),
        ('buyout', 'Notice Period Buyout'),
    ]
    
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    resignation_date = models.DateField()
    last_working_date = models.DateField()
    reason = models.TextField()
    feedback = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=RESIGNATION_STATUS, default='applied')
    exit_status = models.CharField(max_length=20, choices=EXIT_STATUS, default='serving_notice')
    
    # Withdrawal fields
    withdrawal_requested = models.BooleanField(default=False)
    withdrawal_reason = models.TextField(blank=True, null=True)
    withdrawal_requested_at = models.DateTimeField(null=True, blank=True)
    
    # Approval workflow
    applied_to = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name='resignations_received')
    approved_by = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name='resignations_approved')
    approved_date = models.DateField(null=True, blank=True)
    
    # Notice period details
    notice_period_days = models.IntegerField(default=60)
    actual_notice_days = models.IntegerField(default=0)
    notice_period_start = models.DateField(null=True, blank=True)
    notice_period_end = models.DateField(null=True, blank=True)
    
    # Exit details
    exit_interview_date = models.DateField(null=True, blank=True)
    exit_interview_conducted_by = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name='exit_interviews')
    exit_interview_notes = models.TextField(blank=True, null=True)
    
    # Financial details
    pending_salary = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    pending_bonus = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    deductions = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    final_settlement = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    
    # Resignation history tracking
    resignation_count = models.IntegerField(default=1, help_text="Number of times employee has resigned")
    is_reapplied = models.BooleanField(default=False, help_text="If this is a reapplication after withdrawal")
    previous_resignation = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, 
                                           related_name='reapplications')
    
    # System fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'resignation_resignation'
        constraints = [
            models.UniqueConstraint(
                fields=['employee', 'status'],
                condition=~models.Q(status__in=['withdrawn', 'rejected', 'completed']),
                name='unique_active_resignation_per_employee'
            )
        ]
    
    def __str__(self):
        return f"{self.employee} - {self.resignation_date}"
    
    def clean(self):
        """Validate resignation dates"""
        if self.resignation_date and self.last_working_date:
            if self.resignation_date > self.last_working_date:
                raise ValidationError("Last working date must be after resignation date")
            if self.resignation_date < date.today():
                raise ValidationError("Resignation date cannot be in the past")
    
    def get_notice_period_progress(self):
        """Calculate notice period progress with proper date handling"""
        today = date.today()
        
        # Only calculate for accepted resignations with valid dates
        if self.status != 'accepted' or not self.last_working_date:
            return None
        
        # Ensure dates are valid
        if self.resignation_date >= self.last_working_date:
            return None
        
        # Calculate total calendar days
        total_days = (self.last_working_date - self.resignation_date).days
        days_completed = (today - self.resignation_date).days
        
        # Handle edge cases
        if today < self.resignation_date:
            days_completed = 0
        elif today > self.last_working_date:
            days_completed = total_days
        
        days_remaining = max(0, (self.last_working_date - today).days)
        
        # Ensure we don't exceed total days
        days_completed = min(days_completed, total_days)
        
        completion_percentage = (days_completed / total_days) * 100 if total_days > 0 else 0
        
        return {
            'total_days': total_days,
            'days_completed': days_completed,
            'days_remaining': days_remaining,
            'completion_percentage': min(completion_percentage, 100),
            'is_completed': days_remaining <= 0,
            'start_date': self.resignation_date,
            'end_date': self.last_working_date,
            'today': today
        }
    
    def get_exit_process_status(self):
        """Get detailed exit process completion status"""
        try:
            no_due_cert = NoDueCertificate.objects.get(resignation=self)
            no_due_status = no_due_cert.is_completed
        except NoDueCertificate.DoesNotExist:
            no_due_status = False
            
        try:
            exit_interview = ExitInterview.objects.get(resignation=self)
            exit_interview_status = exit_interview.is_completed
        except ExitInterview.DoesNotExist:
            exit_interview_status = False
            
        # Checklist completion with detailed breakdown
        checklist_items = ResignationChecklist.objects.filter(resignation=self)
        total_checklist = checklist_items.count()
        completed_checklist = checklist_items.filter(completed=True).count()
        checklist_progress = (completed_checklist / total_checklist * 100) if total_checklist > 0 else 0
        
        # Calculate days until last working date
        days_until_exit = (self.last_working_date - date.today()).days if self.last_working_date else 0
        
        return {
            'no_due_certificate': no_due_status,
            'exit_interview': exit_interview_status,
            'checklist_progress': checklist_progress,
            'checklist_completed': completed_checklist,
            'checklist_total': total_checklist,
            'final_settlement': bool(self.final_settlement and self.final_settlement > 0),
            'days_until_exit': max(0, days_until_exit),
            'is_on_track': checklist_progress >= (100 - days_until_exit) if days_until_exit > 0 else True
        }
    
    def get_status_timeline(self):
        """Get detailed status timeline with accurate dates"""
        timeline = []
        today = date.today()
        
        # Step 1: Applied (always exists)
        timeline.append({
            'status': 'applied',
            'label': 'Resignation Applied',
            'date': self.created_at.date(),
            'completed': True,
            'active': False,
            'icon': 'fas fa-paper-plane'
        })
        
        # Step 2: Under Review (if not immediately processed)
        if self.status in ['under_review', 'accepted', 'rejected', 'completed']:
            review_date = self.created_at.date() + timedelta(days=1)
            timeline.append({
                'status': 'under_review',
                'label': 'Under Manager Review',
                'date': review_date,
                'completed': True,
                'active': False,
                'icon': 'fas fa-search'
            })
        
        # Step 3: Approved/Rejected
        if self.status in ['accepted', 'completed'] and self.approved_date:
            timeline.append({
                'status': 'accepted',
                'label': 'Resignation Accepted',
                'date': self.approved_date,
                'completed': True,
                'active': False,
                'icon': 'fas fa-check-circle'
            })
            
            # Step 4: Notice Period (only if accepted)
            notice_progress = self.get_notice_period_progress()
            if notice_progress:
                if notice_progress['is_completed']:
                    timeline.append({
                        'status': 'notice_completed',
                        'label': 'Notice Period Completed',
                        'date': self.last_working_date,
                        'completed': True,
                        'active': False,
                        'icon': 'fas fa-calendar-check',
                        'progress': notice_progress
                    })
                else:
                    timeline.append({
                        'status': 'serving_notice',
                        'label': f'Serving Notice Period ({notice_progress["days_remaining"]} days remaining)',
                        'date': self.resignation_date,
                        'completed': False,
                        'active': True,
                        'icon': 'fas fa-user-clock',
                        'progress': notice_progress
                    })
            
            # Step 5: Exit Process
            exit_status = self.get_exit_process_status()
            if exit_status['checklist_progress'] == 100 and exit_status['no_due_certificate'] and exit_status['exit_interview']:
                timeline.append({
                    'status': 'completed',
                    'label': 'Exit Process Completed',
                    'date': self.last_working_date,
                    'completed': True,
                    'active': False,
                    'icon': 'fas fa-flag-checkered'
                })
            else:
                timeline.append({
                    'status': 'exit_process',
                    'label': f'Exit Process ({exit_status["checklist_completed"]}/{exit_status["checklist_total"]} tasks)',
                    'date': None,
                    'completed': False,
                    'active': True,
                    'icon': 'fas fa-tasks',
                    'progress': exit_status
                })
        
        elif self.status == 'rejected':
            timeline.append({
                'status': 'rejected',
                'label': 'Resignation Rejected',
                'date': self.updated_at.date(),
                'completed': True,
                'active': False,
                'icon': 'fas fa-times-circle'
            })
        
        elif self.status == 'withdrawn':
            withdrawal_date = self.withdrawal_requested_at.date() if self.withdrawal_requested_at else self.updated_at.date()
            timeline.append({
                'status': 'withdrawn',
                'label': 'Resignation Withdrawn',
                'date': withdrawal_date,
                'completed': True,
                'active': False,
                'icon': 'fas fa-undo'
            })
        
        return timeline

class ResignationChecklist(models.Model):
    resignation = models.ForeignKey(Resignation, on_delete=models.CASCADE)
    task_name = models.CharField(max_length=200)
    department = models.CharField(max_length=100)
    assigned_to = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True)
    due_date = models.DateField()
    completed = models.BooleanField(default=False)
    completed_date = models.DateField(null=True, blank=True)
    remarks = models.TextField(blank=True, null=True)
    
    class Meta:
        db_table = 'resignation_checklist'

class ResignationDocument(models.Model):
    resignation = models.ForeignKey(Resignation, on_delete=models.CASCADE)
    document_type = models.CharField(max_length=100)
    document_file = models.FileField(upload_to='resignation_documents/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'resignation_documents'

class ExitInterview(models.Model):
    resignation = models.OneToOneField(Resignation, on_delete=models.CASCADE)
   
    # Interview details
    interview_date = models.DateField(null=True, blank=True)
    conducted_by = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name='exit_interviews_conducted')
   
    # Interview questions - Reasons for leaving
    reason_for_leaving = models.TextField(blank=True, null=True)
    concerns_shared_prior = models.TextField(blank=True, null=True)
    single_event_responsible = models.TextField(blank=True, null=True)
    new_company_offer = models.TextField(blank=True, null=True)
   
    # Company feedback
    valued_about_company = models.TextField(blank=True, null=True)
    disliked_about_company = models.TextField(blank=True, null=True)
   
    # Management feedback
    relationship_with_manager = models.TextField(blank=True, null=True)
    supervisor_improvement = models.TextField(blank=True, null=True)
   
    # Job feedback
    liked_about_job = models.TextField(blank=True, null=True)
    disliked_about_job = models.TextField(blank=True, null=True)
    job_improvement_suggestions = models.TextField(blank=True, null=True)
   
    # Resources and support
    resources_support = models.TextField(blank=True, null=True)
    employee_morale = models.TextField(blank=True, null=True)
   
    # Performance and goals
    clear_goals = models.TextField(blank=True, null=True)
    performance_feedback = models.TextField(blank=True, null=True)
   
    # Company commitment
    quality_commitment = models.TextField(blank=True, null=True)
    career_development = models.TextField(blank=True, null=True)
   
    # Recommendations
    workplace_recommendations = models.TextField(blank=True, null=True)
    policies_fairness = models.TextField(blank=True, null=True)
   
    # Success qualities
    success_qualities = models.TextField(blank=True, null=True)
    replacement_qualities = models.TextField(blank=True, null=True)
   
    # Compensation and benefits
    compensation_feedback = models.TextField(blank=True, null=True)
   
    # Future considerations
    future_considerations = models.TextField(blank=True, null=True)
    recommend_company = models.TextField(blank=True, null=True)
   
    # Additional comments
    additional_comments = models.TextField(blank=True, null=True)
   
    # Digital signatures
    employee_signature = models.TextField(blank=True, null=True)
    employee_signed_at = models.DateTimeField(null=True, blank=True)
    hr_signature = models.TextField(blank=True, null=True)
    hr_signed_at = models.DateTimeField(null=True, blank=True)
   
    # Status
    is_completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
   
    class Meta:
        db_table = 'resignation_exit_interview'
   
    def __str__(self):
        return f"Exit Interview - {self.resignation.employee.employee_id}"

class NoDueCertificate(models.Model):
    SETTLEMENT_MODES = [
        ('online', 'Online Transfer/NEFT'),
        ('cheque', 'Cheque'),
        ('cash', 'Cash'),
    ]
    
    resignation = models.OneToOneField(Resignation, on_delete=models.CASCADE)
    
    # Employee acceptance
    employee_signature = models.TextField(blank=True, null=True, help_text="Digital signature of employee")
    employee_signed_at = models.DateTimeField(null=True, blank=True)
    employee_ip_address = models.CharField(max_length=100, blank=True, null=True)
    
    # HR approval
    hr_signature = models.TextField(blank=True, null=True, help_text="Digital signature of HR")
    hr_signed_at = models.DateTimeField(null=True, blank=True)
    hr_approved_by = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name='no_due_certificates_approved')
    
    # Certificate details
    certificate_number = models.CharField(max_length=100, unique=True, blank=True, null=True)
    generated_date = models.DateField(auto_now_add=True)
    is_completed = models.BooleanField(default=False)
    
    # Settlement details
    final_settlement_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    settlement_date = models.DateField(null=True, blank=True)
    settlement_mode = models.CharField(max_length=50, choices=SETTLEMENT_MODES, default='online')
    
    class Meta:
        db_table = 'resignation_no_due_certificate'
    
    def __str__(self):
        return f"No Due Certificate - {self.resignation.employee.employee_id}"
    
    def generate_certificate_number(self):
        if not self.certificate_number:
            self.certificate_number = f"NDC{self.resignation.employee.employee_id}{date.today().strftime('%Y%m%d')}"
        return self.certificate_number