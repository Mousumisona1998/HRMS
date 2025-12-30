from datetime import timedelta
from django.utils import timezone
from django.db import models
from django.core.exceptions import ObjectDoesNotExist

class Admin(models.Model):
    admin_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100)
    email = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    role = models.CharField(max_length=100)
    profile_picture = models.CharField(max_length=255, blank=True, default="")  # Make optional with default
    password_hash = models.CharField(max_length=255)
    status = models.CharField(max_length=8)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = True  
        db_table = 'hr_admin'

class Employee(models.Model):
    # Basic Information
    id = models.AutoField(primary_key=True)
    employee_id = models.CharField(max_length=200)
    first_name = models.CharField(max_length=50)
    middle_name = models.CharField(max_length=50, blank=True, null=True)
    last_name = models.CharField(max_length=50)
    email = models.CharField(max_length=100)
    
    # Phone numbers with dial code
    dial_code = models.CharField(
        max_length=5,
        default='+91',
        help_text="Country code (e.g., +91, +1)"
    )
    phone = models.CharField(max_length=20)
    alternate_phone = models.CharField(max_length=20, blank=True, null=True)
    residence_number = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(null=True, blank=True)
    present_address = models.TextField(null=True, blank=True)
    
    # Personal Information
    GENDER_CHOICES = [
        ('Male', 'Male'),
        ('Female', 'Female'),
        ('Other', 'Other'),
        ('Prefer not to say', 'Prefer not to say')
    ]
    gender = models.CharField(max_length=20, choices=GENDER_CHOICES, blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True, help_text="Format: DD-MM-YYYY")
    
    MARITAL_STATUS_CHOICES = [
        ('Single', 'Single'),
        ('Married', 'Married'),
        ('Divorced', 'Divorced'),
        ('Widowed', 'Widowed')
    ]
    marital_status = models.CharField(max_length=20, choices=MARITAL_STATUS_CHOICES, blank=True, null=True)
    marriage_date = models.DateField(blank=True, null=True, help_text="Format: DD-MMM-YYYY")
    
    # Family Information
    father_name = models.CharField(max_length=100, blank=True, null=True)
    mother_name = models.CharField(max_length=100, blank=True, null=True)
    spouse_name = models.CharField(max_length=100, blank=True, null=True)
    spouse_gender = models.CharField(max_length=20, choices=GENDER_CHOICES, blank=True, null=True)
    
    # Medical & Physical Information
    physically_handicapped = models.BooleanField(default=False)
    
    BLOOD_GROUP_CHOICES = [
        ('A+', 'A+'), ('A-', 'A-'),
        ('B+', 'B+'), ('B-', 'B-'),
        ('O+', 'O+'), ('O-', 'O-'),
        ('AB+', 'AB+'), ('AB-', 'AB-')
    ]
    blood_group = models.CharField(max_length=5, choices=BLOOD_GROUP_CHOICES, blank=True, null=True)
    nationality = models.CharField(max_length=50, default='Indian', blank=True, null=True)
    
    # Updated to use ForeignKey relationships
    department = models.CharField(max_length=100)
    department_id = models.CharField(max_length=100)
    designation = models.CharField(max_length=100)
    designation_id = models.CharField(max_length=100)
    location = models.CharField(max_length=100)
    location_id = models.CharField(max_length=100)
    
    # Employment Details
    role = models.CharField(
        max_length=20,
        choices=[
            ('Employee', 'Employee'),
            ('Manager', 'Manager'),
            ('HR', 'HR'),
            ('Admin', 'Admin'),
            ('Super Admin', 'Super Admin')
        ]
    )
    date_of_joining = models.DateField(help_text="Format: DD-MM-YYYY")
    contract_end_date = models.DateField(blank=True, null=True, help_text="Format: DD-MM-YYYY")
    legal_entity = models.CharField(max_length=200, blank=True, null=True, help_text="Dynamic legal entity entry")
    
    WORKER_TYPE_CHOICES = [
        ('Permanent', 'Permanent'),
        ('Contract', 'Contract'),
        ('Intern', 'Intern'),
        ('Trainee', 'Trainee'),
        ('Consultant', 'Consultant')
    ]
    worker_type = models.CharField(max_length=20, choices=WORKER_TYPE_CHOICES, default='Permanent')
    
    reporting_manager = models.CharField(max_length=100)
    reporting_manager_id = models.CharField(max_length=50, blank=True, null=True)
    
    status = models.CharField(
        max_length=8,
        choices=[('active', 'active'), ('inactive', 'inactive')]
    )
    profile_picture = models.ImageField(upload_to="employees/", blank=True, null=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    # Bank & Salary Information
    bank_name = models.CharField(max_length=100, blank=True, null=True)
    account_number = models.CharField(max_length=20, blank=True, null=True)
    ifsc_code = models.CharField(max_length=11, blank=True, null=True)
    # Probation fields
    probation_period_days = models.IntegerField(default=90, help_text="Probation period in days")
    probation_end_date = models.DateField(null=True, blank=True)
    
    # Notice period fields
    notice_period_days = models.IntegerField(default=60, help_text="Notice period in days")
    notice_period_start_date = models.DateField(null=True, blank=True, help_text="When notice period starts")
    notice_period_end_date = models.DateField(null=True, blank=True, help_text="When notice period ends")
    resignation_date = models.DateField(null=True, blank=True, help_text="Date when employee resigned")
    
    SALARY_PAYMENT_MODE_CHOICES = [
        ('Bank Transfer', 'Bank Transfer'),
        ('Cash', 'Cash'),
        ('Cheque', 'Cheque')
    ]
    salary_payment_mode = models.CharField(
        max_length=20, 
        choices=SALARY_PAYMENT_MODE_CHOICES, 
        default='Bank Transfer'
    )
    name_on_bank_account = models.CharField(max_length=100, blank=True, null=True)
    
    # Basic Salary field
    basic_salary = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0.00,
        blank=True,
        null=True,
        help_text="Basic salary amount"
    )
    
    # PF (Provident Fund) Details
    pf_establishment_id = models.CharField(max_length=100, blank=True, null=True)
    
    PF_DETAILS_CHOICES = [
        ('Yes', 'Yes'),
        ('No', 'No')
    ]
    pf_details_available = models.CharField(
        max_length=3, 
        choices=PF_DETAILS_CHOICES, 
        default='No'
    )
    pf_number = models.CharField(max_length=100, blank=True, null=True)
    pf_joining_date = models.DateField(blank=True, null=True, help_text="Format: DD-MMM-YYYY")
    name_on_pf_account = models.CharField(max_length=100, blank=True, null=True)
    uan = models.CharField(max_length=20, blank=True, null=True, help_text="Universal Account Number")
    
    # ESI (Employee State Insurance) Details
    ESI_ELIGIBLE_CHOICES = [
        ('Yes', 'Yes'),
        ('No', 'No')
    ]
    esi_eligible = models.CharField(
        max_length=3, 
        choices=ESI_ELIGIBLE_CHOICES, 
        default='No'
    )
    employer_esi_number = models.CharField(max_length=100, blank=True, null=True)
    esi_details_available = models.CharField(
        max_length=3, 
        choices=PF_DETAILS_CHOICES, 
        default='No'
    )
    esi_number = models.CharField(max_length=100, blank=True, null=True)
    
    # Professional Tax & LWF Details
    pt_establishment_id = models.CharField(max_length=100, blank=True, null=True)
    
    LWF_ELIGIBLE_CHOICES = [
        ('Yes', 'Yes'),
        ('No', 'No')
    ]
    lwf_eligible = models.CharField(
        max_length=3, 
        choices=LWF_ELIGIBLE_CHOICES, 
        default='No'
    )
    enrollment_number = models.CharField(max_length=100, blank=True, null=True)
    
    # Insurance Details
    INSURANCE_TYPE_CHOICES = [
        ('Health', 'Health Insurance'),
        ('Life', 'Life Insurance'),
        ('Accident', 'Accident Insurance'),
        ('Critical Illness', 'Critical Illness Insurance'),
        ('Other', 'Other')
    ]
    
    insurance_type = models.CharField(
        max_length=20, 
        choices=INSURANCE_TYPE_CHOICES, 
        blank=True, 
        null=True
    )
    policy_name = models.CharField(max_length=200, blank=True, null=True)
    insurance_company = models.CharField(max_length=200, blank=True, null=True)
    policy_number = models.CharField(max_length=100, blank=True, null=True)
    coverage_amount = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        blank=True, 
        null=True,
        help_text="Coverage amount in INR"
    )
    nominee_name = models.CharField(max_length=100, blank=True, null=True)
    nominee_relationship = models.CharField(max_length=100, blank=True, null=True)
    policy_start_date = models.DateField(blank=True, null=True)
    policy_end_date = models.DateField(blank=True, null=True)
    created_by = models.CharField(max_length=100, blank=True, null=True)
    updated_by = models.CharField(max_length=100, blank=True, null=True)
    class Meta:
        managed = True 
        db_table = 'hr_employee' 
    
    def save(self, *args, **kwargs):
            # Recalculate probation end date whenever saving
            if self.date_of_joining:
                from leave.services import ProbationService
                self.probation_end_date = ProbationService.calculate_probation_end_date(self)
            
            # Auto-calculate notice period end date if resignation date is set
            if self.resignation_date and not self.notice_period_end_date:
                self.notice_period_start_date = self.resignation_date
                self.notice_period_end_date = self.calculate_notice_period_end_date()
            
            if not self.created_at:
                self.created_at = timezone.now()
            self.updated_at = timezone.now()
            
            super().save(*args, **kwargs)
            
    def calculate_probation_end_date(self):
        """Calculate probation end date using individual probation period"""
        if self.date_of_joining and self.probation_period_days:
            return self.date_of_joining + timedelta(days=self.probation_period_days)
        return None  
    def calculate_notice_period_end_date(self):
        """Calculate notice period end date"""
        if self.resignation_date and self.notice_period_days:
            return self.resignation_date + timedelta(days=self.notice_period_days)
        return None
    def is_on_probation(self):
        """Check if employee is currently on probation"""
        if not self.probation_end_date:
            return False
        return timezone.now().date() <= self.probation_end_date     
    
    def is_on_notice_period(self):
        """Check if employee is currently on notice period"""
        if not self.notice_period_end_date:
            return False
        return (self.notice_period_start_date <= timezone.now().date() <= self.notice_period_end_date)
    
    def get_remaining_notice_days(self):
        """Get remaining days in notice period"""
        if not self.is_on_notice_period():
            return 0
        remaining = (self.notice_period_end_date - timezone.now().date()).days
        return max(0, remaining)
    # fuctionality of wishing anniversary
    def is_birthday_today(self):
        """Check if today is employee's birthday"""
        if not self.date_of_birth:
            return False
        today = timezone.now().date()
        return self.date_of_birth.month == today.month and self.date_of_birth.day == today.day
    
    def is_anniversary_today(self):
        """Check if today is work anniversary"""
        if not self.date_of_joining:
            return False
        today = timezone.now().date()
        return self.date_of_joining.month == today.month and self.date_of_joining.day == today.day
    
    def is_marriage_anniversary_today(self):
        """Check if today is marriage anniversary"""
        if not self.marriage_date:
            return False
        today = timezone.now().date()
        return self.marriage_date.month == today.month and self.marriage_date.day == today.day
    
    def get_years_of_service(self):
        """Calculate years of service for anniversary"""
        if not self.date_of_joining:
            return 0
        today = timezone.now().date()
        years = today.year - self.date_of_joining.year
        # Adjust if anniversary hasn't occurred yet this year
        if today.month < self.date_of_joining.month or (today.month == self.date_of_joining.month and today.day < self.date_of_joining.day):
            years -= 1
        return years
    
    def get_years_of_marriage(self):
        """Calculate years of marriage"""
        if not self.marriage_date:
            return 0
        today = timezone.now().date()
        years = today.year - self.marriage_date.year
        # Adjust if anniversary hasn't occurred yet this year
        if today.month < self.marriage_date.month or (today.month == self.marriage_date.month and today.day < self.marriage_date.day):
            years -= 1
        return years
    
    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.employee_id})"
    
    # Property methods to access names easily
    @property
    def department_name(self):
        return self.department.name if self.department else None
    
    @property
    def designation_name(self):
        return self.designation.title if self.designation else None
    
    @property
    def location_name(self):
        return self.location.name if self.location else None
    
    @property
    def full_name(self):
        if self.middle_name:
            return f"{self.first_name} {self.middle_name} {self.last_name}"
        return f"{self.first_name} {self.last_name}"
    
