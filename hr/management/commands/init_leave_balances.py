from django.core.management.base import BaseCommand
from django.db import transaction
from hr.models import Employee
from leave.models import LeaveBalance
from leave.services import AutoLeaveBalanceService, CarryForwardService, DailyProbationService
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
            '--daily-probation-check',
            action='store_true',
            help='Run daily probation check for employees whose probation ended',
        )
        parser.add_argument(
            '--year',
            type=int,
            help='Process for specific year (default: current year)',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Run all services: carry forward, daily probation check, and monthly accrual',
        )


    def handle(self, *args, **options):
        force = options.get('force', False)
        process_carry_forward = options.get('carry_forward', False)
        run_monthly_accrual = options.get('monthly_accrual', False)
        run_daily_probation = options.get('daily_probation_check', False)
        run_all = options.get('all', False)
        year = options.get('year')
        
        # Default to current year if not specified
        if year is None:
            year = date.today().year
        
         # If --all flag is used, run all services
        if run_all:
            process_carry_forward = True
            run_daily_probation = True
            run_monthly_accrual = True

        # STEP 1: Daily Probation Check (should run first to catch recent probation ends)
        if run_daily_probation:
            self.stdout.write('\n' + '='*60)
            self.stdout.write(self.style.SUCCESS('STEP 1: Daily Probation Check'))
            self.stdout.write('='*60)
            
            try:
                count = DailyProbationService.daily_probation_check()
                if count > 0:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'✓ Daily probation check completed: {count} employees granted leave accrual after probation ended'
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            '⚠ No employees found whose probation ended recently'
                        )
                    )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f'✗ Daily probation check failed: {str(e)}'
                    )
                )
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
        
         # STEP 4: Monthly Leave Accrual
        if run_monthly_accrual:
            self.stdout.write('\n' + '='*60)
            self.stdout.write(self.style.SUCCESS('STEP 4: Running Monthly Leave Accrual'))
            self.stdout.write('='*60)

            try:
                count = AutoLeaveBalanceService.monthly_accrual_cron()
                if count > 0:
                    self.stdout.write(self.style.SUCCESS(f'✓ Monthly accrual completed for {count} employees'))
                else:
                    self.stdout.write(self.style.WARNING('⚠ No employees eligible for monthly accrual (may be on probation)'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'✗ Monthly accrual failed: {str(e)}'))
                
        # Print summary
        # self.stdout.write('\n' + '='*60)
        # self.stdout.write(self.style.SUCCESS(f'Initialization Complete'))
        # self.stdout.write('='*60)
        # self.stdout.write(f'Total Employees: {total_count}')
        # self.stdout.write(self.style.SUCCESS(f'Successfully Initialized: {success_count}'))
        # if error_count > 0:
        #     self.stdout.write(self.style.ERROR(f'Errors: {error_count}'))
        # self.stdout.write('='*60)
        
        # # STEP 3: Monthly Leave Accrual
        # if options.get('monthly_accrual'):
        #     self.stdout.write('\n' + '='*60)
        #     self.stdout.write(self.style.SUCCESS('STEP 3: Running Monthly Leave Accrual'))
        #     self.stdout.write('='*60)

        #     try:
        #         count = AutoLeaveBalanceService.monthly_accrual_cron()
        #         self.stdout.write(self.style.SUCCESS(f'✓ Monthly accrual completed for {count} employees'))
        #     except Exception as e:
        #         self.stdout.write(self.style.ERROR(f'✗ Monthly accrual failed: {str(e)}'))
        
        
         # Print final summary
        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS(f'PROCESSING COMPLETE'))
        self.stdout.write('='*60)
        self.stdout.write(f'Total Employees: {total_count}')
        self.stdout.write(self.style.SUCCESS(f'Successfully Initialized: {success_count}'))
        if error_count > 0:
            self.stdout.write(self.style.ERROR(f'Errors: {error_count}'))
        
        # Summary of services run
        services_run = []
        if run_daily_probation:
            services_run.append('Daily Probation Check')
        if process_carry_forward:
            services_run.append('Carry Forward')
        if run_monthly_accrual:
            services_run.append('Monthly Accrual')
        
        if services_run:
            self.stdout.write(f'Services Executed: {", ".join(services_run)}')
        
        self.stdout.write('='*60)

    def print_usage_examples(self):
        """Print usage examples for the command"""
        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS('USAGE EXAMPLES'))
        self.stdout.write('='*60)
        self.stdout.write('1. Initialize leave balances only:')
        self.stdout.write('   python manage.py initialize_leave_balances')
        self.stdout.write('')
        self.stdout.write('2. Initialize with carry forward from previous year:')
        self.stdout.write('   python manage.py initialize_leave_balances --carry-forward')
        self.stdout.write('')
        self.stdout.write('3. Run daily probation check only:')
        self.stdout.write('   python manage.py initialize_leave_balances --daily-probation-check')
        self.stdout.write('')
        self.stdout.write('4. Run monthly accrual only:')
        self.stdout.write('   python manage.py initialize_leave_balances --monthly-accrual')
        self.stdout.write('')
        self.stdout.write('5. Run all services:')
        self.stdout.write('   python manage.py initialize_leave_balances --all')
        self.stdout.write('')
        self.stdout.write('6. Force recreate all balances:')
        self.stdout.write('   python manage.py initialize_leave_balances --force --all')
        self.stdout.write('')
        self.stdout.write('7. Process for specific year:')
        self.stdout.write('   python manage.py initialize_leave_balances --year 2024 --all')
        self.stdout.write('='*60)