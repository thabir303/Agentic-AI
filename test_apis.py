#!/usr/bin/env python3
"""
Test script for the Agentic AI platform APIs
"""
import os
import sys
import django
import requests
import json
from pathlib import Path

# Add the backend directory to Python path
backend_dir = Path(__file__).parent / 'backend'
sys.path.insert(0, str(backend_dir))

# Configure Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

BASE_URL = 'http://127.0.0.1:8000'

def test_api_endpoints():
    """Test various API endpoints"""
    print("🚀 Testing Agentic AI Platform APIs")
    print("=" * 50)
    
    # Test 1: Register a new user
    print("1️⃣  Testing user registration...")
    try:
        register_data = {
            'username': 'testuser',
            'email': 'test@example.com',
            'password': 'testpass123',
            'password2': 'testpass123'
        }
        
        response = requests.post(f'{BASE_URL}/auth/register/', json=register_data)
        if response.status_code == 201:
            print("✅ User registration successful")
            user_data = response.json()
            access_token = user_data.get('access')
        else:
            print(f"❌ Registration failed: {response.status_code}")
            # Try login instead
            login_data = {'username': 'testuser', 'password': 'testpass123'}
            response = requests.post(f'{BASE_URL}/auth/login/', json=login_data)
            if response.status_code == 200:
                print("✅ Login successful")
                user_data = response.json()
                access_token = user_data.get('access')
            else:
                print("❌ Both registration and login failed")
                return
    except Exception as e:
        print(f"❌ Registration/Login error: {e}")
        return
    
    # Headers for authenticated requests
    headers = {'Authorization': f'Bearer {access_token}'} if access_token else {}
    
    # Test 2: Get categories
    print("\n2️⃣  Testing categories endpoint...")
    try:
        response = requests.get(f'{BASE_URL}/categories/', headers=headers)
        if response.status_code == 200:
            categories = response.json().get('categories', [])
            print(f"✅ Categories retrieved: {categories}")
        else:
            print(f"❌ Categories failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Categories error: {e}")
    
    # Test 3: Get products
    print("\n3️⃣  Testing products endpoint...")
    try:
        response = requests.get(f'{BASE_URL}/products/', headers=headers)
        if response.status_code == 200:
            products_data = response.json()
            products = products_data.get('products', [])
            print(f"✅ Products retrieved: {len(products)} products found")
            if products:
                print(f"📱 First product: {products[0].get('name', 'N/A')}")
        else:
            print(f"❌ Products failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Products error: {e}")
    
    # Test 4: Search products
    print("\n4️⃣  Testing product search...")
    try:
        response = requests.get(f'{BASE_URL}/products/?search=wireless', headers=headers)
        if response.status_code == 200:
            products_data = response.json()
            products = products_data.get('products', [])
            print(f"✅ Search results: {len(products)} products found for 'wireless'")
        else:
            print(f"❌ Search failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Search error: {e}")
    
    # Test 5: Get specific product
    print("\n5️⃣  Testing specific product endpoint...")
    try:
        response = requests.get(f'{BASE_URL}/products/1/', headers=headers)
        if response.status_code == 200:
            product_data = response.json()
            product = product_data.get('product', {})
            similar = product_data.get('similar_products', [])
            print(f"✅ Product detail retrieved: {product.get('name', 'N/A')}")
            print(f"Similar products: {len(similar)} found")
        else:
            print(f"❌ Product detail failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Product detail error: {e}")
    
    # Test 6: Test chatbot
    print("\n6️⃣  Testing chatbot endpoint...")
    try:
        chatbot_data = {'message': 'Hello, can you help me find wireless headphones?'}
        response = requests.post(f'{BASE_URL}/chatbot/', json=chatbot_data, headers=headers)
        if response.status_code == 200:
            chatbot_response = response.json()
            print(f"✅ Chatbot response received")
            print(f"🤖 Response: {chatbot_response.get('response', 'N/A')[:100]}...")
            print(f"🎯 Intent: {chatbot_response.get('intent', 'N/A')}")
        else:
            print(f"❌ Chatbot failed: {response.status_code}")
            print(f"Response: {response.text}")
    except Exception as e:
        print(f"❌ Chatbot error: {e}")
    
    print("\n" + "=" * 50)
    print("🎉 API testing completed!")

if __name__ == '__main__':
    test_api_endpoints()
