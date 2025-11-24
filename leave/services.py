# leave/services.py
from django.utils import timezone
from datetime import datetime, date, timedelta
from django.db import transaction
from dateutil.relativedelta import relativedelta
from decimal import Decimal
from .models import Leave, LeaveBalance, LeaveType, Holiday
from hr.models import Employee
import calendar

class LeaveAccrualService:
    """Handles monthly leave accrual of 1.5 days per month"""
    
    @staticmethod
    def calculate_monthly_accrual(employee, month, year):
        """Calculate monthly accrual of 1.5 days"""
        # Check probation period
        if hasattr(employee, 'probation_end_date') and employee.probation_end_date:
            if employee.probation_end_date > timezone.now().date():
                return Decimal('0')  # No leave during probation
        
        # Check if employee has completed the month
        if employee.date_of_joining:
            joining_date = employee.date_of_joining
            # If joined after the 1st of the month, no accrual for that month
            if joining_date.day > 1 and joining_date.month == month and joining_date.year == year:
                return Decimal('0')
        
        return Decimal('1.5')  # Monthly accrual rate

    @staticmethod
    def process_monthly_accrual_for_all():
        """Process monthly accrual for all active employees"""
        today = timezone.now().date()
        current_month = today.month
        current_year = today.year
        
        # Only process on 1st of each month
        if today.day != 1:
            return
        
        active_employees = Employee.objects.filter(status='active')
        annual_leave_type, created = LeaveType.objects.get_or_create(
            name='Earned',
            defaults={'max_days': 18, 'is_active': True}
        )
        
        for employee in active_employees:
            accrual_amount = LeaveAccrualService.calculate_monthly_accrual(
                employee, current_month, current_year
            )
            
            if accrual_amount > 0:
                with transaction.atomic():
                    balance, created = LeaveBalance.objects.get_or_create(
                        employee=employee,
                        leave_type=annual_leave_type,
                        year=current_year,
                        defaults={
                            'total_leaves': accrual_amount,
                            'leaves_remaining': accrual_amount,
                            'leaves_taken': 0,
                            'carry_forward': 0
                        }
                    )
                    
                    if not created:
                        balance.total_leaves += accrual_amount
                        balance.leaves_remaining += accrual_amount
                        balance.save()

class OptionalLeaveService:
    """Manages optional leave rules (4 days/year, use only 2, lose remaining 2)"""
    
    @staticmethod
    def initialize_optional_leave(employee, year):
        """Initialize optional leave balance for the year"""
        optional_leave_type, created = LeaveType.objects.get_or_create(
            name='optional',
            defaults={'max_days': 4, 'is_active': True}
        )
        
        balance, created = LeaveBalance.objects.get_or_create(
            employee=employee,
            leave_type=optional_leave_type,
            year=year,
            defaults={
                'total_leaves': 4,
                'leaves_remaining': 4,
                'leaves_taken': 0,
                'carry_forward': 0
            }
        )
        return balance
    
    @staticmethod
    def can_use_optional_leave(employee, days_requested, year):
        """Check if employee can use optional leave"""
        try:
            optional_leave_type = LeaveType.objects.get(name='optional')
            balance = LeaveBalance.objects.get(
                employee=employee,
                leave_type=optional_leave_type,
                year=year
            )
            
            # Check if already used 2 days (max allowed)
            if balance.leaves_taken >= 2:
                return False, "Maximum 2 optional leaves allowed per year"
            
            # Check if requested days exceed remaining quota
            remaining_quota = 2 - balance.leaves_taken
            if days_requested > remaining_quota:
                return False, f"Can only use {remaining_quota} more optional leave days"
            
            # Check overall balance
            if days_requested > balance.leaves_remaining:
                return False, f"Insufficient optional leave balance. Available: {balance.leaves_remaining}"
            
            return True, "Can use optional leave"
            
        except (LeaveType.DoesNotExist, LeaveBalance.DoesNotExist):
            return False, "Optional leave balance not found"

# class CarryForwardService:
#     """Handles earned leave carry forward (max 12 days, rest LOST)"""
    
