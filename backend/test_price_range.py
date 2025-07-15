#!/usr/bin/env python3

import os
import sys
import django
import json

# Setup Django
sys.path.append('/home/bs01127/Agentic-AI/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from authentication.chatbot_service import ChatbotService

def test_price_range_feature():
    """Test price range search feature"""
    
    print("🧪 Testing Price Range Search Feature\n")
    print("="*80)
    
    chatbot = ChatbotService()
    
    # Test cases for price range search
    test_messages = [
        "Show me products under $50",
        "I want something between $20 to $100",
        "Products cheaper than $30",
        "What's available in electronics under $200?",
        "Find me items from $50 to $150",
        "I have a budget of $75",
        "Show me products around $100",
        "Clothing items below $40"
    ]
    
    for i, message in enumerate(test_messages, 1):
        print(f"\n🔍 Test {i}: '{message}'")
        print("-" * 60)
        
        try:
            # Test intent detection
            intent = chatbot.detect_intent(message)
            print(f"📋 Detected Intent: {intent}")
            
            # Test price range extraction
            price_range = chatbot.extract_price_range_from_message(message)
            print(f"💰 Extracted Price Range: {price_range}")
            
            # Test full response
            response = chatbot.process_message(message, user_id=1)
            
            print(f"🤖 Bot Response:")
            print(response['response'])
            
            if 'products' in response and response['products']:
                print(f"\n📦 Found {len(response['products'])} products:")
                for j, product in enumerate(response['products'][:3], 1):
                    print(f"   {j}. {product['name']} - ${product['price']} ({product['category']})")
            
        except Exception as e:
            print(f"❌ Error: {e}")
        
        print("\n" + "="*80)

def test_price_range_extraction():
    """Test price range extraction patterns"""
    
    print("\n🔧 Testing Price Range Extraction Patterns\n")
    
    chatbot = ChatbotService()
    
    test_patterns = [
        ("under $50", (0, 50)),
        ("below $30", (0, 30)),
        ("less than $100", (0, 100)),
        ("between $20 and $80", (20, 80)),
        ("$25 to $75", (25, 75)),
        ("from $30 to $120", (30, 120)),
        ("budget of $60", (0, 60)),
        ("around $90", (40, 140)),  # around +/- 50
        ("price range $200", (0, 200))
    ]
    
    for pattern, expected in test_patterns:
        result = chatbot.extract_price_range_from_message(pattern)
        status = "✅" if result == expected else "❌"
        print(f"{status} '{pattern}' → {result} (expected: {expected})")

if __name__ == "__main__":
    test_price_range_extraction()
    test_price_range_feature()
