from rest_framework import serializers
from .models import User
from django.contrib.auth import authenticate
from django.conf import settings
from django.db import models

class UserSignupSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('username', 'email', 'password')
        extra_kwargs = {'password': {'write_only': True}}

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password'],
            role='customer'
        )
        return user

class UserSigninSerializer(serializers.Serializer):
    identifier = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        identifier = data['identifier']
        password = data['password']
        admin_email = settings.ADMIN_EMAIL
        admin_password = settings.ADMIN_PASSWORD
        
        # Check for hardcoded admin credentials
        if identifier == admin_email and password == admin_password:
            # Try to get existing admin user first
            try:
                user = User.objects.get(email=admin_email)
                return user
            except User.DoesNotExist:
                # Create new admin user if doesn't exist
                try:
                    user = User.objects.create_user(
                        username='admin',
                        email=admin_email,
                        password=admin_password,
                        role='admin'
                    )
                    user.is_staff = True
                    user.is_superuser = True
                    user.save()
                    return user
                except:
                    # If username 'admin' exists, try with email as username
                    user = User.objects.create_user(
                        username=admin_email,
                        email=admin_email,
                        password=admin_password,
                        role='admin'
                    )
                    user.is_staff = True
                    user.is_superuser = True
                    user.save()
                    return user
        
        # Customer login by username or email
        user = User.objects.filter(role='customer').filter(
            models.Q(username=identifier) | models.Q(email=identifier)
        ).first()
        if user and user.check_password(password):
            return user
        raise serializers.ValidationError('Invalid credentials.')