#     @staticmethod
#     def calculate_carry_forward(employee, current_year):
#         """Calculate carry forward from previous year"""
#         previous_year = current_year - 1
        
#         try:
#             annual_leave_type = LeaveType.objects.get(name='annual')
#             prev_balance = LeaveBalance.objects.get(
#                 employee=employee,
#                 leave_type=annual_leave_type,
#                 year=previous_year
#             )
            
#             # Calculate carry forward (max 12 days)
#             available_carry = prev_balance.leaves_remaining
#             carry_forward = min(available_carry, 12)
            
#             return carry_forward
            
#         except (LeaveType.DoesNotExist, LeaveBalance.DoesNotExist):
#             return Decimal('0')
    
#     @staticmethod
#     def process_carry_forward(employee, current_year):
#         """Process carry forward for new year"""
#         carry_forward = CarryForwardService.calculate_carry_forward(employee, current_year)
        
#         if carry_forward > 0:
#             annual_leave_type = LeaveType.objects.get(name='annual')
            
#             # Create or update current year balance with carry forward
#             balance, created = LeaveBalance.objects.get_or_create(
#                 employee=employee,
#                 leave_type=annual_leave_type,
#                 year=current_year,
#                 defaults={
#                     'total_leaves': carry_forward,
#                     'leaves_remaining': carry_forward,
#                     'leaves_taken': 0,
#                     'carry_forward': carry_forward
#                 }
#             )
            
#             if not created:
#                 balance.carry_forward = carry_forward
#                 balance.leaves_remaining += carry_forward
#                 balance.total_leaves += carry_forward
#                 balance.save()
        
#         return carry_forward

#---------------------

class ProbationService:
    """Service for probation-related logic"""
    
    @staticmethod
    def calculate_probation_end_date(employee):
        """Calculate probation end date using individual probation period"""
        if employee.date_of_joining and employee.probation_period_days:
            return employee.date_of_joining + timedelta(int(employee.probation_period_days))
        elif employee.date_of_joining:
            # Fallback to 90 days (3 months) if probation_period_days not set
            return employee.date_of_joining + timedelta(days=90)
        return None
    
    @staticmethod
    def is_on_probation(employee):
        """Check if employee is currently on probation"""
        if not employee.probation_end_date:
            # Calculate probation end date if not set
            probation_end = ProbationService.calculate_probation_end_date(employee)
            if probation_end:
                return date.today() <= probation_end
            return False
        
        return date.today() <= employee.probation_end_date
    
    @staticmethod
    def get_probation_message(employee):
        """Get probation status message"""
        if not ProbationService.is_on_probation(employee):
            return None
        
        end_date = employee.probation_end_date
        if not end_date:
            end_date = ProbationService.calculate_probation_end_date(employee)
        
        if end_date:
            days_remaining = (end_date - date.today()).days
            return f"Probation ends in {days_remaining} days ({end_date.strftime('%d %b %Y')})"
        
        return "You are currently on probation"
    
    @staticmethod
    def get_months_after_probation(employee):
        """Calculate how many months after probation the employee has completed"""
        probation_end_date = employee.probation_end_date
        
        if not probation_end_date:
            probation_end_date = ProbationService.calculate_probation_end_date(employee)
        
        if not probation_end_date:
            return 0
        
        # If still on probation, return 0
        if date.today() <= probation_end_date:
            return 0
        
        # Calculate months after probation ended
        current_date = date.today()
        months_after = (current_date.year - probation_end_date.year) * 12 + \
                      (current_date.month - probation_end_date.month)
        
        # If current day is before probation end day in the month, don't count current month
        if current_date.day < probation_end_date.day:
            months_after -= 1
        
        return max(0, months_after)
    
    
    
    
