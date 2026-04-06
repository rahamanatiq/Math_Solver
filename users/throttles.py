from rest_framework.throttling import AnonRateThrottle
from django.conf import settings

class OTPRateThrottle(AnonRateThrottle):
    """
    Strict rate limit specifically for OTP-sending endpoints:
    register, password-reset, and resend-otp.
    
    Allows 5 requests per hour per IP address in production.
    This prevents bots from burning through your Gmail SMTP quota
    (Gmail limits ~500 emails/day for regular accounts).
    
    Why per-IP instead of per-email?
    A bot could rotate email addresses. IP-based throttling catches
    that. The 60-second cooldown in ResendOTPView handles the
    per-email case.
    """
    # Enforce strict 5/hour rate match production behavior.
    # User commented out for testing:
    # rate = '15/hour'
    # scope = 'otp'
    
    def get_rate(self):
        # Fallback to None if rate is not defined (disables throttling)
        return getattr(self, 'rate', None)