class EmployeePassword(models.Model):
    employee = models.OneToOneField(Employee, on_delete=models.CASCADE, primary_key=True)
    password_hash = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = True
        db_table = 'hr_employeepassword' 
        
    def __str__(self):
        return f"Password for {self.employee.email}"


class EmployeeDocument(models.Model):
    DOCUMENT_TYPES = [
        ('educational', 'Educational Certificate'),
        ('pan', 'PAN Card'),
        ('aadhaar', 'Aadhaar Card'),
        ('passbook', 'Bank Passbook'),
        ('offer_letter', 'Offer Letter'),
        ('salary_slip', 'Salary Slip'),
        ('bank_statement', 'Bank Statement'),
        ('experience_letter', 'Experience/Relieving Letter'),
    ]
    
    id = models.AutoField(primary_key=True)
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='documents')
    document_type = models.CharField(max_length=20, choices=DOCUMENT_TYPES)
    document_number = models.CharField(max_length=100, blank=True, null=True)  # For PAN, Aadhaar
    file = models.FileField(upload_to="employee_documents/")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        managed = True
        db_table = 'hr_employee_documents'

    def __str__(self):
        return f"{self.employee.employee_id} - {self.get_document_type_display()}"    
    
 # ------------------------------------------------------       
    
class Location(models.Model):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=10, unique=True, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    city = models.CharField(max_length=50, blank=True, null=True)
    state = models.CharField(max_length=50, blank=True, null=True)
    country = models.CharField(max_length=50, default='India')
    zip_code = models.CharField(max_length=20, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'hr_locations'
        ordering = ['name']

    def _str_(self):
        return self.name

    def get_full_address(self):
        address_parts = []
        if self.address:
            address_parts.append(self.address)
        if self.city:
            address_parts.append(self.city)
        if self.state:
            address_parts.append(self.state)
        if self.country:
            address_parts.append(self.country)
        if self.zip_code:
            address_parts.append(self.zip_code)
        return ', '.join(filter(None, address_parts))



class Department(models.Model):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=10, unique=False, null=True, blank=True)
    description = models.TextField(blank=True, null=True)
    head = models.ForeignKey(
        'Employee', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='headed_departments'
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'hr_departments'
        ordering = ['name']

    def _str_(self):
        return self.name

class Designation(models.Model):
    title = models.CharField(max_length=100)
    code = models.CharField(max_length=10, unique=True, blank=True, null=True)
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='designations')
    level = models.IntegerField(default=1, help_text="Hierarchy level (1 = entry level)")
    description = models.TextField(blank=True, null=True)
    min_salary = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    max_salary = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'hr_designations'
        ordering = ['department', 'level']
        unique_together = ['title', 'department']

    def _str_(self):
        return f"{self.title} - {self.department.name}"


