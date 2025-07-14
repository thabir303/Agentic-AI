#!/usr/bin/env python3
"""
Test Pure Embedding-Based Chatbot
Tests the new approach where all product queries use vector search
"""

import requests
import json
import time

BASE_URL = "http://localhost:8000"

def test_embedding_search(query, description):
    """Test a query using the pure embedding approach"""
    print(f"\n{'='*60}")
    print(f"Test: {description}")
    print(f"Query: '{query}'")
    print(f"{'='*60}")
    
    try:
        # First create a test user session (simulate login)
        auth_data = {
            "username": "testuser",
            "password": "testpass123"
        }
        
        # Test the chatbot endpoint (assuming authentication will be handled)
        payload = {"message": query}
        
        response = requests.post(
            f"{BASE_URL}/chatbot/",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ SUCCESS")
            print(f"Response: {result.get('response', 'No response')[:500]}...")
        else:
            print(f"❌ FAILED - Status: {response.status_code}")
            print(f"Error: {response.text[:200]}...")
            
    except Exception as e:
        print(f"❌ ERROR: {e}")
    
    time.sleep(1)  # Brief delay between tests

def main():
    print("🧪 Testing Pure Embedding-Based Chatbot Approach")
    print("=" * 70)
    
    # Test cases for different scenarios
    test_cases = [
        # 1. Simple product searches (should use embedding)
        ("show me laptops", "Simple laptop search using embedding"),
        ("I need phones", "Phone search using embedding"),
        ("gaming headsets", "Gaming headset search"),
        
        # 2. Queries with numbers that should NOT be treated as product IDs
        ("I want 5 laptops", "Number in query (should NOT treat 5 as product ID)"),
        ("Show me 10 phones", "Number in query (should NOT treat 10 as product ID)"),
        ("Need 3 tablets", "Number in query (should NOT treat 3 as product ID)"),
        
        # 3. Specific requests that should use embedding search
        ("cheap electronics", "Price-based search using embedding"),
        ("wireless accessories", "Feature-based search"),
        ("books about history", "Category-based search"),
        
        # 4. More complex semantic searches
        ("something for fitness", "Semantic search for fitness products"),
        ("items for cooking", "Semantic search for cooking items"),
        ("gadgets for home", "Semantic search for home gadgets"),
        
        # 5. Contextual queries (after getting some results)
        ("what about bluetooth devices", "Bluetooth device search"),
        ("tell me more about that", "Contextual reference query"),
        
        # 6. Issue reporting (should still work)
        ("I have a problem with my order", "Issue reporting test"),
    ]
    
    for query, description in test_cases:
        test_embedding_search(query, description)
    
    print(f"\n{'='*70}")
    print("🏁 Testing Complete!")
    print("Key things to verify:")
    print("✅ All product searches use embedding/vector search")
    print("✅ Numbers in queries are NOT treated as product IDs")
    print("✅ Responses include actual product information with links")
    print("✅ No false positive product ID detection")
    print("✅ Semantic understanding works properly")
    print("=" * 70)

if __name__ == "__main__":
    main()
