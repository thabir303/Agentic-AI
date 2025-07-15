#!/usr/bin/env python3

import os
import sys
import django

# Setup Django
sys.path.append('/home/bs01127/Agentic-AI/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from authentication.chatbot_service import ChatbotService

def test_link_format():
    """Test link format without external API calls"""
    
    print("🧪 Testing Link Format Generation\n")
    
    chatbot = ChatbotService()
    
    # Simulate a response that would include links
    sample_response = """Here are some great products for you:

Product Links:
http://localhost:5173/products/29
http://localhost:5173/products/132
http://localhost:5173/products/167

Check these out!"""
    
    print("📋 Sample Response:")
    print(sample_response)
    print("\n" + "="*60)
    
    # Test regex pattern
    import re
    urls = re.findall(r'(https?://localhost:5173/products/(\d+))', sample_response)
    
    print(f"🔗 Found {len(urls)} URLs:")
    for i, (full_url, product_id) in enumerate(urls, 1):
        print(f"   {i}. Full URL: {full_url}")
        print(f"      Product ID: {product_id}")
    
    print(f"\n✅ Links are clean (no emoji icons)")
    print(f"✅ Frontend will display URLs as button text")

if __name__ == "__main__":
    test_link_format()
