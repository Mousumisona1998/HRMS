from django.apps import AppConfig


class HrConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'hr'
    
    
    def ready(self):
        """Import signals when app is ready"""
        import hr.signals  # This will register all signals