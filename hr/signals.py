# hr/signals.py - CREATE THIS FILE

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from hr.models import Employee
from leave.services import AutoLeaveBalanceService
from datetime import date
import logging

logger = logging.getLogger(__name__)

@receiver(post_save, sender=Employee)
def create_employee_leave_balance(sender, instance, created, **kwargs):
    """
    Automatically create leave balance when a new employee is created
    """
    if created:
        try:
            # Initialize leave balances for new employee
            created_balances = AutoLeaveBalanceService.initialize_employee_leave_balance(instance)
            logger.info(
                f"Leave balances created for employee {instance.employee_id}: {created_balances}"
            )
        except Exception as e:
            logger.error(
                f"Error creating leave balance for employee {instance.employee_id}: {str(e)}"
            )

@receiver(pre_save, sender=Employee)
def check_probation_end(sender, instance, **kwargs):
    """
    Check if probation is ending and update leave balances accordingly
    """
    if instance.pk:  # Only for existing employees
        try:
            old_instance = Employee.objects.get(pk=instance.pk)
            
            # Check if probation_end_date was updated or if probation just ended
            if old_instance.probation_end_date != instance.probation_end_date:
                # Check if probation is now over
                if instance.probation_end_date and instance.probation_end_date <= date.today():
                    # Probation ended - update leave balances
                    AutoLeaveBalanceService.update_leave_balance_on_probation_end(instance)
                    logger.info(
                        f"Leave balances updated for employee {instance.employee_id} - Probation ended"
                    )
        except Employee.DoesNotExist:
            pass  # New employee
        except Exception as e:
            logger.error(
                f"Error checking probation end for employee {instance.employee_id}: {str(e)}"
            )