class CarryForwardService:
    """Service to handle annual leave carry forward"""
    
    MAX_CARRY_FORWARD = 12  # Maximum days that can be carried forward
    
    @staticmethod
    @transaction.atomic
    def process_year_end_carry_forward(year):
        """
        Process carry forward for all employees at year end
        Call this on December 31st or January 1st
        
        Args:
            year: The year that just ended (e.g., 2024 to carry forward to 2025)
        """
        from hr.models import Employee
        
        next_year = year + 1
        carried_forward_count = 0
        
        # Get Earned Leave type
        try:
            annual_leave = LeaveType.objects.get(
                is_active=True,
                accrual_rate=Decimal('1.5')
            )
        except LeaveType.DoesNotExist:
            return 0
        
        # Get all active employees
        employees = Employee.objects.filter(status='active')
        
        for employee in employees:
            try:
                # Get previous year balance
                prev_balance = LeaveBalance.objects.get(
                    employee=employee,
                    leave_type=annual_leave,
                    year=year
                )
                
                # Calculate carry forward (max 12 days)
                remaining = prev_balance.leaves_remaining
                carry_forward_amount = min(remaining, CarryForwardService.MAX_CARRY_FORWARD)
                
                if carry_forward_amount > 0:
                    # Create or update next year balance
                    next_balance, created = LeaveBalance.objects.get_or_create(
                        employee=employee,
                        leave_type=annual_leave,
                        year=next_year,
                        defaults={
                            'total_leaves': carry_forward_amount,
                            'leaves_taken': 0,
                            'leaves_remaining': carry_forward_amount,
                            'carry_forward': carry_forward_amount
                        }
                    )
                    
                    if not created:
                        # Update existing balance
                        next_balance.carry_forward = carry_forward_amount
                        next_balance.total_leaves += carry_forward_amount
                        next_balance.leaves_remaining += carry_forward_amount
                        next_balance.save()
                    
                    carried_forward_count += 1
                    
            except LeaveBalance.DoesNotExist:
                # No balance in previous year, skip
                continue
        
        return carried_forward_count
    
    @staticmethod
    def calculate_carry_forward_for_employee(employee, from_year):
        """
        Calculate carry forward amount for a specific employee
        
        Returns: carry_forward_amount (max 12 days)
        """
        try:
            annual_leave = LeaveType.objects.get(
                is_active=True,
                accrual_rate=Decimal('1.5')
            )
            
            prev_balance = LeaveBalance.objects.get(
                employee=employee,
                leave_type=annual_leave,
                year=from_year
            )
            
            # Calculate carry forward (max 12 days)
            remaining = prev_balance.leaves_remaining
            carry_forward = min(remaining, CarryForwardService.MAX_CARRY_FORWARD)
            
            return float(carry_forward)
            
        except (LeaveType.DoesNotExist, LeaveBalance.DoesNotExist):
            return 0.0
    
    @staticmethod
    def get_carry_forward_summary(year):
        """
        Get summary of carry forward for all employees
        Used for reporting
        
        Returns: List of dicts with employee carry forward info
        """
        from hr.models import Employee
        
        summary = []
        
        try:
            annual_leave = LeaveType.objects.get(
                is_active=True,
                accrual_rate=Decimal('1.5')
            )
        except LeaveType.DoesNotExist:
            return summary
        
        employees = Employee.objects.filter(status='active')
        
        for employee in employees:
            try:
                prev_balance = LeaveBalance.objects.get(
                    employee=employee,
                    leave_type=annual_leave,
                    year=year
                )
                
                remaining = prev_balance.leaves_remaining
                carry_forward = min(remaining, CarryForwardService.MAX_CARRY_FORWARD)
                forfeited = max(0, remaining - CarryForwardService.MAX_CARRY_FORWARD)
                
                summary.append({
                    'employee_id': employee.employee_id,
                    'employee_name': f"{employee.first_name} {employee.last_name}",
                    'total_allocated': prev_balance.total_leaves,
                    'leaves_taken': prev_balance.leaves_taken,
                    'leaves_remaining': remaining,
                    'carry_forward': carry_forward,
                    'forfeited': forfeited
                })
                
            except LeaveBalance.DoesNotExist:
                continue
        
        return summary

    
