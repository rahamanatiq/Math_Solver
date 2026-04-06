import random
from django.core.mail import send_mail
from django.conf import settings

def generate_otp():
    """Generates a 6-digit OTP."""
    return str(random.randint(100000, 999999))

def send_otp_email(email, otp, username="User", expiry_minutes=10):
    """
    Sends OTP to the user's email.
    
    Uses Celery if available (production/Docker), falls back to
    synchronous sending if Celery/Redis is not running (local dev).
    """
    try:
        from users.tasks import send_otp_email_task
        # Pass all context to the background task
        send_otp_email_task.delay(email, otp, username, expiry_minutes)
    except Exception:
        # Fallback: send synchronously (Plain text for simplicity in fallback)
        subject = 'Your Verification Code'
        message = f'Hi {username}, your verification code is {otp}. It expires in {expiry_minutes} minutes.'
        email_from = f'Horus <{settings.EMAIL_HOST_USER}>'
        recipient_list = [email]
        send_mail(subject, message, email_from, recipient_list)
