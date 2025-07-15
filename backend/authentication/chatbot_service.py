import os
import json
import logging
from groq import Groq
from mem0 import MemoryClient
from django.conf import settings
from .vector_service import get_vector_service
from .models import Issue
from .markdown_to_text import markdown_to_text

logger = logging.getLogger(__name__)

class ChatbotService:
    def __init__(self):
        self.groq_client = Groq(api_key=os.getenv('GROQ_API_KEY'))
        
        # Initialize mem0 client
        mem0_api_key = os.getenv('MEM0_API_KEY')
        if mem0_api_key:
            try:
                self.memory = MemoryClient(api_key=mem0_api_key)
                logger.info("Mem0 client initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Mem0 client: {e}")
                self.memory = None
        else:
            logger.warning("MEM0_API_KEY not found, memory features disabled")
            self.memory = None
    
    def detect_intent(self, message):
        """Detect user intent using LLM"""
        
        # Check for specific product ID patterns first
        import re
        product_id_patterns = [
            r'product\s+(\d+)',
            r'product\s+id\s+(\d+)',
            r'id\s+(\d+)',
            r'show\s+me\s+product\s+(\d+)',
            r'give\s+me\s+product\s+(\d+)',
            r'product\s+number\s+(\d+)'
        ]
        
        # Check for price range patterns
        price_range_patterns = [
            r'under\s+\$?(\d+)',
            r'below\s+\$?(\d+)',
            r'less\s+than\s+\$?(\d+)',
            r'cheaper\s+than\s+\$?(\d+)',
            r'between\s+\$?(\d+)\s*(?:and|to|-)\s*\$?(\d+)',
            r'\$?(\d+)\s*(?:to|-)\s*\$?(\d+)',
            r'from\s+\$?(\d+)\s*to\s*\$?(\d+)',
            r'price\s+range\s+\$?(\d+)',
            r'budget\s+of\s+\$?(\d+)',
            r'around\s+\$?(\d+)'
        ]
        
        message_lower = message.lower()
        for pattern in product_id_patterns:
            match = re.search(pattern, message_lower)
            if match:
                return "product_specific"
        
        # Check for price range patterns
        for pattern in price_range_patterns:
            match = re.search(pattern, message_lower)
            if match:
                return "price_range_search"
        
        prompt = f"""
        Analyze the following user message and determine the intent. Return only one of these categories:
        
        1. "product_search" - User is looking for products, asking about features, prices, availability
        2. "product_specific" - User is asking about a specific product by name, ID, or wants details
        3. "category_browse" - User wants to browse products by category
        4. "price_range_search" - User is looking for products within a specific price range
        5. "issue_report" - User is reporting a problem, complaint, or needs help with an order/service
        6. "general_chat" - General conversation, greetings, or unclear intent
        
        User message: "{message}"
        
        Intent:"""
        
        try:
            response = self.groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.3-70b-versatile",  # Faster model
                temperature=0.1,
                max_tokens=20,
                timeout=5
            )
            
            intent = response.choices[0].message.content.strip().lower()
            logger.info(f"Detected intent: {intent} for message: {message[:50]}...")
            return intent
            
        except Exception as e:
            logger.error(f"Error detecting intent: {e}")
            return "general_chat"
    
    def extract_category_from_message(self, message):
        """Extract category from user message"""
        categories = get_vector_service().get_categories()
        message_lower = message.lower()
        
        for category in categories:
            if category.lower() in message_lower:
                return category
        return None
    
    def extract_price_range_from_message(self, message):
        """Extract price range from user message"""
        import re
        
        price_range_patterns = [
            (r'under\s+\$?(\d+)', lambda m: (0, int(m.group(1)))),
            (r'below\s+\$?(\d+)', lambda m: (0, int(m.group(1)))),
            (r'less\s+than\s+\$?(\d+)', lambda m: (0, int(m.group(1)))),
            (r'cheaper\s+than\s+\$?(\d+)', lambda m: (0, int(m.group(1)))),
            (r'between\s+\$?(\d+)\s*(?:and|to|-)\s*\$?(\d+)', lambda m: (int(m.group(1)), int(m.group(2)))),
            (r'\$?(\d+)\s*(?:to|-)\s*\$?(\d+)', lambda m: (int(m.group(1)), int(m.group(2)))),
            (r'from\s+\$?(\d+)\s*to\s*\$?(\d+)', lambda m: (int(m.group(1)), int(m.group(2)))),
            (r'budget\s+of\s+\$?(\d+)', lambda m: (0, int(m.group(1)))),
            (r'around\s+\$?(\d+)', lambda m: (max(0, int(m.group(1)) - 50), int(m.group(1)) + 50)),
            (r'price\s+range\s+\$?(\d+)', lambda m: (0, int(m.group(1))))
        ]
        
        message_lower = message.lower()
        for pattern, extractor in price_range_patterns:
            match = re.search(pattern, message_lower)
            if match:
                try:
                    min_price, max_price = extractor(match)
                    return (min_price, max_price)
                except (ValueError, IndexError):
                    continue
        
        return None

    def handle_product_search(self, message, user_id=None):
        """Handle product search queries"""
        try:
            # Extract category if mentioned
            category = self.extract_category_from_message(message)
            
            # Search for products
            products = get_vector_service().search_products(message, k=5, category_filter=category)
            
            if not products:
                return {
                    "response": "I couldn't find any products matching your query. Could you please be more specific or try different keywords?",
                    "products": [],
                    "intent": "product_search"
                }
            
            # Generate response with LLM
            products_text = ""
            product_links = ""
            for i, product in enumerate(products[:3], 1):
                products_text += f"{i}. **{product['name']}** - ${product['price']}\n   Category: {product['category']}\n   {product['description'][:100]}...\n\n"
                product_links += f"🔗 http://localhost:5173/products/{product['id']}\n"
            
            prompt = f"""
            Based on the user's search query: "{message}"
            
            Here are the top matching products:
            {products_text}
            
            Provide a helpful, conversational response that:
            1. Acknowledges their search
            2. Briefly mentions the products found
            3. Offers to provide more details if needed
            4. Keep it under 150 words
            
            Response:"""
            
            response = self.groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.3-70b-versatile", 
                temperature=0.7,
                max_tokens=120,
                timeout=8
            )
            
            bot_response = response.choices[0].message.content.strip()
            
            bot_response = markdown_to_text(bot_response)
            
            if product_links:
                bot_response += f"\n\nProduct Links:\n{product_links}"
            
            # Store in memory if user_id provided
            if user_id and self.memory:
                try:
                    messages = [
                        {"role": "user", "content": f"User searched for: {message}"},
                        {"role": "assistant", "content": f"Found {len(products)} products matching '{message}'. Top results: {', '.join([p['name'] for p in products[:3]])}"}
                    ]
                    self.memory.add(messages, user_id=str(user_id))
                except Exception as e:
                    logger.error(f"Error storing memory: {e}")
            
            return {
                "response": bot_response,
                "products": products[:5],
                "intent": "product_search"
            }
            
        except Exception as e:
            logger.error(f"Error in product search: {e}")
            return {
                "response": "I'm sorry, I encountered an error while searching for products. Please try again.",
                "products": [],
                "intent": "product_search"
            }
    
    def handle_product_specific(self, message, user_id=None):
        """Handle specific product queries"""
        try:
            import re
            
            # First, try to extract product ID from message
            product_id_patterns = [
                r'product\s+(\d+)',
                r'product\s+id\s+(\d+)',
                r'id\s+(\d+)',
                r'show\s+me\s+product\s+(\d+)',
                r'give\s+me\s+product\s+(\d+)',
                r'product\s+number\s+(\d+)'
            ]
            
            message_lower = message.lower()
            product_id = None
            
            for pattern in product_id_patterns:
                match = re.search(pattern, message_lower)
                if match:
                    product_id = int(match.group(1))
                    break
            
            # If we found a product ID, search by ID
            if product_id:
                product = get_vector_service().get_product_by_id(product_id)
                if product:
                    products = [product]
                else:
                    return {
                        "response": f"I couldn't find product with ID {product_id}. Please check the product ID or try searching by name.",
                        "products": [],
                        "intent": "product_specific"
                    }
            else:
                # Search for the specific product by name/description
                products = get_vector_service().search_products(message, k=1)
            
            if not products:
                return {
                    "response": "I couldn't find that specific product. Could you provide more details or check the product name/ID?",
                    "products": [],
                    "intent": "product_specific"
                }
            
            product = products[0]
            
            prompt = f"""
            User is asking about this specific product: "{message}"
            
            Product Details:
            - ID: {product['id']}
            - Name: {product['name']}
            - Price: ${product['price']}
            - Category: {product['category']}
            - Description: {product['description']}
            
            Provide a concise, structured response that includes:
            1. Product name and ID
            2. Price and category
            3. Brief description (2-3 sentences max)
            4. Keep it under 100 words and professional
            
            Response:"""
            
            response = self.groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.3-70b-versatile",
                temperature=0.3,
                max_tokens=100,
                timeout=8
            )
            
            bot_response = response.choices[0].message.content.strip()
            
            # Convert markdown to plain text
            bot_response = markdown_to_text(bot_response)
            
            # Add product link
            product_link = f"http://localhost:5173/products/{product['id']}"
            bot_response += f"\n\nProduct Link:\n{product_link}"
            
            if user_id and self.memory:
                try:
                    messages = [
                        {"role": "user", "content": f"User asked about product ID {product['id']}: {message}"},
                        {"role": "assistant", "content": f"Showed product ID {product['id']}: {product['name']} - ${product['price']} in {product['category']} category"}
                    ]
                    self.memory.add(messages, user_id=str(user_id))
                except Exception as e:
                    logger.error(f"Error storing memory: {e}")
            
            return {
                "response": bot_response,
                "products": [product],
                "intent": "product_specific"
            }
            
        except Exception as e:
            logger.error(f"Error in specific product query: {e}")
            return {
                "response": "I'm sorry, I couldn't retrieve the product details right now. Please try again.",
                "products": [],
                "intent": "product_specific"
            }
    
    def handle_category_browse(self, message, user_id=None):
        """Handle category browsing"""
        try:
            category = self.extract_category_from_message(message)
            
            if not category:
                categories = get_vector_service().get_categories()
                return {
                    "response": f"I can help you browse our categories! We have: {', '.join(categories)}. Which category interests you?",
                    "products": [],
                    "categories": categories,
                    "intent": "category_browse"
                }
            
            products = get_vector_service().get_products_by_category(category, limit=5)
            
            if not products:
                return {
                    "response": f"I couldn't find any products in the {category} category right now. Please try another category.",
                    "products": [],
                    "intent": "category_browse"
                }
            
            prompt = f"""
            User wants to browse products in the "{category}" category.
            
            Found {len(products)} products in this category. Here are the top ones:
            {chr(10).join([f"- {p['name']} (${p['price']})" for p in products[:3]])}
            
            Provide an engaging response that:
            1. Welcomes them to the category
            2. Mentions the variety available
            3. Encourages them to explore
            Keep it under 150 words.
            
            Response:"""
            
            response = self.groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.3-70b-versatile",
                temperature=0.7,
                max_tokens=120,
                timeout=8
            )
            
            bot_response = response.choices[0].message.content.strip()
            
            # Convert markdown to plain text
            bot_response = markdown_to_text(bot_response)
            
            # Add product links
            if products:
                product_links = ""
                for product in products[:3]:
                    product_links += f"🔗 http://localhost:5173/products/{product['id']}\n"
                
                if product_links:
                    bot_response += f"\n\n📱 **Featured Products:**\n{product_links}"
            
            bot_response = markdown_to_text(bot_response)

            if user_id and self.memory:
                try:
                    messages = [
                        {"role": "user", "content": f"User browsed {category} category"},
                        {"role": "assistant", "content": f"Showed {len(products)} products from {category} category. Featured: {', '.join([p['name'] for p in products[:3]])}"}
                    ]
                    self.memory.add(messages, user_id=str(user_id))
                except Exception as e:
                    logger.error(f"Error storing memory: {e}")
            
            return {
                "response": bot_response,
                "products": products,
                "category": category,
                "intent": "category_browse"
            }
            
        except Exception as e:
            logger.error(f"Error in category browse: {e}")
            return {
                "response": "I'm sorry, I couldn't load the category right now. Please try again.",
                "products": [],
                "intent": "category_browse"
            }
    
    def handle_issue_report(self, message, user_id=None, user_email=None, username=None):
        """Handle issue reporting"""
        try:
            # Create issue in database
            issue = Issue.objects.create(
                username=username or "Anonymous",
                email=user_email or "",
                message=message,
                status="pending"
            )
            
            # Generate empathetic response
            prompt = f"""
            A user has reported an issue: "{message}"
            
            Provide a helpful, empathetic response that:
            1. Acknowledges their concern
            2. Assures them it will be addressed
            3. Provides an issue reference number: #{issue.id}
            4. Offers additional assistance
            Keep it professional and caring, under 150 words.
            
            Response:"""
            
            response = self.groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.3-70b-versatile",
                temperature=0.6,
                max_tokens=120,
                timeout=8
            )
            
            bot_response = response.choices[0].message.content.strip()
            
            # Convert markdown to plain text
            bot_response = markdown_to_text(bot_response)
            
            if user_id and self.memory:
                try:
                    messages = [
                        {"role": "user", "content": f"User reported issue: {message[:100]}..."},
                        {"role": "assistant", "content": f"Created issue #{issue.id} for user {username}: {message[:50]}..."}
                    ]
                    self.memory.add(messages, user_id=str(user_id))
                except Exception as e:
                    logger.error(f"Error storing memory: {e}")
            
            logger.info(f"Created issue #{issue.id} for user {username}")
            
            return {
                "response": bot_response,
                "issue_id": issue.id,
                "intent": "issue_report"
            }
            
        except Exception as e:
            logger.error(f"Error handling issue report: {e}")
            return {
                "response": "I'm sorry, I couldn't submit your issue right now. Please try again or contact our support team directly.",
                "intent": "issue_report"
            }
    
    def handle_general_chat(self, message, user_id=None):
        """Handle general conversation"""
        try:
            # Get user memory context if available
            memories = ""
            if user_id and self.memory:
                try:
                    memory_results = self.memory.search(message, user_id=str(user_id))
                    if memory_results:
                        memories = "Previous context: " + "; ".join([m.get('memory', '') for m in memory_results[:3]])
                except Exception as e:
                    logger.error(f"Error retrieving memories: {e}")
                    memories = ""
            
            prompt = f"""
            You are a helpful AI assistant for an e-commerce platform called "Agentic AI Store".
            
            {memories}
            
            User message: "{message}"
            
            Provide a helpful, friendly response. If appropriate, gently guide them toward browsing products or ask how you can help them find what they need.
            Keep it conversational and under 150 words.
            
            Response:"""
            
            response = self.groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.3-70b-versatile",
                temperature=0.8,
                max_tokens=120,
                timeout=8
            )
            
            bot_response = response.choices[0].message.content.strip()
            
            # Convert markdown to plain text
            bot_response = markdown_to_text(bot_response)
            
            if user_id and self.memory:
                try:
                    messages = [
                        {"role": "user", "content": f"General chat: {message}"},
                        {"role": "assistant", "content": f"Responded to general conversation: {bot_response[:100]}..."}
                    ]
                    self.memory.add(messages, user_id=str(user_id))
                except Exception as e:
                    logger.error(f"Error storing memory: {e}")
            
            return {
                "response": bot_response,
                "intent": "general_chat"
            }
            
        except Exception as e:
            logger.error(f"Error in general chat: {e}")
            return {
                "response": "Hello! I'm here to help you find products or answer any questions. How can I assist you today?",
                "intent": "general_chat"
            }
    
    def handle_price_range_search(self, message, user_id=None):
        """Handle price range based product search"""
        try:
            # Extract price range
            price_range = self.extract_price_range_from_message(message)
            
            if not price_range:
                return {
                    "response": "I couldn't understand the price range you're looking for. Could you please specify it more clearly? For example: 'products under $50' or 'between $20 to $100'",
                    "products": [],
                    "intent": "price_range_search"
                }
            
            min_price, max_price = price_range
            
            # Also check for category if mentioned
            category = self.extract_category_from_message(message)
            
            # Search for products in price range
            products = get_vector_service().search_products_by_price_range(
                min_price=min_price, 
                max_price=max_price, 
                category_filter=category,
                k=10
            )
            
            if not products:
                price_text = f"${min_price}-${max_price}" if min_price > 0 else f"under ${max_price}"
                category_text = f" in {category}" if category else ""
                return {
                    "response": f"I couldn't find any products {price_text}{category_text}. Would you like to try a different price range or browse our other products?",
                    "products": [],
                    "intent": "price_range_search"
                }
            
            # Generate response with LLM
            price_text = f"${min_price}-${max_price}" if min_price > 0 else f"under ${max_price}"
            category_text = f" in {category}" if category else ""
            
            products_text = ""
            product_links = ""
            for i, product in enumerate(products[:5], 1):
                products_text += f"{i}. {product['name']} - ${product['price']}\n   Category: {product['category']}\n   {product['description'][:80]}...\n\n"
                product_links += f"🔗 http://localhost:5173/products/{product['id']}\n"
            
            prompt = f"""
            User is looking for products in price range {price_text}{category_text}.
            
            Found {len(products)} products matching their criteria:
            {products_text}
            
            Provide a helpful response that:
            1. Confirms their price range search
            2. Mentions the number of products found
            3. Highlights a few top options
            4. Encourages them to check the links
            Keep it under 150 words and conversational.
            
            Response:"""
            
            response = self.groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.3-70b-versatile",
                temperature=0.7,
                max_tokens=120,
                timeout=8
            )
            
            bot_response = response.choices[0].message.content.strip()
            
            # Convert markdown to plain text
            bot_response = markdown_to_text(bot_response)
            
            # Add product links
            if product_links:
                bot_response += f"\n\nProduct Links:\n{product_links}"
            
            # Store in memory if user_id provided
            if user_id and self.memory:
                try:
                    messages = [
                        {"role": "user", "content": f"User searched for products in price range {price_text}{category_text}"},
                        {"role": "assistant", "content": f"Found {len(products)} products in price range {price_text}{category_text}. Top results: {', '.join([p['name'] for p in products[:3]])}"}
                    ]
                    self.memory.add(messages, user_id=str(user_id))
                except Exception as e:
                    logger.error(f"Error storing memory: {e}")
            
            return {
                "response": bot_response,
                "products": products[:5],
                "price_range": price_range,
                "category": category,
                "intent": "price_range_search"
            }
            
        except Exception as e:
            logger.error(f"Error in price range search: {e}")
            return {
                "response": "I'm sorry, I encountered an error while searching for products in your price range. Please try again.",
                "products": [],
                "intent": "price_range_search"
            }

    def process_message(self, message, user_id=None, user_email=None, username=None):
        """Main method to process user messages"""
        try:
            intent = self.detect_intent(message)
            
            if intent == "product_search":
                return self.handle_product_search(message, user_id)
            elif intent == "product_specific":
                return self.handle_product_specific(message, user_id)
            elif intent == "category_browse":
                return self.handle_category_browse(message, user_id)
            elif intent == "issue_report":
                return self.handle_issue_report(message, user_id, user_email, username)
            elif intent == "price_range_search":
                return self.handle_price_range_search(message, user_id)
            else:
                return self.handle_general_chat(message, user_id)
                
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            return {
                "response": "I'm sorry, I encountered an error. Please try again.",
                "intent": "error"
            }

# Global instance
chatbot_service = ChatbotService()
