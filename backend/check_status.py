#!/usr/bin/env python3
"""
Check issues and admin status
"""
import os
import sys
import django

# Setup Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from authentication.models import User, Issue

def check_status():
    print("=== Database Status ===")
    print(f"Total Users: {User.objects.count()}")
    print(f"Total Issues: {Issue.objects.count()}")
    
    print("\n=== User Roles ===")
    for user in User.objects.all():
        print(f"👤 {user.username} ({user.email}) - Role: {user.role}")
    
    print("\n=== Sample Issues ===")
    for issue in Issue.objects.all()[:5]:
        print(f"🎫 Issue #{issue.id}: {issue.username} - {issue.message[:60]}...")
    
    # Create a test issue if none exist
    if Issue.objects.count() == 0:
        Issue.objects.create(
            username="TestUser",
            email="test@example.com",
            message="This is a test issue to verify the admin panel is working correctly.",
            status="pending"
        )
        print("\n✅ Created a test issue")

if __name__ == "__main__":
    check_status()
