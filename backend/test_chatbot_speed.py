#!/usr/bin/env python3
"""
Test improved chatbot speed and memory accuracy
"""
import os
import sys
import django
import time

# Setup Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from authentication.chatbot_service import chatbot_service

def test_chatbot_speed():
    print("Testing Chatbot Speed and Memory Accuracy...")
    print("=" * 60)
    
    test_user_id = "speed_test_user"
    
    # Test 1: Product ID query
    print("🔍 Test 1: Product ID query")
    start_time = time.time()
    result1 = chatbot_service.process_message("show me product 3", user_id=test_user_id)
    end_time = time.time()
    print(f"⏱️  Response time: {end_time - start_time:.2f} seconds")
    print(f"📝 Intent: {result1['intent']}")
    print(f"💬 Response preview: {result1['response'][:100]}...")
    
    # Test 2: Product search
    print("\n🔍 Test 2: Product search")
    start_time = time.time()
    result2 = chatbot_service.process_message("wireless bluetooth headphones", user_id=test_user_id)
    end_time = time.time()
    print(f"⏱️  Response time: {end_time - start_time:.2f} seconds")
    print(f"📝 Intent: {result2['intent']}")
    print(f"💬 Response preview: {result2['response'][:100]}...")
    
    # Test 3: General chat
    print("\n🔍 Test 3: General chat")
    start_time = time.time()
    result3 = chatbot_service.process_message("hello how are you", user_id=test_user_id)
    end_time = time.time()
    print(f"⏱️  Response time: {end_time - start_time:.2f} seconds")
    print(f"📝 Intent: {result3['intent']}")
    print(f"💬 Response preview: {result3['response'][:100]}...")
    
    # Test 4: Another product ID to test memory
    print("\n🔍 Test 4: Another product ID (testing memory)")
    start_time = time.time()
    result4 = chatbot_service.process_message("show me product 5", user_id=test_user_id)
    end_time = time.time()
    print(f"⏱️  Response time: {end_time - start_time:.2f} seconds")
    print(f"📝 Intent: {result4['intent']}")
    print(f"💬 Response preview: {result4['response'][:100]}...")
    
    print("\n" + "=" * 60)
    print("✅ Speed test completed!")
    print("🚀 All responses should be under 10 seconds")
    print("🧠 Memory should store correct product IDs")

if __name__ == "__main__":
    test_chatbot_speed()
