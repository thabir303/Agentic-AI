#!/usr/bin/env python3

import os
import sys
import django

# Setup Django
sys.path.append('/home/bs01127/Agentic-AI/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from authentication.chatbot_service import markdown_to_text

def test_markdown_conversion():
    """Test markdown to text conversion"""
    
    test_cases = [
        # Test case 1: Bold text
        {
            'input': '**This is bold text** and this is normal text.',
            'expected': 'This is bold text and this is normal text.'
        },
        # Test case 2: Italic text
        {
            'input': '*This is italic text* and this is normal text.',
            'expected': 'This is italic text and this is normal text.'
        },
        # Test case 3: Links
        {
            'input': 'Check out [this product](http://localhost:5173/products/1) for more details.',
            'expected': 'Check out this product for more details.'
        },
        # Test case 4: Headers
        {
            'input': '### Product Features\nThis product has amazing features.',
            'expected': 'Product Features\nThis product has amazing features.'
        },
        # Test case 5: Code blocks
        {
            'input': 'Here is some code: ```python\nprint("hello")\n```',
            'expected': 'Here is some code: '
        },
        # Test case 6: Inline code
        {
            'input': 'Use the `search` function to find products.',
            'expected': 'Use the search function to find products.'
        },
        # Test case 7: Mixed formatting
        {
            'input': '**Product Name:** *Wireless Headphones*\n\n### Features:\n- **Noise Cancelling**\n- *Long Battery Life*\n\nCheck [product page](http://localhost:5173/products/123) for details.',
            'expected': 'Product Name: Wireless Headphones\n\nFeatures:\n- Noise Cancelling\n- Long Battery Life\n\nCheck product page for details.'
        }
    ]
    
    print("Testing markdown to text conversion...\n")
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"Test Case {i}:")
        print(f"Input: {repr(test_case['input'])}")
        
        result = markdown_to_text(test_case['input'])
        print(f"Output: {repr(result)}")
        print(f"Expected: {repr(test_case['expected'])}")
        
        # Check if conversion worked (basic check)
        if '**' not in result and '*' not in result and '```' not in result and '`' not in result:
            print("✅ Markdown formatting removed successfully")
        else:
            print("❌ Some markdown formatting still present")
        
        print("-" * 80)

if __name__ == "__main__":
    test_markdown_conversion()
