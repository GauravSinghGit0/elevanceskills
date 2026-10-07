import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

class Command(BaseCommand):
    help = 'Creates or updates the Cineva administrative superuser with secure credentials'

    def handle(self, *args, **options):
        User = get_user_model()
        username = os.environ.get('ADMIN_USERNAME', 'admin')
        password = os.environ.get('ADMIN_PASSWORD', 'Admin@Cineva#Secure2026!')
        email = os.environ.get('ADMIN_EMAIL', 'admin@cineva.film')

        user, created = User.objects.get_or_create(
            username=username,
            defaults={'email': email, 'is_staff': True, 'is_superuser': True}
        )
        user.set_password(password)
        user.is_staff = True
        user.is_superuser = True
        user.email = email
        user.save()

        action = "Created new" if created else "Updated existing"
        self.stdout.write(self.style.SUCCESS(
            f"Successfully {action} superuser '{username}' with secure password and staff/superuser privileges."
        ))
