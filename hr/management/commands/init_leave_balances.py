from django.core.management.base import BaseCommand
from django.db import transaction
from hr.models import Employee
from leave.models import LeaveBalance
from leave.services import AutoLeaveBalanceService, CarryForwardService
from datetime import date


class Command(BaseCommand):
    help = 'Initialize leave balances for all existing employees'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force recreation of leave balances even if they exist',
        )
        parser.add_argument(
            '--carry-forward',
            action='store_true',
            help='Process carry forward from previous year',
        )
        parser.add_argument(
            '--monthly-accrual',
            action='store_true',
            help='Run monthly leave accrual (1.5 days for eligible employees)',
        )
        parser.add_argument(
            '--year',
            type=int,
            help='Process for specific year (default: current year)',
        )


    def handle(self, *args, **options):
        force = options.get('force', False)
        process_carry_forward = options.get('carry_forward', False)
        year = options.get('year')
        
        # Default to current year if not specified
        if year is None:
            year = date.today().year
        
        # Process carry forward first if requested
        if process_carry_forward:
            self.stdout.write('\n' + '='*60)
            self.stdout.write(self.style.SUCCESS('STEP 1: Processing Carry Forward'))
            self.stdout.write('='*60)
            
            prev_year = year - 1
            summary = CarryForwardService.get_carry_forward_summary(prev_year)
            
            if summary:
                total_carry_forward = sum(emp['carry_forward'] for emp in summary)
                total_forfeited = sum(emp['forfeited'] for emp in summary)
                
                self.stdout.write(
                    f'\n📊 Carry Forward Summary ({prev_year} → {year}):'
                )
                self.stdout.write(f'  • {len(summary)} employees with remaining leave')
                self.stdout.write(f'  • {total_carry_forward:.1f} days will be carried forward')
                if total_forfeited > 0:
                    self.stdout.write(
                        self.style.WARNING(
                            f'  • {total_forfeited:.1f} days will be forfeited (>12 day limit)'
                        )
                    )
                
                # Process carry forward
                count = CarryForwardService.process_year_end_carry_forward(prev_year)
                self.stdout.write(
                    self.style.SUCCESS(
                        f'\n✓ Carry forward processed for {count} employees'
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f'No carry forward data found for {prev_year}'
                    )
                )
        
        # Initialize leave balances
        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS(
            f'STEP 2: Initializing Leave Balances for {year}'
        ))
        self.stdout.write('='*60)
        
        employees = Employee.objects.filter(status='active')
        total_count = employees.count()
        
        self.stdout.write(
            self.style.SUCCESS(f'\nFound {total_count} active employees')
        )
        
        success_count = 0
        error_count = 0
        
        for employee in employees:
            try:
                # If force flag is set, delete existing balances first
                if force:
                    deleted_count = LeaveBalance.objects.filter(
                        employee=employee,
                        year=year
                    ).delete()[0]
                    if deleted_count > 0:
                        self.stdout.write(
                            self.style.WARNING(
                                f'  Deleted {deleted_count} existing balances for {employee.employee_id}'
                            )
                        )
                
                created_balances = AutoLeaveBalanceService.initialize_employee_leave_balance(
                    employee
                )
                
                if created_balances:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'✓ {employee.employee_id} - {employee.first_name} {employee.last_name}: '
                            f'Created {len(created_balances)} leave types'
                        )
                    )
                    success_count += 1
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f'⚠ {employee.employee_id} - {employee.first_name} {employee.last_name}: '
                            f'Already has leave balances'
                        )
                    )
                
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f'✗ {employee.employee_id} - {employee.first_name} {employee.last_name}: '
                        f'Error - {str(e)}'
                    )
                )
                error_count += 1
        
        # Print summary
        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS(f'Initialization Complete'))
        self.stdout.write('='*60)
        self.stdout.write(f'Total Employees: {total_count}')
        self.stdout.write(self.style.SUCCESS(f'Successfully Initialized: {success_count}'))
        if error_count > 0:
            self.stdout.write(self.style.ERROR(f'Errors: {error_count}'))
        self.stdout.write('='*60)
        
        # STEP 3: Monthly Leave Accrual
        if options.get('monthly_accrual'):
            self.stdout.write('\n' + '='*60)
            self.stdout.write(self.style.SUCCESS('STEP 3: Running Monthly Leave Accrual'))
            self.stdout.write('='*60)

            try:
                count = AutoLeaveBalanceService.monthly_accrual_cron()
                self.stdout.write(self.style.SUCCESS(f'✓ Monthly accrual completed for {count} employees'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'✗ Monthly accrual failed: {str(e)}'))