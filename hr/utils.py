import hashlib
from .models import Admin, AllowedDomain, Employee, EmployeePassword

def authenticate_user(email, password):
    """
    Authenticate user against Admin and Employee tables
    Returns: (user_object, user_type) or (None, None)
    """
    # Try to authenticate as admin first
    try:
        admin = Admin.objects.get(email=email, status='active')
        # Simple password hash check
        if admin.password_hash == simple_hash(password):
            return admin, 'SUPER ADMIN'
    except Admin.DoesNotExist:
        pass
    
    # Try to authenticate as employee
    try:
        employee = Employee.objects.get(email=email, status='active')
        # Check if employee has password set
        try:
            employee_password = EmployeePassword.objects.get(employee=employee)
            if employee_password.password_hash == simple_hash(password):
                return employee, employee.role.upper()
        except EmployeePassword.DoesNotExist:
            # If no password set, use default passwords
            if check_employee_default_password(employee, password):
                return employee, employee.role.upper()
    except Employee.DoesNotExist:
        pass
    
    return None, None

def simple_hash(password):
    """Simple hash function for demo purposes"""
    return hashlib.md5(password.encode()).hexdigest()

def check_employee_default_password(employee, password):
    """
    Check employee password using employee_id or phone as default password
    """
    # Default passwords
    default_passwords = [
        employee.employee_id,  # Employee ID as password
        employee.phone,        # Phone as password
        '123456',              # Common default password
        'password'             # Common default password
    ]
    
    return password in default_passwords

def set_employee_password(employee, new_password):
    """Set or update employee password"""
    password_hash = simple_hash(new_password)
    
    try:
        # Update existing password
        employee_password = EmployeePassword.objects.get(employee=employee)
        employee_password.password_hash = password_hash
        employee_password.save()
    except EmployeePassword.DoesNotExist:
        # Create new password record
        EmployeePassword.objects.create(
            employee=employee,
            password_hash=password_hash
        )
    
    return True

def get_user_display_name(user, user_type):
    """Get display name based on user type"""
    if user_type == 'SUPER ADMIN':
        return user.name
    else:  # Employee
        return f"{user.first_name} {user.last_name}"
    
    
def validate_email_domain(email):
    """
    Validate if email domain is allowed to login
    Returns: (is_allowed, message)
    """
    if not email or '@' not in email:
        return False, "Invalid email format"
    
    domain = extract_domain_from_email(email)
    if not domain:
        return False, "Invalid email domain"
    
    # Get all active domain rules
    domain_rules = AllowedDomain.objects.filter(is_active=True)
    
    # If no rules exist, allow all domains (open system)
    if not domain_rules.exists():
        return True, "No domain restrictions configured"
    
    # Check for explicit block rules first (highest priority)
    block_rules = domain_rules.filter(domain_type='BLOCK')
    for rule in block_rules:
        if _domain_matches(domain, rule.domain):
            return False, f"Email domain '{domain}' is blocked from accessing the system"
    
    # Check for allow rules
    allow_rules = domain_rules.filter(domain_type='ALLOW')
    if allow_rules.exists():
        for rule in allow_rules:
            if _domain_matches(domain, rule.domain):
                return True, "Domain allowed"
        # If we have allow rules but no match, block the domain
        return False, f"Email domain '{domain}' is not in the allowed list"
    
    # If only block rules exist and domain is not blocked, allow it
    return True, "Domain allowed"

def _domain_matches(input_domain, rule_domain):
    """
    Check if input domain matches the rule domain
    Supports wildcard domains like *.company.com
    """
    input_domain = input_domain.lower()
    rule_domain = rule_domain.lower().strip()
    
    # Exact match
    if input_domain == rule_domain:
        return True
    
    # Wildcard match - *.company.com
    if rule_domain.startswith('*.'):
        base_domain = rule_domain[2:]  # Remove '*.'
        return input_domain.endswith('.' + base_domain) or input_domain == base_domain
    
    return False

def extract_domain_from_email(email):
    """Extract domain from email address"""
    try:
        return email.split('@')[1].lower().strip()
    except (IndexError, AttributeError):
        return None

def get_domain_restriction_message():
    """
    Get a user-friendly message about domain restrictions
    """
    domains = AllowedDomain.objects.filter(is_active=True, domain_type='ALLOW')
    if not domains.exists():
        return "All email domains are currently allowed"
    
    allowed_domains = [domain.domain for domain in domains]
    
    if len(allowed_domains) == 1:
        return f"Only {allowed_domains[0]} emails are allowed"
    elif len(allowed_domains) <= 3:
        return f"Only emails from {', '.join(allowed_domains)} are allowed"
    else:
        return f"Only emails from {len(allowed_domains)} allowed domains are permitted"