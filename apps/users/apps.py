from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.users'
    # Set a short app label so Django model references use 'users' as the app_label
    label = 'users'
