import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'auth_system.settings')
django.setup()

from django.contrib.auth import get_user_model
User = get_user_model()

print("Registered Users:")
for user in User.objects.all():
    print(f"ID: {user.id}, Username: {user.username}, Email: {user.email}")
