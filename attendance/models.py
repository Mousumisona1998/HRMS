from django.db import models
from hr.models import Employee

class Attendance(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    date = models.DateField()
    check_in = models.DateTimeField()
    check_out = models.DateTimeField(null=True, blank=True)

    # ✅ New location fields
    checkin_latitude = models.CharField(max_length=50, null=True, blank=True)
    checkin_longitude = models.CharField(max_length=50, null=True, blank=True)
    checkin_address = models.TextField(null=True, blank=True)
    checkout_latitude = models.CharField(max_length=50, null=True, blank=True)
    checkout_longitude = models.CharField(max_length=50, null=True, blank=True)
    checkout_address = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = True
        db_table = 'attendance_attendance'
        unique_together = ['employee', 'date']
        ordering = ['-date']

    def __str__(self):
        return f"{self.employee.first_name} {self.employee.last_name} - {self.date}"

    @property
    def status(self):
        if self.check_in:
            check_in_time = self.check_in.time()
            cutoff_time = models.TimeField().to_python('09:30:00')
            return 'On Time' if check_in_time <= cutoff_time else 'Late'
        return 'N/A'