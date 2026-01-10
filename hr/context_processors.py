# In context_processors.py
from hr.models import Role, Employee, YsMenuMaster, YsMenuLinkMaster, YsMenuRoleMaster, YsUserRoleMaster,CelebrationWish
from datetime import date, timedelta
from django.utils import timezone


# In context_processors.py
def dynamic_menu(request):
    """Provide menus based on user permissions"""
    if not request.session.get('user_authenticated'):
        return {}

    try:
        user_role_name = request.session.get('user_role')
        user_employee_id = request.session.get('user_employee_id')
        
        # Get role permissions
        try:
            user_role = Role.objects.get(name=user_role_name)
            role_permissions = YsMenuRoleMaster.objects.filter(
                userRoleId=user_role.id, 
                permission_type='ROLE',
                status=True
            )
        except Role.DoesNotExist:
            role_permissions = []

        # Get individual permissions if employee ID exists
        individual_permissions = []
        if user_employee_id:
            try:
                employee = Employee.objects.get(employee_id=user_employee_id)
                individual_permissions = YsMenuRoleMaster.objects.filter(
                    userRoleId=employee.id,
                    permission_type='EMPLOYEE', 
                    status=True
                )
            except Employee.DoesNotExist:
                individual_permissions = []

        # Combine permissions
        all_permissions = list(role_permissions) + list(individual_permissions)
        
        # Build menu structure (same as before)
        menu_dict = {}
        
        for permission in all_permissions:
            if permission.menu_id:
                try:
                    menu = YsMenuMaster.objects.get(menu_id=permission.menu_id, status=1)
                    if menu.menu_id not in menu_dict:
                        menu_dict[menu.menu_id] = {
                            'id': menu.menu_id,
                            'name': menu.menu_name,
                            'icon': menu.menu_icon,
                            'url': menu.menu_url,
                            'submenus': []
                        }
                except YsMenuMaster.DoesNotExist:
                    continue
        
        for permission in all_permissions:
            if permission.menu_link_id:
                try:
                    menu_link = YsMenuLinkMaster.objects.get(menu_link_id=permission.menu_link_id, status=1)
                    menu = menu_link.menu
                    if menu.menu_id in menu_dict:
                        existing_links = [sm.menu_link_id for sm in menu_dict[menu.menu_id]['submenus']]
                        if menu_link.menu_link_id not in existing_links:
                            menu_dict[menu.menu_id]['submenus'].append(menu_link)
                except (YsMenuLinkMaster.DoesNotExist, YsMenuMaster.DoesNotExist):
                    continue
        
        menu_data = list(menu_dict.values())
        menu_data.sort(key=lambda x: x['id'])

        return {'menu_data': menu_data}
    except Exception as e:
        print(f"Menu error: {e}")
        return {'menu_data': []}


def get_assigned_menus(request):
    """
    Context processor to get menus assigned to the logged-in user
    """
    if not request.session.get('user_authenticated'):
        return {'menu_data': []}
    
    try:
        # Get current user's role
        user_role = request.session.get('user_role')
        if not user_role:
            return {'menu_data': []}
        
        # Get user role ID from ys_user_role_master
        user_role_obj = Role.objects.filter(name=user_role, is_active=True).first()
        if not user_role_obj:
            return {'menu_data': []}
        
        role_id = user_role_obj.id
        
        # Get all assigned menu links for this role
        assigned_permissions = YsMenuRoleMaster.objects.filter(
            userRoleId=role_id,
            status=True
        )
        
        # Get assigned menu_link_ids
        assigned_menu_link_ids = [perm.menu_link_id for perm in assigned_permissions]
        
        # Get all active menus
        menus = YsMenuMaster.objects.filter(status=True).order_by('seq')
        
        menu_data = []
        
        for menu in menus:
            # Check if this menu has any assigned submenus
            assigned_submenus = YsMenuLinkMaster.objects.filter(
                menu_id=menu.menu_id,
                menu_link_id__in=assigned_menu_link_ids,
                status=1
            ).order_by('seq')
            
            # Check if this menu itself is assigned (standalone menu)
            is_menu_assigned = YsMenuRoleMaster.objects.filter(
                userRoleId=role_id,
                menu_id=menu.menu_id,
                menu_link_id=menu.menu_id,  # For standalone menus
                status=True
            ).exists()
            
            # If it's a standalone menu and assigned, or has assigned submenus
            if is_menu_assigned or assigned_submenus.exists():
                menu_info = {
                    'id': menu.menu_id,
                    'name': menu.menu_name,
                    'icon': menu.menu_icon,
                    'url': menu.menu_url,
                    'submenus': []
                }
                
                # Add submenus if any are assigned
                for submenu in assigned_submenus:
                    menu_info['submenus'].append({
                        'menu_link_id': submenu.menu_link_id,
                        'menu_link_name': submenu.menu_link_name,
                        'menu_link_icon': submenu.menu_link_icon,
                        'menu_link_url': submenu.menu_link_url
                    })
                
                menu_data.append(menu_info)
        
        return {'menu_data': menu_data}
    
    except Exception as e:
        print(f"Error in menu context processor: {e}")
        return {'menu_data': []}
    