class AutoLeaveBalanceService:
    """
    Service to automatically create and update leave balances for employees
    """
    
    @staticmethod
    def initialize_employee_leave_balance(employee):
        """
        Initialize leave balance when a new employee is created
        For current year, includes carry forward from previous year if applicable
        """
        current_year = date.today().year
        
        # Check if employee is on probation
        is_on_probation = ProbationService.is_on_probation(employee)
        
        created_balances = []
        
        # Get Earned Leave type
        try:
            annual_leave = LeaveType.objects.get(
                is_active=True,
                accrual_rate=Decimal('1.5')
            )
        except LeaveType.DoesNotExist:
            annual_leave = None
        
        # Get Unpaid Leave type
        try:
            unpaid_leave = LeaveType.objects.get(
                is_active=True,
                name__icontains='unpaid'
            )
        except LeaveType.DoesNotExist:
            unpaid_leave = None
        
        # Create Earned Leave Balance
        if annual_leave:
            balance, created = LeaveBalance.objects.get_or_create(
                employee=employee,
                leave_type=annual_leave,
                year=current_year,
                defaults={
                    'total_leaves': 0,
                    'leaves_taken': 0,
                    'leaves_remaining': 0,
                    'carry_forward': 0
                }
            )
            
            if created:
                # Calculate carry forward from previous year (if employee joined before current year)
                carry_forward_amount = 0
                if employee.date_of_joining.year < current_year:
                    carry_forward_amount = CarryForwardService.calculate_carry_forward_for_employee(
                        employee, 
                        current_year - 1
                    )
                
                if is_on_probation:
                    # Probation: 0 accrued, but can have carry forward
                    balance.carry_forward = carry_forward_amount
                    balance.total_leaves = carry_forward_amount
                    balance.leaves_remaining = carry_forward_amount
                else:
                    # Not on probation: Calculate accrued + carry forward
                    months_after_probation = ProbationService.get_months_after_probation(employee)
                    
                    # Only count months in current year
                    if employee.date_of_joining.year < current_year:
                        # Joined in previous year - count all months of current year after probation
                        current_month = date.today().month
                        months_in_current_year = current_month
                    else:
                        # Joined in current year - count months from probation end
                        months_in_current_year = months_after_probation
                    
                    accrued_leaves = float(Decimal(str(months_in_current_year)) * annual_leave.accrual_rate)
                    
                    balance.carry_forward = carry_forward_amount
                    balance.total_leaves = accrued_leaves + carry_forward_amount
                    balance.leaves_remaining = accrued_leaves + carry_forward_amount
                
                balance.save()
                created_balances.append(annual_leave.name)
                
                
                
                
        # ========== CREATE OPTIONAL LEAVE BALANCE ==========
        # Only create optional leave if employee is NOT on probation
        if not is_on_probation:
            # Get or Create Optional Leave type
            optional_leave_type, created = LeaveType.objects.get_or_create(
                name='optional',
                defaults={
                    'max_days': 4, 
                    'is_active': True,
                    'is_optional': True
                }
            )
            
            balance, created = LeaveBalance.objects.get_or_create(
                employee=employee,
                leave_type=optional_leave_type,
                year=current_year,
                defaults={
                    'total_leaves': 2,  # Only 2 days can be used out of 4 allocated
                    'leaves_taken': 0,
                    'leaves_remaining': 2,
                    'carry_forward': 0
                }
            )
            
            if created:
                created_balances.append(optional_leave_type.name)        
                
                
                
                
        
        # Create Unpaid Leave Balance
        if unpaid_leave:
            balance, created = LeaveBalance.objects.get_or_create(
                employee=employee,
                leave_type=unpaid_leave,
                year=current_year,
                defaults={
                    'total_leaves': 0,
                    'leaves_taken': 0,
                    'leaves_remaining': 0,
                    'carry_forward': 0
                }
            )
            
            if created:
                created_balances.append(unpaid_leave.name)
        
        return created_balances
    
    @staticmethod
  
    def update_leave_balance_on_probation_end(employee):
        """
        Update leave balance when probation ends
        Grant annual leave accrual and optional leave after probation ends
        """
        current_year = date.today().year
        
        # Get Earned Leave type
        try:
            annual_leave = LeaveType.objects.get(
                is_active=True,
                accrual_rate=Decimal('1.5')
            )
        except LeaveType.DoesNotExist:
            annual_leave = None
        
        # Get Optional Leave type
        try:
            optional_leave = LeaveType.objects.get(
                is_active=True,
                is_optional=True
            )
        except LeaveType.DoesNotExist:
            optional_leave = None
        
        # Update Earned Leave Balance
        if annual_leave:
            balance, created = LeaveBalance.objects.get_or_create(
                employee=employee,
                leave_type=annual_leave,
                year=current_year,
                defaults={
                    'total_leaves': 0,
                    'leaves_taken': 0,
                    'leaves_remaining': 0,
                    'carry_forward': 0
                }
            )
            
            # Calculate months after probation end
            months_after_probation = ProbationService.get_months_after_probation(employee)
            
            # Calculate accrued leaves (1.5 days per month after probation)
            additional_leaves = float(Decimal(str(months_after_probation)) * annual_leave.accrual_rate)
            balance.total_leaves = additional_leaves + balance.carry_forward
            balance.leaves_remaining = additional_leaves + balance.carry_forward - balance.leaves_taken
            balance.save()
        
        # Grant Optional Leave (2 days) - ONLY ADDED THIS PART
        if optional_leave:
            balance, created = LeaveBalance.objects.get_or_create(
                employee=employee,
                leave_type=optional_leave,
                year=current_year,
                defaults={
                    'total_leaves': 2,
                    'leaves_taken': 0,
                    'leaves_remaining': 2,
                    'carry_forward': 0
                }
            )
            
            if not created:
                # Update existing balance to 2 days
                balance.total_leaves = 2
                balance.leaves_remaining = 2 - balance.leaves_taken
                balance.save()
        
        return True
    
    @staticmethod
    @transaction.atomic
    def monthly_accrual_cron():
        """
        Monthly cron job to accrue leaves for all employees
        Run this on 1st of every month
        
        Only accrue Earned Leave (1.5 days/month) for non-probation employees
        """
        from hr.models import Employee
        
        current_year = date.today().year
        
        # Get all active employees not on probation
        employees = Employee.objects.filter(status='active')
        
        # Get Earned Leave type
        try:
            annual_leave = LeaveType.objects.get(
                is_active=True,
                accrual_rate=Decimal('1.5')
            )
        except LeaveType.DoesNotExist:
            return 0
        
        updated_count = 0
        
        for employee in employees:
            # Check probation status
            is_on_probation = ProbationService.is_on_probation(employee)
            
            if is_on_probation:
                continue  # Skip employees on probation
            
            # Get or create balance for annual leave
            balance, created = LeaveBalance.objects.get_or_create(
                employee=employee,
                leave_type=annual_leave,
                year=current_year,
                defaults={
                    'total_leaves': 0,
                    'leaves_taken': 0,
                    'leaves_remaining': 0,
                    'carry_forward': 0
                }
            )
            
            # Add monthly accrual (1.5 days)
            accrual_amount = annual_leave.accrual_rate
            balance.total_leaves = float(Decimal(str(balance.total_leaves)) + accrual_amount)
            balance.leaves_remaining = float(Decimal(str(balance.leaves_remaining)) + accrual_amount)
            balance.save()
            
            updated_count += 1
        
        return updated_count
    
    @staticmethod
    def ensure_unpaid_leave_balance(employee):
        """
        Ensure employee has unpaid leave balance
        Unpaid leave balance starts at 0 and increases when taken
        """
        current_year = date.today().year
        
        # Get Unpaid Leave type
        try:
            unpaid_leave = LeaveType.objects.get(
                is_active=True,
                name__icontains='unpaid'
            )
        except LeaveType.DoesNotExist:
            return None
        
        # Get or create unpaid leave balance - STARTS AT 0
        balance, created = LeaveBalance.objects.get_or_create(
            employee=employee,
            leave_type=unpaid_leave,
            year=current_year,
            defaults={
                'total_leaves': 0,  # Starts at 0
                'leaves_taken': 0,
                'leaves_remaining': 0,  # Starts at 0
                'carry_forward': 0
            }
        )
        
        return balance
    
    @staticmethod
    def record_unpaid_leave(employee, days_taken):
        """
        Record unpaid leave when taken
        This increases the unpaid leave balance (as a negative/tracking record)
        """
        current_year = date.today().year
        
        # Get Unpaid Leave type
        try:
            unpaid_leave = LeaveType.objects.get(
                is_active=True,
                name__icontains='unpaid'
            )
        except LeaveType.DoesNotExist:
            return None
        
        # Get or create unpaid leave balance
        balance, created = LeaveBalance.objects.get_or_create(
            employee=employee,
            leave_type=unpaid_leave,
            year=current_year,
            defaults={
                'total_leaves': 0,
                'leaves_taken': 0,
                'leaves_remaining': 0,
                'carry_forward': 0
            }
        )
        
        # Increase leaves_taken (this tracks how much unpaid leave was taken)
        balance.leaves_taken = float(Decimal(str(balance.leaves_taken)) + Decimal(str(days_taken)))
        balance.save()
        
        return balance
    
    @staticmethod
    def get_or_create_balance(employee, leave_type, year):
        """
        Helper to get or create balance with smart defaults
        Only for Earned Leave and Unpaid Leave
        """
        balance, created = LeaveBalance.objects.get_or_create(
            employee=employee,
            leave_type=leave_type,
            year=year,
            defaults={
                'total_leaves': 0,
                'leaves_taken': 0,
                'leaves_remaining': 0,
                'carry_forward': 0
            }
        )
        
        if created:
            # Initialize with proper values
            is_on_probation = ProbationService.is_on_probation(employee)
            
            # Check if this is unpaid leave
            if 'unpaid' in leave_type.name.lower():
                # Unpaid leave starts at 0
                balance.total_leaves = 0
                balance.leaves_remaining = 0
            elif not is_on_probation and leave_type.accrual_rate > 0:
                # Earned leave - calculate accrued leaves AFTER probation
                probation_end_date = employee.probation_end_date
                current_date = date.today()
                
                # If probation end date exists and is in the past
                if probation_end_date and probation_end_date < current_date:
                    months_after_probation = (current_date.year - probation_end_date.year) * 12 + \
                                            (current_date.month - probation_end_date.month)
                    
                    if current_date.day < probation_end_date.day:
                        months_after_probation -= 1
                    
                    months_after_probation = max(0, months_after_probation)
                    
                    accrued = float(Decimal(str(months_after_probation)) * leave_type.accrual_rate)
                    balance.total_leaves = accrued
                    balance.leaves_remaining = accrued
                else:
                    # Still on probation or no probation end date
                    balance.total_leaves = 0
                    balance.leaves_remaining = 0
            
            balance.save()
        
        return balance
