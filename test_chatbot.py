#!/usr/bin/env python3
"""
Test the enhanced chatbot functionality
"""
import os
import sys
import django
from pathlib import Path

# Add the backend directory to Python path
backend_dir = Path(__file__).parent / 'backend'
sys.path.insert(0, str(backend_dir))

# Configure Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from authentication.chatbot_service import chatbot_service

def test_chatbot():
    print("🤖 Testing Enhanced Chatbot Functionality")
    print("=" * 50)
    
    test_cases = [
        "show me product 3",
        "give me product id 1", 
        "product 5",
        "I want to see product number 10",
        "wireless earbuds",
        "show me electronics",
        "I have a problem with my order"
    ]
    
    for i, message in enumerate(test_cases, 1):
        print(f"\n{i}️⃣  Test: '{message}'")
        print("-" * 30)
        
        try:
            result = chatbot_service.process_message(message)
            print(f"Intent: {result.get('intent', 'unknown')}")
            print(f"Response: {result.get('response', 'No response')[:200]}...")
            
            if result.get('products'):
                print(f"Products found: {len(result['products'])}")
                for product in result['products'][:2]:
                    print(f"  - {product.get('name', 'Unknown')} (ID: {product.get('id', 'N/A')})")
                    
        except Exception as e:
            print(f"Error: {e}")
    
    print("\n" + "=" * 50)
    print("✅ Chatbot testing completed!")

if __name__ == '__main__':
    test_chatbot()