class Role(models.Model):
    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'hr_roles'
        verbose_name = 'Role'
        verbose_name_plural = 'Roles'
        ordering = ['name']

    def _str_(self):
        return self.name
# ------------------------------------------------------    


class ProbationConfiguration(models.Model):
    """Configuration for probation period settings"""
    probation_period_days = models.IntegerField(default=90, help_text="Default probation period in days")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'hr_probation_configuration'
        verbose_name_plural = "Probation Configuration"
    
    def __str__(self):
        return f"Probation: {self.probation_period_days} days"
    
    def save(self, *args, **kwargs):
        # Ensure only one active configuration
        if self.is_active:
            ProbationConfiguration.objects.exclude(id=self.id).update(is_active=False)
        super().save(*args, **kwargs)


class MessageCategory(models.Model):
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True) 
    
    class Meta:
        db_table = 'message_category' 

    def __str__(self):
        return self.name


class MessageSubType(models.Model):
    category = models.ForeignKey(MessageCategory, on_delete=models.CASCADE, related_name="subtypes")
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'message_subtype' 

    def __str__(self):
        return f"{self.category.name} - {self.name}"


class EmployeeWarning(models.Model):
    employee_code = models.CharField(max_length=100)

    message_category = models.CharField(max_length=255)  
    sub_type = models.CharField(max_length=255)

    warning_date = models.DateField()
    subject = models.CharField(max_length=255)
    description = models.TextField()
    issued_by = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'employee_warning'

    def __str__(self):
        return f"{self.employee_code} - {self.subject}"

    def get_employee_name(self):
        from hr.models import Employee
        try:
            emp = Employee.objects.get(employee_id=self.employee_code)
            return f"{emp.first_name} {emp.last_name} ({emp.employee_id})"
        except:
            return f"({self.employee_code})"
 
    # Helper for table display
    def get_message_type(self):
        if self.message_category == "Warning":
            return self.warning_type
        else:
            return self.appreciation_type   


