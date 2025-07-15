#!/usr/bin/env python3
"""
Make a user admin
"""
import os
import sys
import django

# Setup Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from authentication.models import User

def make_admin():
    # Find a user and make them admin
    users = User.objects.all()
    if users:
        user = users.first()
        user.role = 'admin'
        user.save()
        print(f"✅ Made user '{user.username}' an admin")
        print(f"✅ User ID: {user.id}, Email: {user.email}")
    else:
        print("❌ No users found")

if __name__ == "__main__":
    make_admin()
