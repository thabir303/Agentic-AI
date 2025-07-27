#!/usr/bin/env python3
"""
Simple test to check API availability
"""

import os
import sys

# Add backend to path
sys.path.append('/home/bs01127/Agentic-AI/backend')

# Load environment
import dotenv
dotenv.load_dotenv('/home/bs01127/Agentic-AI/.env')
dotenv.load_dotenv('/home/bs01127/Agentic-AI/backend/.env')

print("Environment Check:")
print(f"GROQ_API_KEY: {'Found' if os.getenv('GROQ_API_KEY') else 'Not found'}")
print(f"USE_LOCAL_FALLBACK: {os.getenv('USE_LOCAL_FALLBACK', 'Not set')}")

# Test Groq directly
print("\nTesting Groq API directly...")
try:
    from groq import Groq
    
    groq_api_key = os.getenv('GROQ_API_KEY')
    if groq_api_key:
        client = Groq(api_key=groq_api_key)
        
        response = client.chat.completions.create(
            messages=[{"role": "user", "content": "Say 'API Working'"}],
            model="llama-3.3-70b-versatile",
            max_tokens=10,
            timeout=5
        )
        
        print(f"✅ Groq API Response: {response.choices[0].message.content}")
    else:
        print("❌ No Groq API key")
        
except Exception as e:
    print(f"❌ Groq API Error: {e}")

print("\nDone!")