# Menu and submenu

class YsMenuMaster(models.Model):
    menu_id = models.AutoField(primary_key=True)
    menu_name = models.CharField(max_length=45)
    menu_icon = models.CharField(max_length=200, null=True, blank=True)
    menu_id_name = models.CharField(max_length=45, null=True, blank=True)
    menu_url = models.CharField(max_length=100, null=True, blank=True)
    display_area_type = models.CharField(max_length=1, null=True, blank=True)
    icon_bytes = models.BinaryField(null=True, blank=True)
    seq = models.IntegerField(null=True, blank=True)
    status = models.BooleanField(default=False)

    class Meta:
        db_table = 'ys_menu_master'
        ordering = ['seq']

    def _str_(self):
        return self.menu_name


class YsMenuLinkMaster(models.Model):
    menu_link_id = models.AutoField(primary_key=True)
    menu_link_name = models.CharField(max_length=45)
    menu_link_icon = models.CharField(max_length=200, null=True, blank=True)
    menu_link_url = models.CharField(max_length=100, null=True, blank=True)
    menu_link_id_name = models.CharField(max_length=45, null=True, blank=True)
    menu = models.ForeignKey(YsMenuMaster, on_delete=models.CASCADE)
    seq = models.IntegerField(null=True, blank=True)
    status = models.IntegerField(default=1)  # Change from BooleanField to IntegerField

    class Meta:
        db_table = 'ys_menu_link_master'
        ordering = ['seq']

    def _str_(self):
        return self.menu_link_name
    

    # User role
