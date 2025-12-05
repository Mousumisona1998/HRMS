from django import forms
from django.contrib.auth.forms import AuthenticationForm
from .models import Admin, AllowedDomain, Employee, MessageSubType ,Role,Location,Department,Designation,EmployeeWarning,MessageCategory

class CustomAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your email',
            'autocomplete': 'email'
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your password',
            'autocomplete': 'current-password'
        })
    )

class AdminForm(forms.ModelForm):
    class Meta:
        model = Admin
        fields = ['name', 'email', 'phone', 'role', 'status']

class EmployeeLoginForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your email'
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your password'
        })
    )

class ChangePasswordForm(forms.Form):
    current_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Current password'
        })
    )
    new_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'New password'
        })
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirm new password'
        })
    )

    def clean(self):
        cleaned_data = super().clean()
        new_password = cleaned_data.get('new_password')
        confirm_password = cleaned_data.get('confirm_password')
        
        if new_password and confirm_password and new_password != confirm_password:
            raise forms.ValidationError("New passwords don't match")
        
        if new_password and len(new_password) < 6:
            raise forms.ValidationError("Password must be at least 6 characters long")
        
        return cleaned_data
    
class LocationForm(forms.ModelForm):
    class Meta:
        model = Location
        fields = ['name', 'code', 'address', 'city', 'state', 'country', 'zip_code', 'phone', 'email', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter location name'}),
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter location code'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Enter full address'}),
            'city': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter city'}),
            'state': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter state/province'}),
            'country': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter country'}),
            'zip_code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter ZIP/postal code'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter phone number'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Enter email address'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def _init_(self, *args, **kwargs):
        super()._init_(*args, **kwargs)
        self.fields['name'].required = True

class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ['name', 'code', 'description', 'head', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'head': forms.Select(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def _init_(self, *args, **kwargs):
        super()._init_(*args, **kwargs)
        self.fields['head'].queryset = Employee.objects.filter(
            status='active',
            role__in=['Manager', 'HR', 'Admin', 'Super Admin']
        ).order_by('first_name', 'last_name')
        # Add empty choice for head field
        self.fields['head'].empty_label = "Select a department head"
        
        # Make fields required
        self.fields['name'].required = True
        self.fields['code'].required = False
    
    def clean_code(self):
        code = self.cleaned_data.get('code')
        # If code is empty string, convert to None
        if code == '':
            return None
        return code

class DesignationForm(forms.ModelForm):
    class Meta:
        model = Designation
        fields = ['title', 'code', 'department', 'level', 'description', 'min_salary', 'max_salary', 'is_active']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'department': forms.Select(attrs={'class': 'form-control'}),
            'level': forms.NumberInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'min_salary': forms.NumberInput(attrs={'class': 'form-control'}),
            'max_salary': forms.NumberInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class RoleForm(forms.ModelForm):
    class Meta:
        model = Role
        fields = ['name', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter role name'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            })
        }

    def clean_name(self):
        name = self.cleaned_data.get('name')
        if Role.objects.filter(name__iexact=name).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("A role with this name already exists.")
        return name
# --------------------------------------------------------------------------------------
class EmployeeWarningForm(forms.ModelForm):

    class Meta:
        model = EmployeeWarning
        fields = ['employee_code', 'message_category', 'sub_type', 'subject', 'description', 'warning_date']

        widgets = {
            'subject': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter subject'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'warning_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Category dropdown should load categories
        self.fields['message_category'].queryset = MessageCategory.objects.filter(is_active=True)

        # Subtype empty by default
        self.fields['sub_type'].queryset = MessageSubType.objects.none()

        # Handle AJAX post load
        if 'message_category' in self.data:
            try:
                cat_id = int(self.data.get('message_category'))
                self.fields['sub_type'].queryset = MessageSubType.objects.filter(
                    category_id=cat_id, is_active=True
                )
            except:
                pass

        # Editing case
        elif self.instance.pk:
            cat = MessageCategory.objects.filter(name=self.instance.message_category).first()
            if cat:
                self.fields['sub_type'].queryset = MessageSubType.objects.filter(
                    category=cat, is_active=True
                )


    def clean(self):
        cleaned = super().clean()
        category = cleaned.get('message_category')
        subtype = cleaned.get('sub_type')

        # Validation: Subtype must be selected
        if category and not subtype:
            self.add_error('sub_type', "Please select a valid type for this message category.")

        return cleaned

    
class AllowedDomainForm(forms.ModelForm):
    class Meta:
        model = AllowedDomain
        fields = ['domain', 'domain_type', 'is_active', 'description']
        widgets = {
            'domain': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'e.g., company.com or *.company.com for all subdomains'
            }),
            'domain_type': forms.Select(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'description': forms.Textarea(attrs={
                'class': 'form-control', 
                'rows': 3,
                'placeholder': 'Optional description'
            }),
        }
    
    def clean_domain(self):
        domain = self.cleaned_data['domain'].lower().strip()
        if not domain:
            raise forms.ValidationError("Domain is required")
        
        # Basic domain validation
        if not any(c.isalnum() for c in domain.replace('.', '').replace('*', '')):
            raise forms.ValidationError("Enter a valid domain")
            
        return domain