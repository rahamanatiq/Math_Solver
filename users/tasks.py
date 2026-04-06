"""
Celery tasks for the users app.

These are the functions that run in the BACKGROUND on the Celery worker,
not on the Django web server. When a view calls:

    send_otp_email_task.delay(email, otp)

Here's what happens:
1. Django serializes the arguments (email, otp) into a JSON message
2. Django pushes that message to Redis (takes ~1ms)
3. Django returns the HTTP response to the user IMMEDIATELY
4. The Celery worker (separate container) picks up the message from Redis
5. The worker runs send_otp_email_task() which sends the actual email (2-5s)

The user never waits for the email to be sent.
"""

from celery import shared_task
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,  # Wait 60 seconds before retrying
)
def send_otp_email_task(self, email, otp, username="User", expiry_minutes=10):
    """
    Sends OTP to the user's email in the background using an HTML template.
    """
    try:
        subject = 'Your Verification Code'
        
        # Context for the HTML template
        context = {
            'username': username,
            'otp_code': otp,
            'expiry_minutes': expiry_minutes,
        }
        
        # Render the HTML template
        html_message = render_to_string('users/email_otp.html', context)
        # Create a plain-text version for email clients that don't support HTML
        plain_message = strip_tags(html_message)
        
        email_from = f"Horus <{settings.EMAIL_HOST_USER}>"
        recipient_list = [email]
        
        send_mail(
            subject, 
            plain_message, 
            email_from, 
            recipient_list, 
            html_message=html_message
        )
        return f"HTML OTP sent to {email}"
    
    except Exception as exc:
        raise self.retry(exc=exc)
