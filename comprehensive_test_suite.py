#!/usr/bin/env python3
"""
Comprehensive Test Suite for Agentic AI Chatbot
Category-wise queries + Memory context testing scenarios
"""

# All possible test queries organized by category and memory scenarios

class AgenticAITestSuite:
    
    @staticmethod
    def get_product_search_queries():
        """Category-wise product search queries"""
        return {
            "Electronics": [
                "Show me the latest smartphones",
                "Do you have any wireless earbuds?", 
                "Suggest a good quality smart LED TV",
                "Find me bluetooth speakers under $100",
                "I need a wireless gaming mouse",
                "Show me laptops for students"
            ],
            
            "Home & Kitchen": [
                "I need a set of mixing bowls",
                "Show me non-stick frying pans", 
                "Find glass food storage containers",
                "Suggest kitchen knives under $50",
                "I want stainless steel cookware",
                "Show me coffee makers"
            ],
            
            "Clothing": [
                "Show me men's running shoes",
                "Do you have classic denim jackets?",
                "Suggest some affordable t-shirts", 
                "Find winter coats under $100",
                "I need formal dress shirts",
                "Show me casual sneakers"
            ],
            
            "Books": [
                "Recommend a good sci-fi novel",
                "Find children's picture books",
                "Show me cookbooks for beginners",
                "I want mystery thriller books",
                "Suggest self-help books under $20",
                "Find educational books for kids"
            ],
            
            "Toys & Games": [
                "Show me remote control cars", 
                "Find building block sets for kids",
                "Suggest educational toys under $30",
                "I need board games for family",
                "Show me action figures",
                "Find puzzle games for children"
            ]
        }
    
    @staticmethod
    def get_price_range_queries():
        """Price range and budget queries"""
        return [
            # Under/Below patterns
            "Show me all the earbuds you have less than $50",
            "Suggest wireless gaming mouse under 40 dollars", 
            "Find products below $25",
            "I want headphones under $100",
            
            # Greater than patterns  
            "Show me laptops above $500",
            "Find phones over $300",
            "I need something more than 200 dollars",
            "Products greater than $150",
            
            # Around patterns
            "Something around $100",
            "Products approximately $75", 
            "I want items about $50",
            "Around 250 dollar budget",
            
            # Between patterns
            "Find smart LED TVs between $200 and $400",
            "Products from $50 to $150",
            "Something between 100 to 300 dollars",
            
            # Budget patterns
            "My budget is under $30",
            "Budget of $200",
            "I can spend up to $500",
            "Maximum 150 dollars",
            "Price limit is $80"
        ]
    
    @staticmethod
    def get_category_browse_queries():
        """Category browsing queries"""
        return [
            "Browse electronics",
            "Show me home and kitchen items", 
            "Explore clothing category",
            "What categories do you have?",
            "Browse books section",
            "Show toys and games",
            "Electronics category",
            "Kitchen items browse"
        ]
    
    @staticmethod
    def get_product_specific_queries():
        """Product-specific ID queries"""
        return [
            "Show me product ID 6",
            "Product number 3 details",
            "Give me product 10", 
            "Show me details about product 132",
            "Product 25 information",
            "Find product ID 45",
            "Product number 78 details"
        ]
    
    @staticmethod 
    def get_general_chat_queries():
        """General chat and personalization queries"""
        return [
            "Hello!",
            "Hi there",
            "Good morning",
            "What can you do?",
            "How does this work?", 
            "What's my name?",
            "Who am I?",
            "What's your name?",
            "Thank you",
            "Thanks for your help",
            "How are you?",
            "Can you help me?",
            "What are your capabilities?"
        ]
    
    @staticmethod
    def get_issue_report_queries():
        """Issue reporting queries"""
        return [
            "My order is missing",
            "I have a problem with my purchase",
            "The product doesn't work",
            "Can you help me with a complaint?",
            "Item was damaged when delivered", 
            "Wrong product was sent",
            "Refund request for order",
            "Product quality issue",
            "Shipping problem"
        ]
    
    @staticmethod
    def get_memory_context_scenarios():
        """Connected conversation scenarios for memory testing"""
        return {
            "Gift Scenario": [
                "I want to buy a gift for my sister",
                "She likes books and jewelry", 
                "My budget is under $30",
                "Can you show me the best options?"
            ],
            
            "TV Shopping": [
                "Suggest me some good quality smart LED TV",
                "But my budget is 200 dollar",
                "I want to mean under $200", 
                "Show me more options in that price range"
            ],
            
            "Earbuds Search": [
                "Show me all the earbuds you have less than $50",
                "Which one is best for sports?",
                "Can you show me more details about the first product?",
                "Do you have wireless options?"
            ],
            
            "Kitchen Shopping": [
                "I need kitchen items for my new apartment",
                "Looking for basic cooking essentials",
                "My budget is around $150", 
                "Show me the most important items first"
            ],
            
            "Student Laptop": [
                "I need a laptop for my college studies", 
                "Budget is between $400 to $600",
                "It should be good for programming",
                "Show me the best options"
            ],
            
            "General Context": [
                "Hello!",
                "Can you remember my previous searches?",
                "Show me something similar to what I searched before",
                "What did I ask about last time?"
            ],
            
            "Clothing Style": [
                "I'm looking for casual wear",
                "Something comfortable for daily use", 
                "Price range under $80",
                "Show me t-shirts and jeans"
            ],
            
            "Home Decor": [
                "I want to decorate my living room",
                "Need some affordable items",
                "Budget is maximum $200",
                "Show me decorative pieces"
            ]
        }
    
    @staticmethod
    def get_all_test_categories():
        """Get all test categories for systematic testing"""
        return {
            "Product Search (Category-wise)": AgenticAITestSuite.get_product_search_queries(),
            "Price Range Queries": AgenticAITestSuite.get_price_range_queries(), 
            "Category Browse": AgenticAITestSuite.get_category_browse_queries(),
            "Product Specific": AgenticAITestSuite.get_product_specific_queries(),
            "General Chat": AgenticAITestSuite.get_general_chat_queries(),
            "Issue Reporting": AgenticAITestSuite.get_issue_report_queries(),
            "Memory Context Scenarios": AgenticAITestSuite.get_memory_context_scenarios()
        }
    
    @staticmethod
    def print_all_test_queries():
        """Print all test queries in organized format"""
        print("🤖 AGENTIC AI CHATBOT - COMPREHENSIVE TEST SUITE")
        print("=" * 70)
        
        test_categories = AgenticAITestSuite.get_all_test_categories()
        
        for category, queries in test_categories.items():
            print(f"\n📂 {category.upper()}")
            print("-" * 50)
            
            if isinstance(queries, dict):
                # Handle nested categories (like product search)
                for subcategory, subqueries in queries.items():
                    print(f"\n  📋 {subcategory}:")
                    for i, query in enumerate(subqueries, 1):
                        print(f"    {i}. {query}")
            elif isinstance(queries, list):
                # Handle simple list queries
                for i, query in enumerate(queries, 1):
                    print(f"  {i}. {query}")
        
        print("\n" + "=" * 70)
        print("🎯 Total test scenarios ready for comprehensive testing!")

