#!/usr/bin/env python
"""
Test script to verify API endpoints
"""
import requests
import json

BASE_URL = "http://127.0.0.1:8000"

def test_endpoints():
    """Test basic API endpoint connectivity"""
    
    # Test signup
    print("Testing signup...")
    signup_data = {
        "email": "test@example.com",
        "password": "testpass123",
        "first_name": "Test",
        "last_name": "User"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/auth/signup/", json=signup_data)
        print(f"Signup status: {response.status_code}")
        if response.status_code == 201:
            print("✅ Signup successful")
            signup_response = response.json()
            token = signup_response.get('access')
        else:
            print(f"❌ Signup failed: {response.text}")
            # Try signin instead
            print("Trying signin...")
            signin_data = {
                "email": "test@example.com",
                "password": "testpass123"
            }
            response = requests.post(f"{BASE_URL}/auth/signin/", json=signin_data)
            print(f"Signin status: {response.status_code}")
            if response.status_code == 200:
                print("✅ Signin successful")
                signup_response = response.json()
                token = signup_response.get('access')
            else:
                print(f"❌ Signin failed: {response.text}")
                return
    except Exception as e:
        print(f"❌ Authentication error: {e}")
        return
    
    # Set up headers with token
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test products endpoint
    print("\nTesting products endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/auth/products/", headers=headers)
        print(f"Products status: {response.status_code}")
        if response.status_code == 200:
            print("✅ Products endpoint working")
            products_data = response.json()
            print(f"Found {len(products_data.get('products', []))} products")
        else:
            print(f"❌ Products failed: {response.text}")
    except Exception as e:
        print(f"❌ Products error: {e}")
    
    # Test categories endpoint
    print("\nTesting categories endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/auth/categories/", headers=headers)
        print(f"Categories status: {response.status_code}")
        if response.status_code == 200:
            print("✅ Categories endpoint working")
            categories_data = response.json()
            print(f"Found categories: {categories_data.get('categories', [])}")
        else:
            print(f"❌ Categories failed: {response.text}")
    except Exception as e:
        print(f"❌ Categories error: {e}")
    
    # Test chatbot endpoint
    print("\nTesting chatbot endpoint...")
    try:
        chatbot_data = {"message": "Hello, can you help me find products?"}
        response = requests.post(f"{BASE_URL}/auth/chatbot/", json=chatbot_data, headers=headers)
        print(f"Chatbot status: {response.status_code}")
        if response.status_code == 200:
            print("✅ Chatbot endpoint working")
            chatbot_response = response.json()
            print(f"Bot response: {chatbot_response.get('response', 'No response')}")
        else:
            print(f"❌ Chatbot failed: {response.text}")
    except Exception as e:
        print(f"❌ Chatbot error: {e}")

if __name__ == "__main__":
    print("🚀 Testing API endpoints...")
    test_endpoints()
    print("\n✨ Test complete!")