#-----------------------
# class ProbationService:
#     """Service for probation-related logic"""
    
#     @staticmethod
#     def is_on_probation(employee):
#         """Check if employee is currently on probation"""
#         if not employee.probation_end_date:
#             # If no probation end date, check if within 3 months of joining
#             if employee.date_of_joining:
#                 probation_end = employee.date_of_joining + relativedelta(months=3)
#                 return date.today() <= probation_end
#             return False
#         return date.today() <= employee.probation_end_date
    
#     @staticmethod
#     def get_probation_message(employee):
#         """Get probation status message"""
#         if not ProbationService.is_on_probation(employee):
#             return None
        
#         end_date = employee.probation_end_date
#         if not end_date and employee.date_of_joining:
#             end_date = employee.date_of_joining + relativedelta(months=3)
        
#         if end_date:
#             days_remaining = (end_date - date.today()).days
#             return f"Probation ends in {days_remaining} days ({end_date.strftime('%d %b %Y')})"
        
#         return "You are currently on probation"

class CompOffService:
    """Handles compensatory off for working on holidays"""
    
    @staticmethod
    def earn_comp_off(employee, work_date, reason=""):
        """Earn comp off for working on holiday"""
        # Check if it's actually a holiday for employee's region
        is_holiday = Holiday.objects.filter(
            date=work_date,
            region__name=employee.location
        ).exists()
        
        if not is_holiday:
            return False, "Not a holiday in your region"
        
        # Check if comp off already earned for this date
        existing_comp_off = Leave.objects.filter(
            employee=employee,
            start_date=work_date,
            leave_type__name='comp_off',
            status='approved'
        ).exists()
        
        if existing_comp_off:
            return False, "Comp off already earned for this date"
        
        # Get or create comp off leave type
        comp_off_type, created = LeaveType.objects.get_or_create(
            name='comp_off',
            defaults={'max_days': 30, 'is_active': True}
        )
        
        # Create comp off balance entry
        balance, created = LeaveBalance.objects.get_or_create(
            employee=employee,
            leave_type=comp_off_type,
            year=work_date.year,
            defaults={
                'total_leaves': 1,
                'leaves_remaining': 1,
                'leaves_taken': 0,
                'carry_forward': 0
            }
        )
        
        if not created:
            balance.total_leaves += 1
            balance.leaves_remaining += 1
            balance.save()
        
        # Create comp off leave record
        comp_off_leave = Leave.objects.create(
            employee=employee,
            leave_type=comp_off_type,
            start_date=work_date,
            end_date=work_date,
            days_requested=1,
            reason=f"Comp off for working on holiday: {reason}",
            status='approved',
            applied_date=timezone.now()
        )
        
        return True, "Comp off earned successfully"