class YsUserRoleMaster(models.Model):
    userRoleId = models.AutoField(primary_key=True)
    userRole = models.CharField(max_length=45)
    isActive = models.BooleanField(default=True)

    class Meta:
        db_table = 'ys_user_role_master'
        verbose_name = 'User Role'
        verbose_name_plural = 'User Roles'

    def _str_(self):
        return self.userRole

# In models.py - Update YsMenuRoleMaster
class YsMenuRoleMaster(models.Model):
    menu_role_id = models.AutoField(primary_key=True)
    userRoleId = models.IntegerField()  # Can be Role.id or Employee.id
    menu_link_id = models.IntegerField(null=True, blank=True)
    menu_id = models.IntegerField(null=True, blank=True)
    status = models.BooleanField(default=True)    
    # created_at = models.DateTimeField(auto_now_add=True)
    # updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ys_menu_role_master'
        managed = False

    def _str_(self):
        return f"MenuRole {self.menu_role_id} - UserRole: {self.userRoleId}"
    
    
class AllowedDomain(models.Model):
    DOMAIN_TYPES = [
        ('ALLOW', 'Allow'),
        ('BLOCK', 'Block'),
    ]
    
    domain = models.CharField(max_length=255, unique=True, help_text="Enter domain like 'company.com' or '*.company.com' for subdomains")
    domain_type = models.CharField(max_length=10, choices=DOMAIN_TYPES, default='ALLOW')
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True, null=True, help_text="Optional description")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        status = "Active" if self.is_active else "Inactive"
        return f"{self.domain} ({self.domain_type} - {status})"
    
    class Meta:
        db_table = 'hr_allowed_domains'
        verbose_name = 'Allowed Domain'
        verbose_name_plural = 'Allowed Domains'
        ordering = ['domain']
        
        
        
class CelebrationWish(models.Model):
    celebrant = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='received_wishes')
    wisher = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='sent_wishes')
    message = models.TextField()
    wish_type = models.CharField(max_length=20, choices=[
        ('birthday', 'Birthday'),
        ('work_anniversary', 'Work Anniversary'),
        ('marriage_anniversary', 'Marriage Anniversary')
    ])
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'celebration_wishes'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Wish from {self.wisher.full_name} to {self.celebrant.full_name}"