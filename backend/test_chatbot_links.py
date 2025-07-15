#!/usr/bin/env python3

import os
import sys
import django
import requests

# Setup Django
sys.path.append('/home/bs01127/Agentic-AI/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from authentication.models import User
from rest_framework_simplejwt.tokens import RefreshToken

def test_chatbot_links():
    """Test chatbot with real authentication to check link generation"""
    
    print("🧪 Testing Chatbot Link Generation\n")
    
    # Get or create test user
    try:
        user, created = User.objects.get_or_create(
            username='linktest',
            defaults={
                'email': 'linktest@example.com',
                'first_name': 'Link',
                'last_name': 'Test'
            }
        )
        
        if created:
            user.set_password('testpass123')
            user.save()
            print(f"✅ Created test user: {user.username}")
        else:
            print(f"✅ Using existing test user: {user.username}")
        
        # Generate JWT token
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
        }
        
        # Test a query that should generate product links
        test_message = "show me products under $50"
        
        print(f"🔍 Testing message: '{test_message}'")
        print("-" * 60)
        
        response = requests.post(
            'http://localhost:8000/auth/chatbot/',
            headers=headers,
            json={'message': test_message},
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            bot_response = data.get('response', '')
            
            print("✅ Bot Response:")
            print(bot_response)
            print("\n" + "="*60)
            
            # Check for product links
            import re
            links = re.findall(r'http://localhost:5173/products/(\d+)', bot_response)
            
            if links:
                print(f"🔗 Found {len(links)} product links:")
                for i, product_id in enumerate(links, 1):
                    print(f"   {i}. Product ID: {product_id}")
                    print(f"      URL: http://localhost:5173/products/{product_id}")
                print("\n✅ Links are properly formatted for frontend parsing!")
            else:
                print("❌ No product links found in response")
                
        else:
            print(f"❌ Request failed: {response.status_code}")
            print(f"Response: {response.text}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_chatbot_links()
