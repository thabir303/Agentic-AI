from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from django.conf import settings
from .models import User
import logging

logger = logging.getLogger(__name__)

class SignupView(APIView):
    def post(self, request):
        try:
            username = request.data.get('username')
            email = request.data.get('email')
            password = request.data.get('password')
            
            # Validation
            if not all([username, email, password]):
                return Response({
                    'message': 'All fields are required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Check if user already exists
            if User.objects.filter(email=email).exists():
                return Response({
                    'message': 'User with this email already exists'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if User.objects.filter(username=username).exists():
                return Response({
                    'message': 'Username already taken'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Create user
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password
            )
            
            # Generate tokens
            refresh = RefreshToken.for_user(user)
            
            return Response({
                'message': 'User created successfully',
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'role': user.role
                }
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"Signup error: {e}")
            return Response({
                'message': 'Registration failed. Please try again.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class SigninView(APIView):
    def post(self, request):
        try:
            identifier = request.data.get('identifier')  # email or username
            password = request.data.get('password')
            
            if not all([identifier, password]):
                return Response({
                    'message': 'Email/username and password are required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Try to find user by email or username
            user = None
            if '@' in identifier:
                try:
                    user = User.objects.get(email=identifier)
                except User.DoesNotExist:
                    pass
            else:
                try:
                    user = User.objects.get(username=identifier)
                except User.DoesNotExist:
                    pass
            
            if user and user.check_password(password):
                # Generate tokens
                refresh = RefreshToken.for_user(user)
                
                return Response({
                    'message': 'Login successful',
                    'access': str(refresh.access_token),
                    'refresh': str(refresh),
                    'user': {
                        'id': user.id,
                        'username': user.username,
                        'email': user.email,
                        'role': user.role
                    }
                })
            else:
                return Response({
                    'message': 'Invalid credentials'
                }, status=status.HTTP_401_UNAUTHORIZED)
                
        except Exception as e:
            logger.error(f"Login error: {e}")
            return Response({
                'message': 'Login failed. Please try again.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class ProfileView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        user = request.user
        return Response({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'role': user.role
        })
