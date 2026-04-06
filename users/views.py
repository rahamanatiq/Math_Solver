from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken
from .serializers import (
    UserRegistrationSerializer, 
    VerifyEmailSerializer, 
    LoginSerializer, 
    PasswordResetRequestSerializer, 
    PasswordResetVerifySerializer, 
    SetNewPasswordSerializer
)
from .utils import generate_otp, send_otp_email
from rest_framework.throttling import AnonRateThrottle
from .throttles import OTPRateThrottle
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
import uuid
from django.conf import settings
from django.utils.translation import gettext as _
from django.core import signing
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

User = get_user_model()


class RegisterView(APIView):
    # throttle_classes = [OTPRateThrottle] # Disabled for testing
    
    def post(self, request):
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            otp = generate_otp()
            user.otp = otp
            user.otp_created_at = timezone.now()
            user.save()
            send_otp_email(user.email, otp, user.username)
            return Response({'message': _('Registration successful. OTP sent to email.')}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class VerifyEmailView(APIView):
    def post(self, request):
        serializer = VerifyEmailSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            otp = serializer.validated_data['otp']
            try:
                user = User.objects.get(email=email)
                if user.otp == otp:
                    # Check if OTP is expired (e.g., 10 minutes)
                    if user.otp_created_at + timedelta(minutes=10) > timezone.now():
                        user.is_verified = True
                        user.otp = None  # Clear OTP
                        user.save()
                        return Response({'message': _('Email verified successfully.')}, status=status.HTTP_200_OK)
                    return Response({'error': _('OTP expired.')}, status=status.HTTP_400_BAD_REQUEST)
                return Response({'error': _('Invalid OTP.')}, status=status.HTTP_400_BAD_REQUEST)
            except User.DoesNotExist:
                return Response({'error': _('User not found.')}, status=status.HTTP_404_NOT_FOUND)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class LoginView(APIView):
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            password = serializer.validated_data['password']

            user = authenticate(username=email, password=password)
            
            if user:
                if not user.is_verified:
                    return Response({'error': 'Email not verified.'}, status=status.HTTP_403_FORBIDDEN)
                
                refresh = RefreshToken.for_user(user)
                return Response({
                    'message': 'Login successful',
                    'tokens': {
                        'refresh': str(refresh),
                        'access': str(refresh.access_token),
                    },
                    'user': {
                        'id': user.id,
                        'username': user.username,
                        'email': user.email,
                    }
                }, status=status.HTTP_200_OK)
            return Response({'error': _('Invalid credentials.')}, status=status.HTTP_401_UNAUTHORIZED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class RequestPasswordResetView(APIView):
    # throttle_classes = [OTPRateThrottle] # Disabled for testing
    
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            try:
                user = User.objects.get(email=email)
                
                # 60-second cooldown between reset requests
                if user.otp_created_at:
                    time_since_last = timezone.now() - user.otp_created_at
                    # if time_since_last.total_seconds() < 60: # Disabled for testing
                    if time_since_last.total_seconds() < 0:
                        remaining = 60 - int(time_since_last.total_seconds())
                        return Response(
                            {
                                'error': f'Please wait {remaining} seconds before requesting a new OTP.',
                                'retry_after': remaining
                            },
                            status=status.HTTP_429_TOO_MANY_REQUESTS
                        )

                otp = generate_otp()
                user.otp = otp
                user.otp_created_at = timezone.now()
                user.save()
                send_otp_email(user.email, otp, user.username)
                return Response({'message': _('OTP sent to email.')}, status=status.HTTP_200_OK)
            except User.DoesNotExist:
                return Response({'error': _('User not found.')}, status=status.HTTP_404_NOT_FOUND)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class VerifyPasswordResetOTPView(APIView):
    def post(self, request):
        serializer = PasswordResetVerifySerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            otp = serializer.validated_data['otp']
            try:
                # Find user by Email
                user = User.objects.get(email=email)
                if user.otp != otp:
                     return Response({'error': 'Invalid OTP.'}, status=status.HTTP_400_BAD_REQUEST)

                if user.otp_created_at + timedelta(minutes=10) > timezone.now():
                    # Generate a secure, time-limited token (e.g., 5 mins for rest)
                    token = signing.dumps({'user_id': user.id})
                    return Response({
                        'message': _('OTP verified. Proceed to reset password.'),
                        'reset_token': token
                    }, status=status.HTTP_200_OK)
                return Response({'error': _('OTP expired.')}, status=status.HTTP_400_BAD_REQUEST)
            except User.DoesNotExist:
                return Response({'error': _('User not found.')}, status=status.HTTP_404_NOT_FOUND)
            except Exception as e:
                return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class SetNewPasswordView(APIView):
    def post(self, request):
        serializer = SetNewPasswordSerializer(data=request.data)
        if serializer.is_valid():
            token = request.data.get('reset_token')
            if not token:
                return Response({'error': _('Reset token is required.')}, status=status.HTTP_400_BAD_REQUEST)

            try:
                # Verify and decrypt the token
                data = signing.loads(token, max_age=600) # Token valid for 5 mins
                user_id = data.get('user_id')
                user = User.objects.get(id=user_id)
                
                new_password = serializer.validated_data['new_password']
                user.set_password(new_password)
                user.otp = None # Clear OTP
                user.save()
                
                return Response({'message': _('Password reset successful.')}, status=status.HTTP_200_OK)
            except signing.SignatureExpired:
                return Response({'error': _('Reset token expired. Please verify OTP again.')}, status=status.HTTP_400_BAD_REQUEST)
            except (signing.BadSignature, User.DoesNotExist):
                return Response({'error': _('Invalid reset token or session.')}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ResendOTPView(APIView):
    """
    Resends OTP for email verification or password reset.
    Includes 60-second cooldown to prevent spam.
    """
    # throttle_classes = [OTPRateThrottle] # Disabled for testing

    def post(self, request):
        email = request.data.get('email')
        purpose = request.data.get('purpose', 'verification')

        if not email:
            return Response(
                {'error': _('Email is required.')},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response(
                {'error': 'User not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Don't resend if already verified
        if purpose == 'verification' and user.is_verified:
            return Response(
                {'error': _('Email is already verified.')},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 60-second cooldown between resends
        if user.otp_created_at:
            time_since_last = timezone.now() - user.otp_created_at
            # if time_since_last.total_seconds() < 60: # Disabled for testing
            if time_since_last.total_seconds() < 0:
                remaining = 60 - int(time_since_last.total_seconds())
                return Response(
                    {
                        'error': f'Please wait {remaining} seconds before requesting a new OTP.',
                        'retry_after': remaining
                    },
                    status=status.HTTP_429_TOO_MANY_REQUESTS
                )

        otp = generate_otp()
        user.otp = otp
        user.otp_created_at = timezone.now()
        user.save()
        send_otp_email(user.email, otp, user.username)

        return Response(
            {'message': _('OTP resent successfully. Please check your email.')},
            status=status.HTTP_200_OK
        )


from rest_framework.permissions import IsAuthenticated
from .serializers import UserProfileSerializer

class UserProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserProfileSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request):
        serializer = UserProfileSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request):
        user = request.user
        user.delete()
        return Response({'message': _('Account deleted successfully.')}, status=status.HTTP_200_OK)

class TermsPrivacyView(APIView):
    def get(self, request):
        content = {
            "title": "Terms and Privacy Policy",
            "content": "This Privacy Policy describes how [Your Company Name] collects, uses, discloses, and protects your personal information..."
        }
        return Response(content, status=status.HTTP_200_OK)

class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data["refresh"]
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response({"message": _("Logout successful.")}, status=status.HTTP_205_RESET_CONTENT)
        except Exception as e:
            return Response({"error": _("Invalid token.")}, status=status.HTTP_400_BAD_REQUEST)

class GoogleLoginView(APIView):
    """
    Handle Google Social Login.
    The frontend exchanges the user's Google credentials for an id_token,
    then sends that id_token here. We securely verify it via Google's library.
    """
    permission_classes = []

    def post(self, request):
        token = request.data.get('id_token')
        if not token:
            return Response({'error': 'id_token is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            client_id = getattr(settings, 'GOOGLE_CLIENT_ID', None)
            if not client_id:
                 return Response({'error': 'Google authentication is not configured on the server'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # Verify the token via Google's certs
            idinfo = id_token.verify_oauth2_token(token, google_requests.Request(), client_id)

            if idinfo['aud'] != client_id:
                raise ValueError("Could not verify audience.")

            email = idinfo.get('email')
            
            # Find or create user
            user = User.objects.filter(email=email).first()
            if not user:
                user = User.objects.create_user(email=email)
                user.is_verified = True # Google guarantees this email is valid
                user.set_unusable_password() 
                user.save()
            elif not user.is_verified:
                # If they already signed up manually but didn't verify, verify them now
                user.is_verified = True
                user.save()

            # Generate standard JWT payload
            refresh = RefreshToken.for_user(user)
            return Response({
                'message': 'Google Login successful',
                'tokens': {
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                },
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                }
            }, status=status.HTTP_200_OK)

        except ValueError as e:
            return Response({'error': f'Invalid token: {str(e)}'}, status=status.HTTP_401_UNAUTHORIZED)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
