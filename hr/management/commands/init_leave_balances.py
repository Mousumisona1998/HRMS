from django.core.management.base import BaseCommand
from django.db import transaction
from hr.models import Employee
from leave.models import LeaveBalance
from leave.services import AutoLeaveBalanceService, CarryForwardService, DailyProbationService,CompOffService
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
            help='Process carry forward from previous year (will run anytime with this flag)',
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
        parser.add_argument(
            '--expire-compoff',
            action='store_true',
            help='Expire comp off that are older than 45 days',
        )

    def handle(self, *args, **options):
        force = options.get('force', False)
        process_carry_forward = options.get('carry_forward', False)
        run_monthly_accrual = options.get('monthly_accrual', False)
        run_daily_probation = options.get('daily_probation_check', False)
        expire_compoff = options.get('expire_compoff', False)
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
            expire_compoff = True

        step_counter = 1
        
        # STEP 1: Daily Probation Check
        if run_daily_probation:
            self.stdout.write('\n' + '='*60)
            self.stdout.write(self.style.SUCCESS(f'STEP {step_counter}: Daily Probation Check'))
            self.stdout.write('='*60)
            step_counter += 1
            
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

        # STEP 2: Expire Old Comp Off
        if expire_compoff:
            self.stdout.write('\n' + '='*60)
            self.stdout.write(self.style.SUCCESS(f'STEP {step_counter}: Expiring Old Comp Off'))
            self.stdout.write('='*60)
            step_counter += 1
            
            try:
                expired_count = CompOffService.expire_old_compoff()
                if expired_count > 0:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'✓ Expired {expired_count} comp off records older than 45 days'
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            '⚠ No comp off records to expire'
                        )
                    )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f'✗ Comp off expiration failed: {str(e)}'
                    )
                )

        # STEP 3: Process Carry Forward
        if process_carry_forward:
            self.stdout.write('\n' + '='*60)
            self.stdout.write(self.style.SUCCESS(f'STEP {step_counter}: Processing Carry Forward'))
            self.stdout.write('='*60)
            step_counter += 1
            
            try:
                # First, let's check what financial year we're in
                today = date.today()
                fy_start, fy_end = CarryForwardService.get_financial_year(today)
                
                self.stdout.write(f'Current financial year: {fy_start}-{fy_end}')
                self.stdout.write(f'Current date: {today.strftime("%d-%m-%Y")}')
                
                # Check if we should process carry forward
                # Normally it runs on April 1st, but with --carry-forward flag we force it
                if today.month == 4 and today.day == 1:
                    self.stdout.write('✅ Today is April 1st - processing financial year carry forward')
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            '⚠ Not April 1st, but processing carry forward due to --carry-forward flag'
                        )
                    )
                
                # Get summary for previous financial year
                prev_fy_start = fy_start - 1
                summary = CarryForwardService.get_carry_forward_summary(prev_fy_start)
                
                if summary:
                    total_carry_forward = sum(emp['carry_forward'] for emp in summary)
                    total_forfeited = sum(emp['forfeited'] for emp in summary)
                    
                    self.stdout.write(
                        f'\n📊 Carry Forward Summary for FY {prev_fy_start}-{prev_fy_start+1}:'
                    )
                    self.stdout.write(f'  • {len(summary)} employees with remaining leave')
                    self.stdout.write(f'  • {total_carry_forward:.1f} days will be carried forward')
                    if total_forfeited > 0:
                        self.stdout.write(
                            self.style.WARNING(
                                f'  • {total_forfeited:.1f} days will be forfeited (>12 day limit)'
                            )
                        )
                    
                    # Show first few employees
                    self.stdout.write('\nFirst 5 employees:')
                    for emp in summary[:5]:
                        self.stdout.write(f"  • {emp['employee_name']}: {emp['leaves_remaining']:.1f} remaining → "
                                        f"{emp['carry_forward']:.1f} carried forward, "
                                        f"{emp['forfeited']:.1f} forfeited")
                    
                    # Process carry forward
                    self.stdout.write('\n🔄 Processing carry forward...')
                    count = CarryForwardService.process_year_end_carry_forward()
                    
                    if count > 0:
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'✓ Carry forward processed for {count} employees'
                            )
                        )
                    else:
                        self.stdout.write(
                            self.style.WARNING(
                                '⚠ No employees processed for carry forward'
                            )
                        )
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f'No carry forward data found for FY {prev_fy_start}-{prev_fy_start+1}'
                        )
                    )
                    
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f'✗ Carry forward failed: {str(e)}'
                    )
                )
                import traceback
                traceback.print_exc()

        # STEP 4: Initialize Leave Balances
        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS(f'STEP {step_counter}: Initializing Leave Balances for {year}'))
        self.stdout.write('='*60)
        step_counter += 1
        
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

        # STEP 5: Monthly Leave Accrual
        if run_monthly_accrual:
            self.stdout.write('\n' + '='*60)
            self.stdout.write(self.style.SUCCESS(f'STEP {step_counter}: Running Monthly Leave Accrual'))
            self.stdout.write('='*60)

            try:
                count = AutoLeaveBalanceService.monthly_accrual_cron()
                if count > 0:
                    self.stdout.write(self.style.SUCCESS(f'✓ Monthly accrual completed for {count} employees'))
                else:
                    self.stdout.write(self.style.WARNING('⚠ No employees eligible for monthly accrual (may be on probation)'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'✗ Monthly accrual failed: {str(e)}'))

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
        if expire_compoff:
            services_run.append('Expire Comp Off')
        if process_carry_forward:
            services_run.append('Carry Forward')
        if run_monthly_accrual:
            services_run.append('Monthly Accrual')
        
        if services_run:
            self.stdout.write(f'Services Executed: {", ".join(services_run)}')
        
        self.stdout.write('='*60)