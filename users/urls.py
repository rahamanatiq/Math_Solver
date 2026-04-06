from django.urls import path
from .views import (
    RegisterView, 
    VerifyEmailView, 
    LoginView, 
    RequestPasswordResetView, 
    VerifyPasswordResetOTPView, 
    SetNewPasswordView,
    UserProfileView,
    TermsPrivacyView,
    LogoutView,
    ResendOTPView,
    GoogleLoginView,
)
from rest_framework_simplejwt.views import (
    TokenRefreshView,
)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('verify-email/', VerifyEmailView.as_view(), name='verify-email'),
    path('login/', LoginView.as_view(), name='login'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('password-reset/', RequestPasswordResetView.as_view(), name='password-reset'),
    path('password-reset/verify/', VerifyPasswordResetOTPView.as_view(), name='password-reset-verify'),
    path('password-reset/confirm/', SetNewPasswordView.as_view(), name='password-reset-confirm'),
    path('profile/', UserProfileView.as_view(), name='profile'),
    path('terms-privacy/', TermsPrivacyView.as_view(), name='terms-privacy'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('resend-otp/', ResendOTPView.as_view(), name='resend-otp'),
    path('google-login/', GoogleLoginView.as_view(), name='google-login'),
]