def celebration_notifications(request):
    """Context processor to check for birthdays and anniversaries for next 7 days"""
    if not request.session.get('user_authenticated'):
        return {}
    
    user_email = request.session.get('user_email')
    user_role = request.session.get('user_role')
    
    celebrations = {
        'birthdays_today': [],
        'birthdays_upcoming': [],  # NEW: For next 7 days
        'work_anniversaries_today': [],
        'work_anniversaries_upcoming': [],  # NEW: For next 7 days
        'marriage_anniversaries_today': [],
        'marriage_anniversaries_upcoming': [],  # NEW: For next 7 days
        'show_celebration_popup': False,
        'has_seen_popup_today': False,
        'current_user_id': None,
        'total_count': 0,
        'upcoming_dates': []  # NEW: Store upcoming dates info
    }
    
    try:
        # Get current user
        current_user = None
        if user_role == 'SUPER ADMIN':
            celebrations['current_user_id'] = 'admin'
        else:
            try:
                current_user = Employee.objects.get(email=user_email, status='active')
                celebrations['current_user_id'] = current_user.id
            except Employee.DoesNotExist:
                celebrations['current_user_id'] = None

        # Get today's date and next 7 days
        today = timezone.now().date()
        week_from_now = today + timedelta(days=7)
        
        # Create list of upcoming dates for display
        upcoming_dates = []
        for i in range(8):  # 0-7 days (including today)
            date_obj = today + timedelta(days=i)
            upcoming_dates.append({
                'date': date_obj,
                'day_name': date_obj.strftime('%A'),
                'display': date_obj.strftime('%d %b') + (" (Today)" if i == 0 else (" (Tomorrow)" if i == 1 else ""))
            })
        
        celebrations['upcoming_dates'] = upcoming_dates
        
        # Check if user has already seen popup today
        today_str = today.isoformat()
        if request.session.get('last_popup_date') != today_str:
            celebrations['show_celebration_popup'] = True
            request.session['last_popup_date'] = today_str
        
        # Get all active employees
        active_employees = Employee.objects.filter(status='active')
        
        # Process birthdays (today + next 7 days)
        for emp in active_employees:
            if emp.date_of_birth:
                # Get next birthday
                next_birthday = date(today.year, emp.date_of_birth.month, emp.date_of_birth.day)
                if next_birthday < today:
                    next_birthday = date(today.year + 1, emp.date_of_birth.month, emp.date_of_birth.day)
                
                # Check if birthday is within next 7 days
                days_until = (next_birthday - today).days
                if 0 <= days_until <= 7:
                    birthday_data = {
                        'id': emp.id,
                        'employee_id': emp.employee_id,
                        'name': emp.full_name,
                        'designation': emp.designation,
                        'department': emp.department,
                        'years_old': today.year - emp.date_of_birth.year if next_birthday.year > emp.date_of_birth.year else today.year - emp.date_of_birth.year - 1,
                        'is_current_user': current_user and emp.id == current_user.id,
                        'date': next_birthday,
                        'days_until': days_until,
                        'formatted_date': next_birthday.strftime('%d %b')
                    }
                    
                    if days_until == 0:
                        celebrations['birthdays_today'].append(birthday_data)
                    else:
                        celebrations['birthdays_upcoming'].append(birthday_data)
        
        # Process work anniversaries (today + next 7 days)
        for emp in active_employees:
            if emp.date_of_joining:
                # Get next anniversary
                next_anniversary = date(today.year, emp.date_of_joining.month, emp.date_of_joining.day)
                if next_anniversary < today:
                    next_anniversary = date(today.year + 1, emp.date_of_joining.month, emp.date_of_joining.day)
                
                # Check if anniversary is within next 7 days
                days_until = (next_anniversary - today).days
                if 0 <= days_until <= 7:
                    years_of_service = emp.get_years_of_service()
                    anniversary_data = {
                        'id': emp.id,
                        'employee_id': emp.employee_id,
                        'name': emp.full_name,
                        'designation': emp.designation,
                        'department': emp.department,
                        'years': years_of_service,
                        'is_current_user': current_user and emp.id == current_user.id,
                        'date': next_anniversary,
                        'days_until': days_until,
                        'formatted_date': next_anniversary.strftime('%d %b')
                    }
                    
                    if days_until == 0:
                        celebrations['work_anniversaries_today'].append(anniversary_data)
                    else:
                        celebrations['work_anniversaries_upcoming'].append(anniversary_data)
        
        # Process marriage anniversaries (today + next 7 days)
        for emp in active_employees:
            if emp.marriage_date:
                # Get next anniversary
                next_anniversary = date(today.year, emp.marriage_date.month, emp.marriage_date.day)
                if next_anniversary < today:
                    next_anniversary = date(today.year + 1, emp.marriage_date.month, emp.marriage_date.day)
                
                # Check if anniversary is within next 7 days
                days_until = (next_anniversary - today).days
                if 0 <= days_until <= 7:
                    years_of_marriage = emp.get_years_of_marriage()
                    anniversary_data = {
                        'id': emp.id,
                        'employee_id': emp.employee_id,
                        'name': emp.full_name,
                        'designation': emp.designation,
                        'department': emp.department,
                        'years': years_of_marriage,
                        'is_current_user': current_user and emp.id == current_user.id,
                        'date': next_anniversary,
                        'days_until': days_until,
                        'formatted_date': next_anniversary.strftime('%d %b')
                    }
                    
                    if days_until == 0:
                        celebrations['marriage_anniversaries_today'].append(anniversary_data)
                    else:
                        celebrations['marriage_anniversaries_upcoming'].append(anniversary_data)
        
        # Sort upcoming events by date
        celebrations['birthdays_upcoming'] = sorted(celebrations['birthdays_upcoming'], key=lambda x: x['days_until'])
        celebrations['work_anniversaries_upcoming'] = sorted(celebrations['work_anniversaries_upcoming'], key=lambda x: x['days_until'])
        celebrations['marriage_anniversaries_upcoming'] = sorted(celebrations['marriage_anniversaries_upcoming'], key=lambda x: x['days_until'])
        
        # Update show_celebration_popup based on actual celebrations
        if celebrations['show_celebration_popup']:
            celebrations['show_celebration_popup'] = (
                len(celebrations['birthdays_today']) > 0 or
                len(celebrations['work_anniversaries_today']) > 0 or
                len(celebrations['marriage_anniversaries_today']) > 0 or
                len(celebrations['birthdays_upcoming']) > 0 or
                len(celebrations['work_anniversaries_upcoming']) > 0 or
                len(celebrations['marriage_anniversaries_upcoming']) > 0
            )
        
    except Exception as e:
        # Log error but don't break the application
        print(f"Error in celebration notifications: {str(e)}")
    
    # Calculate total count (today + upcoming)
    total_count = (
        len(celebrations['birthdays_today']) +
        len(celebrations['work_anniversaries_today']) +
        len(celebrations['marriage_anniversaries_today']) +
        len(celebrations['birthdays_upcoming']) +
        len(celebrations['work_anniversaries_upcoming']) +
        len(celebrations['marriage_anniversaries_upcoming'])
    )
    celebrations['total_count'] = total_count
    
    return {'celebrations': celebrations}