class YearEndService:
    """Handles year-end processing and automatic loss of excess leaves"""
    
    @staticmethod
    def process_year_end():
        """Process year-end for all employees"""
        current_year = timezone.now().year
        next_year = current_year + 1
        
        employees = Employee.objects.filter(status='active')
        
        for employee in employees:
            YearEndService.process_employee_year_end(employee, current_year, next_year)
    
    @staticmethod
    def process_employee_year_end(employee, current_year, next_year):
        """Process year-end for a single employee"""
        with transaction.atomic():
            # Process annual leave carry forward
            carry_forward = CarryForwardService.process_carry_forward(employee, next_year)
            
            # Reset optional leaves (lose remaining - max use 2 out of 4)
            try:
                optional_leave_type = LeaveType.objects.get(name='optional')
                optional_balance = LeaveBalance.objects.get(
                    employee=employee,
                    leave_type=optional_leave_type,
                    year=current_year
                )
                # Optional leaves don't carry forward - they're lost
                optional_balance.leaves_remaining = 0
                optional_balance.save()
                
                # Initialize next year's optional leaves
                OptionalLeaveService.initialize_optional_leave(employee, next_year)
                
            except (LeaveType.DoesNotExist, LeaveBalance.DoesNotExist):
                # Initialize if not exists
                OptionalLeaveService.initialize_optional_leave(employee, next_year)
            
            # Reset sick leaves (typically don't carry forward)
            try:
                sick_leave_type = LeaveType.objects.get(name='sick')
                sick_balance = LeaveBalance.objects.get(
                    employee=employee,
                    leave_type=sick_leave_type,
                    year=current_year
                )
                sick_balance.leaves_remaining = 0
                sick_balance.save()
            except (LeaveType.DoesNotExist, LeaveBalance.DoesNotExist):
                pass
            
            # Reset comp off (typically don't carry forward)
            try:
                comp_off_type = LeaveType.objects.get(name='comp_off')
                comp_off_balance = LeaveBalance.objects.get(
                    employee=employee,
                    leave_type=comp_off_type,
                    year=current_year
                )
                comp_off_balance.leaves_remaining = 0
                comp_off_balance.save()
            except (LeaveType.DoesNotExist, LeaveBalance.DoesNotExist):
                pass

