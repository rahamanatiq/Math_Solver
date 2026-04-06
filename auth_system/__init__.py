# This ensures Celery is loaded when Django starts.
#
# Why is this needed?
# When Django boots up (either via runserver, gunicorn, or the Celery worker),
# Python imports this __init__.py file. By importing the Celery app here,
# we guarantee that:
# 1. The Celery app is configured before any tasks are used
# 2. The @shared_task decorator in tasks.py files works correctly
# 3. Auto-discovery of tasks happens at the right time
#
# Without this, calling .delay() on a task would fail with:
# "Task not registered" errors

from .celery import app as celery_app

__all__ = ('celery_app',)
