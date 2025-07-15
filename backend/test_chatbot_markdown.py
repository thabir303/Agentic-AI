#!/usr/bin/env python3

import os
import sys
import django
import json
import requests

# Setup Django
sys.path.append('/home/bs01127/Agentic-AI/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from authentication.models import User
from rest_framework_simplejwt.tokens import RefreshToken

def get_auth_token():
    """Get authentication token for testing"""
    try:
        # Try to get existing user or create one
        user, created = User.objects.get_or_create(
            username='testuser',
            defaults={
                'email': 'test@example.com',
                'first_name': 'Test',
                'last_name': 'User'
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
        print(f"✅ Generated access token")
        
        return access_token
    except Exception as e:
        print(f"❌ Error getting auth token: {e}")
        return None

def test_chatbot_with_auth():
    """Test chatbot interaction with authentication"""
    
    # Get auth token
    token = get_auth_token()
    if not token:
        print("❌ Could not get authentication token")
        return
    
    # Test messages that might produce markdown from LLM
    test_messages = [
        "Tell me about wireless headphones",
        "Show me product ID 1",
        "I need help with electronics",
        "What are the best products in the Electronics category?"
    ]
    
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    }
    
    print("Testing chatbot responses for markdown to text conversion...\n")
    
    for i, message in enumerate(test_messages, 1):
        print(f"Test {i}: '{message}'")
        print("-" * 50)
        
        try:
            # Send request to chatbot
            response = requests.post(
                'http://localhost:8000/auth/chatbot/',
                headers=headers,
                json={'message': message},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                bot_response = data.get('response', '')
                
                print(f"✅ Response received:")
                print(f"Response: {bot_response}")
                
                # Check for markdown formatting
                markdown_indicators = ['**', '*', '```', '`', '[', '](#', '###', '##', '#']
                has_markdown = any(indicator in bot_response for indicator in markdown_indicators)
                
                if has_markdown:
                    print("⚠️  Response still contains markdown formatting")
                    print("Markdown indicators found:", [ind for ind in markdown_indicators if ind in bot_response])
                else:
                    print("✅ Response is in plain text format")
                
                # Check for product links
                if 'http://localhost:5173/products/' in bot_response:
                    print("✅ Product links preserved")
                
            else:
                print(f"❌ Request failed: {response.status_code}")
                print(f"Response: {response.text}")
        
        except Exception as e:
            print(f"❌ Error: {e}")
        
        print("\n" + "="*80 + "\n")

if __name__ == "__main__":
    test_chatbot_with_auth()