class LeaveValidationService:
    """Centralized leave validation service"""
    
    @staticmethod
    def validate_leave_application(employee, leave_type, start_date, end_date, days_requested):
        """
        Validate leave application against business rules
        Returns: (is_valid, errors, warnings)
        """
        errors = []
        warnings = []
        
        # Check if unpaid leave - skip balance validation
        is_unpaid = 'unpaid' in leave_type.name.lower()
        
        if is_unpaid:
            # Unpaid leave is always valid (no balance check needed)
            return (True, errors, warnings)
        
        # For paid leaves, check balance
        try:
            balance = LeaveBalance.objects.get(
                employee=employee,
                leave_type=leave_type,
                year=start_date.year
            )
            
            if balance.leaves_remaining < days_requested:
                errors.append(
                    f"Insufficient {leave_type.name} balance. "
                    f"Available: {balance.leaves_remaining}, Requested: {days_requested}"
                )
        except LeaveBalance.DoesNotExist:
            errors.append(f"No leave balance found for {leave_type.name}")
        
        # Check if employee is on probation
       
        is_on_probation = ProbationService.is_on_probation(employee)
        
        if is_on_probation:
            warnings.append("Employee is on probation. Any approved leave will be unpaid.")
        
        # Validate date range
        if start_date > end_date:
            errors.append("Start date cannot be after end date")
        
        if start_date < date.today():
            errors.append("Cannot apply for leave in the past")
        
        is_valid = len(errors) == 0
        return (is_valid, errors, warnings)
    

    @staticmethod
    def deduct_leave_balance(employee, leave_type, days, year):
        """Deduct leave balance after approval"""
        try:
            balance = LeaveBalance.objects.get(
                employee=employee,
                leave_type=leave_type,
                year=year
            )
            # Convert days to Decimal to handle 0.5 properly
            days_decimal = Decimal(str(days))
            if balance.leaves_remaining >= days_decimal:
                balance.leaves_taken = Decimal(str(balance.leaves_taken)) + days_decimal
                balance.leaves_remaining = Decimal(str(balance.leaves_remaining)) - days_decimal
                balance.save()
                return True
            return False
            
        except LeaveBalance.DoesNotExist:
            return False
        
        
        
    @staticmethod
    def restore_leave_balance(employee, leave_type, days, year):
        """Restore leave balance when leave is rejected or status changed from approved"""
        try:
            balance = LeaveBalance.objects.get(
                employee=employee,
                leave_type=leave_type,
                year=year
            )
            
            # Convert days to Decimal to handle 0.5 properly
            days_decimal = Decimal(str(days))
            print(f"DEBUG: Restored days requested {days} days")
            # Restore the balance - reduce leaves_taken and increase leaves_remaining
            balance.leaves_taken = max(Decimal('0'), Decimal(str(balance.leaves_taken)) - days_decimal)
            balance.leaves_remaining = Decimal(str(balance.leaves_remaining)) + days_decimal
            
            balance.save()
            
            # Debug logging
            print(f"DEBUG: Restored {days} days for {employee.first_name} - {leave_type.name}")
            print(f"DEBUG: New balance - Taken: {balance.leaves_taken}, Remaining: {balance.leaves_remaining}")
            
            return True
            
        except LeaveBalance.DoesNotExist:
            print(f"ERROR: No balance found for {employee.first_name} - {leave_type.name}")
            return False
        except Exception as e:
            print(f"ERROR: Failed to restore balance: {str(e)}")
            return False

# Utility function to initialize leave balances for new employee
def initialize_employee_leave_balances(employee, year):
    """Initialize all leave balances for a new employee"""
    leave_types = LeaveType.objects.filter(is_active=True)
    
    for leave_type in leave_types:
        defaults = {
            'total_leaves': 0,
            'leaves_remaining': 0,
            'leaves_taken': 0,
            'carry_forward': 0
        }
        
        # Set initial values based on leave type
        if leave_type.name == 'Earned':
            # New employees start with 0 annual leaves (accrual starts next month)
            pass
        elif leave_type.name == 'optional':
            defaults['total_leaves'] = 4
            defaults['leaves_remaining'] = 4
        elif leave_type.name == 'sick':
            defaults['total_leaves'] = 12  # Example: 12 sick leaves per year
            defaults['leaves_remaining'] = 12
        elif leave_type.name == 'casual':
            defaults['total_leaves'] = 6   # Example: 6 casual leaves per year
            defaults['leaves_remaining'] = 6
        
        LeaveBalance.objects.get_or_create(
            employee=employee,
            leave_type=leave_type,
            year=year,
            defaults=defaults
        )