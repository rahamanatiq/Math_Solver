"""
Celery Configuration for auth_system project.

This file tells Celery:
1. Where to find Django settings
2. Where to find task functions (auto-discovers from all installed apps)
3. How to connect to Redis (the message broker)

How Celery works in this project:
- Django views call tasks like: send_otp_email_task.delay(email, otp)
- The .delay() method pushes the task to Redis (takes ~1ms)
- The Celery worker (running in a separate container) picks it up
- The worker executes the actual email sending (takes 2-5 seconds)
- Django has already returned the response to the user
"""

import os
from celery import Celery

# Set Django settings module so Celery can access your project config
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'auth_system.settings')

# Create the Celery app instance
# 'auth_system' is just a name for identification in logs
app = Celery('auth_system')

# Load Celery settings from Django settings.py
# All settings prefixed with CELERY_ in settings.py will be picked up
# Example: CELERY_BROKER_URL in settings.py → broker_url in Celery
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks.py files in all installed apps
# This means Celery will automatically find:
#   users/tasks.py
#   chatbot/tasks.py
# You don't need to register tasks manually
app.autodiscover_tasks()