# Test execution functions
def test_single_category(category_name, chatbot_service=None):
    """Test a single category of queries"""
    if not chatbot_service:
        print("ChatbotService not available for testing")
        return
    
    test_categories = AgenticAITestSuite.get_all_test_categories()
    if category_name not in test_categories:
        print(f"Category '{category_name}' not found")
        return
    
    print(f"\n🧪 TESTING: {category_name}")
    print("=" * 50)
    
    queries = test_categories[category_name]
    
    if isinstance(queries, dict):
        for subcategory, subqueries in queries.items():
            print(f"\n📋 {subcategory}:")
            for query in subqueries[:2]:  # Test first 2 of each subcategory
                result = chatbot_service.process_message(query, user_id="test_user")
                print(f"  ✓ '{query}' -> Intent: {result.get('intent', 'unknown')}")
    else:
        for query in queries[:3]:  # Test first 3 queries
            result = chatbot_service.process_message(query, user_id="test_user")
            print(f"  ✓ '{query}' -> Intent: {result.get('intent', 'unknown')}")

def test_memory_scenarios(chatbot_service=None):
    """Test memory context scenarios"""
    if not chatbot_service:
        print("ChatbotService not available for testing")
        return
    
    print("\n🧠 TESTING MEMORY CONTEXT SCENARIOS")
    print("=" * 50)
    
    scenarios = AgenticAITestSuite.get_memory_context_scenarios()
    
    for scenario_name, queries in scenarios.items():
        print(f"\n📚 Scenario: {scenario_name}")
        test_user_id = f"memory_test_{scenario_name.lower().replace(' ', '_')}"
        
        for i, query in enumerate(queries, 1):
            result = chatbot_service.process_message(
                query, 
                user_id=test_user_id, 
                username="memory_tester"
            )
            memory_used = "✓" if result.get('intent') in ['price_range_search'] and i > 1 else "○"
            print(f"  {i}. {memory_used} '{query}' -> {result.get('intent', 'unknown')}")

if __name__ == "__main__":
    # Print all test queries for manual testing
    AgenticAITestSuite.print_all_test_queries()
    
    print("\n📋 USAGE INSTRUCTIONS:")
    print("1. Copy any query from above categories")
    print("2. Test in your chatbot interface")  
    print("3. For memory testing, use scenarios in sequence")
    print("4. Verify intent detection and product results")
    print("5. Check memory context usage in connected conversations")
