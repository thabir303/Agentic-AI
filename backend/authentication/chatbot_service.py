import os
import json
import re
import logging
from datetime import datetime
from groq import Groq
from mem0 import MemoryClient
from django.conf import settings
from .vector_service import get_vector_service
from .models import Issue
from .markdown_to_text import markdown_to_text

logger = logging.getLogger(__name__)

class ChatbotService:
    def __init__(self):
        # Check fallback configuration - disable fallback by default to use APIs
        self.use_local_fallback = os.getenv('USE_LOCAL_FALLBACK', 'False').lower() == 'true'
        self.enable_api_fallback = os.getenv('ENABLE_API_FALLBACK', 'True').lower() == 'true'
        
        # Initialize Groq client with API key
        groq_api_key = os.getenv('GROQ_API_KEY')
        if groq_api_key and not self.use_local_fallback:
            try:
                self.groq_client = Groq(api_key=groq_api_key)
                # Test the connection with a simple request
                logger.info("Groq client initialized successfully with API key")
            except Exception as e:
                logger.error(f"Failed to initialize Groq client: {e}")
                self.groq_client = None
        else:
            if self.use_local_fallback:
                logger.warning("Local fallback mode enabled, Groq client disabled")
            else:
                logger.warning("No Groq API key found")
            self.groq_client = None
        
        # Initialize mem0 client with API key  
        mem0_api_key = os.getenv('MEM0_API_KEY')
        self.use_mem0 = False
        
        if mem0_api_key and not self.use_local_fallback:
            try:
                self.memory = MemoryClient(api_key=mem0_api_key)
                self.use_mem0 = True
                logger.info("Mem0 client initialized successfully with API key")
            except Exception as e:
                logger.error(f"Failed to initialize Mem0 client: {e}")
                logger.warning("Falling back to local memory storage")
                self.memory = None
                self.use_mem0 = False
        else:
            if self.use_local_fallback:
                logger.warning("Local fallback mode enabled, using local memory storage")
            else:
                logger.warning("No Mem0 API key found, using local memory storage")
            self.memory = None
            self.use_mem0 = False
            
        # Always initialize local memory as fallback
        self.local_memory = {}
    
    def get_user_memory_context(self, user_id, current_message, limit=5):
        """Enhanced memory retrieval with better context filtering and local fallback"""
        if not user_id:
            return ""
        
        try:
            if self.memory:
                # Try Mem0 first
                memory_results = self.memory.search(current_message, user_id=str(user_id))
                
                if not memory_results:
                    return ""
                
                # Filter and format relevant memories
                relevant_memories = []
                for memory in memory_results[:limit]:
                    memory_text = memory.get('memory', '').strip()
                    if memory_text and len(memory_text) > 10:
                        if not self._is_current_conversation(memory_text, current_message):
                            relevant_memories.append(memory_text)
                
                if relevant_memories:
                    context = "Previous user context: " + " | ".join(relevant_memories[:3])
                    logger.info(f"Retrieved {len(relevant_memories)} relevant memories for user {user_id}")
                    return context
                
                return ""
            else:
                # Fallback to local memory
                user_memories = self.local_memory.get(str(user_id), [])
                if user_memories:
                    recent_memories = user_memories[-limit:]
                    context = "Previous context: " + " | ".join([mem['content'] for mem in recent_memories])
                    return context
                return ""
            
        except Exception as e:
            logger.error(f"Error retrieving user memory: {e}")
            # Fallback to local memory
            user_memories = self.local_memory.get(str(user_id), [])
            if user_memories:
                recent_memories = user_memories[-limit:]
                context = "Previous context: " + " | ".join([mem['content'] for mem in recent_memories])
                return context
            return ""
    
    def _is_current_conversation(self, memory_text, current_message):
        """Check if memory is from current conversation to avoid repetition"""
        current_words = set(current_message.lower().split())
        memory_words = set(memory_text.lower().split())
        
        # If more than 60% words overlap, consider it current conversation
        if len(current_words) > 0:
            overlap = len(current_words.intersection(memory_words)) / len(current_words)
            return overlap > 0.6
        return False
    
    def store_user_memory(self, user_id, user_message, bot_response, intent, extra_context=None, username=None):
        """Enhanced memory storage with better context and username tracking + local fallback"""
        if not user_id:
            return
        
        try:
            if self.memory:
                # Try Mem0 storage
                memory_entry = [
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": bot_response}
                ]
                
                metadata = {
                    "intent": intent,
                    "timestamp": json.dumps({"timestamp": str(datetime.now())}),
                    "user_id": str(user_id),
                    "username": username or "unknown_user"
                }
                
                if extra_context:
                    metadata.update(extra_context)
                
                self.memory.add(memory_entry, user_id=str(user_id), metadata=metadata)
                logger.info(f"Stored memory for user {user_id} ({username}) with intent {intent}")
            else:
                # Fallback to local memory
                if not hasattr(self, 'local_memory'):
                    self.local_memory = {}
                
                if str(user_id) not in self.local_memory:
                    self.local_memory[str(user_id)] = []
                
                memory_entry = {
                    "user_message": user_message,
                    "bot_response": bot_response,
                    "intent": intent,
                    "username": username or "unknown_user",
                    "timestamp": str(datetime.now()),
                    "content": f"User ({username}): {user_message} | Bot: {bot_response[:100]}..."
                }
                
                self.local_memory[str(user_id)].append(memory_entry)
                
                # Keep only last 10 memories per user
                if len(self.local_memory[str(user_id)]) > 10:
                    self.local_memory[str(user_id)] = self.local_memory[str(user_id)][-10:]
                
                logger.info(f"Stored local memory for user {user_id} ({username}) with intent {intent}")
            
        except Exception as e:
            logger.error(f"Error storing user memory: {e}")
            # Fallback to local storage even if Mem0 fails
            if not hasattr(self, 'local_memory'):
                self.local_memory = {}
            
            if str(user_id) not in self.local_memory:
                self.local_memory[str(user_id)] = []
            
            memory_entry = {
                "user_message": user_message,
                "bot_response": bot_response,
                "intent": intent,
                "username": username or "unknown_user",
                "timestamp": str(datetime.now()),
                "content": f"User ({username}): {user_message} | Bot: {bot_response[:100]}..."
            }
            
            self.local_memory[str(user_id)].append(memory_entry)
            logger.info(f"Stored fallback local memory for user {user_id} ({username})")

    def store_user_profile(self, user_id, username, user_email=None):
        """Store user profile information in memory for personalization with fallback"""
        if not user_id:
            return
        
        try:
            if self.memory:
                # Try Mem0 storage
                profile_entry = [
                    {"role": "system", "content": f"User profile: Username is {username}, Email: {user_email or 'not provided'}"}
                ]
                
                metadata = {
                    "intent": "user_profile",
                    "username": username,
                    "email": user_email or "",
                    "profile_stored": True
                }
                
                self.memory.add(profile_entry, user_id=str(user_id), metadata=metadata)
                logger.info(f"Stored profile for user {user_id}: {username}")
            else:
                # Fallback to local memory
                if not hasattr(self, 'local_memory'):
                    self.local_memory = {}
                
                if str(user_id) not in self.local_memory:
                    self.local_memory[str(user_id)] = []
                
                profile_entry = {
                    "user_message": "Profile setup",
                    "bot_response": f"Remembered profile for {username}",
                    "intent": "user_profile",
                    "username": username,
                    "email": user_email or "",
                    "timestamp": str(datetime.now()),
                    "content": f"User profile: {username} ({user_email or 'no email'})"
                }
                
                # Add profile at the beginning
                self.local_memory[str(user_id)].insert(0, profile_entry)
                logger.info(f"Stored local profile for user {user_id}: {username}")
            
        except Exception as e:
            logger.error(f"Error storing user profile: {e}")
            # Fallback to local storage
            if not hasattr(self, 'local_memory'):
                self.local_memory = {}
            
            if str(user_id) not in self.local_memory:
                self.local_memory[str(user_id)] = []
            
            profile_entry = {
                "user_message": "Profile setup",
                "bot_response": f"Remembered profile for {username}",
                "intent": "user_profile", 
                "username": username,
                "email": user_email or "",
                "timestamp": str(datetime.now()),
                "content": f"User profile: {username} ({user_email or 'no email'})"
            }
            
            self.local_memory[str(user_id)].insert(0, profile_entry)
            logger.info(f"Stored fallback profile for user {user_id}: {username}")

    def get_user_name_from_memory(self, user_id):
        """
        Retrieve username from memory
        """
        try:
            # Try Mem0 first
            if self.use_mem0:
                memories = self.memory.get_all(user_id=str(user_id))
                
                # Look for profile information
                for memory in memories:
                    memory_text = memory.get('memory', '').lower()
                    if 'profile' in memory_text or 'username' in memory_text:
                        # Extract username from memory
                        lines = memory_text.split('\n')
                        for line in lines:
                            if 'name:' in line.lower() or 'username:' in line.lower():
                                username = line.split(':')[-1].strip()
                                if username:
                                    return username
            
            # Fallback to local memory
            if hasattr(self, 'local_memory') and str(user_id) in self.local_memory:
                memories = self.local_memory[str(user_id)]
                for memory in memories:
                    if memory.get('username'):
                        return memory['username']
                    # Also check in content
                    content = memory.get('content', '')
                    if 'User profile:' in content:
                        parts = content.split('User profile:')
                        if len(parts) > 1:
                            name_part = parts[1].split('(')[0].strip()
                            if name_part:
                                return name_part
                                
        except Exception as e:
            logger.error(f"Error retrieving username from memory: {e}")
        
        return None
        """Get username from memory (local or Mem0)"""
        if not user_id:
            return None
        
        try:
            if self.memory:
                # Try to search for user profile
                memory_results = self.memory.search("User profile", user_id=str(user_id))
                for memory in memory_results:
                    if "username" in memory.get('memory', '').lower():
                        # Extract username from memory
                        memory_text = memory.get('memory', '')
                        if "Username is" in memory_text:
                            username = memory_text.split("Username is")[1].split(",")[0].strip()
                            return username
            else:
                # Check local memory
                user_memories = self.local_memory.get(str(user_id), [])
                for memory in user_memories:
                    if memory.get('intent') == 'user_profile':
                        return memory.get('username')
                    # Also check if username is stored in any memory
                    if memory.get('username') and memory.get('username') != 'unknown_user':
                        return memory.get('username')
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting username from memory: {e}")
            # Try local memory as fallback
            if hasattr(self, 'local_memory'):
                user_memories = self.local_memory.get(str(user_id), [])
                for memory in user_memories:
                    if memory.get('username') and memory.get('username') != 'unknown_user':
                        return memory.get('username')
            return None
            # Fallback to local storage
            if not hasattr(self, 'local_memory'):
                self.local_memory = {}
            
            if str(user_id) not in self.local_memory:
                self.local_memory[str(user_id)] = []
            
            profile_entry = {
                "user_message": "Profile setup",
                "bot_response": f"Remembered profile for {username}",
                "intent": "user_profile", 
                "username": username,
                "email": user_email or "",
                "timestamp": str(datetime.now()),
                "content": f"User profile: {username} ({user_email or 'no email'})"
            }
            
            self.local_memory[str(user_id)].insert(0, profile_entry)
            logger.info(f"Stored fallback profile for user {user_id}: {username}")

    def detect_hybrid_intent(self, message, user_context=""):
        """Simple intent wrapper - just use main detect_intent"""
        return self.detect_intent(message, user_context)
    
    def simple_keyword_intent_detection(self, message_lower):
        """Simple fallback intent detection"""
        
        # Product ID patterns (highest priority)
        if any(phrase in message_lower for phrase in ['product id', 'show product', 'product number', 'product 5']):
            return "product_specific"
        
        # Personal questions
        if any(phrase in message_lower for phrase in ["what's my name", "who am i", "what's your name", "who are you"]):
            return "general_chat"
        
        # Greetings and social
        if any(word in message_lower for word in ['hello', 'hi', 'hey', 'thanks', 'thank you', 'how are you']):
            return "general_chat"
            
        # Category browsing
        if any(word in message_lower for word in ['category', 'browse', 'section', 'electronics']):
            return "category_browse"
            
        # Product search keywords (broader)
        if any(word in message_lower for word in ['find', 'search', 'need', 'want', 'buy', 'steel', 'bowl', 'phone', 'kitchen', 'looking for']):
            return "product_search"
        
        return "general_chat"

    def detect_intent(self, message, user_context=""):
        """Smart LLM-based intent detection with enhanced prompting"""
        
        # If Groq API is disabled, use simple fallback
        if not self.groq_client or self.use_local_fallback:
            return self.simple_keyword_intent_detection(message.lower())
        
        prompt = f"""You are a smart e-commerce assistant. Analyze this message and respond with ONE word intent:

INTENTS: product_search, product_specific, category_browse, general_chat, issue_report

MESSAGE: "{message}"

SMART RULES:
- product_search: Looking for products, need items, kitchen stuff, buy things
- product_specific: "show product 123", "product ID 456", exact product requests  
- category_browse: "browse electronics", "show categories", section browsing
- general_chat: greetings, name questions, thanks, casual talk
- issue_report: problems, complaints, errors, broken things

EXAMPLES:
"Hello" → general_chat
"What's my name?" → general_chat  
"I need kitchen items" → product_search
"Show product 527" → product_specific
"Browse electronics" → category_browse
"My order is broken" → issue_report
"Looking for bowls" → product_search

INTENT:"""
        
        try:
            response = self.groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.3-70b-versatile",
                temperature=0.1,
                max_tokens=10,
                timeout=5
            )
            
            intent = response.choices[0].message.content.strip().lower()
            valid_intents = ["product_search", "product_specific", "category_browse", "general_chat", "issue_report"]
            
            if intent in valid_intents:
                return intent
            else:
                return "general_chat"  # Safe default
                
        except Exception as e:
            logger.error(f"Intent detection failed: {e}")
            return self.simple_keyword_intent_detection(message.lower())
    
    def clean_response_for_production(self, response_text):
        """Clean response text for production - remove markdown and make it user-friendly"""
        if not response_text:
            return response_text
        
        # Remove markdown formatting
        clean_text = markdown_to_text(response_text)
        
        # Remove excessive bold/italic markers that might remain
        clean_text = clean_text.replace('**', '').replace('*', '')
        clean_text = clean_text.replace('__', '').replace('_', '')
        
        # Clean up extra whitespace and newlines
        lines = [line.strip() for line in clean_text.split('\n') if line.strip()]
        clean_text = '\n'.join(lines)
        
        # Remove any remaining markdown syntax
        clean_text = clean_text.replace('# ', '').replace('## ', '').replace('### ', '')
        clean_text = clean_text.replace('- ', '• ').replace('* ', '• ')
        
        return clean_text.strip()

    def generate_simple_product_response(self, products, username, query, price_info=""):
        """Generate simple template-based product response when LLM is unavailable"""
        
        # Only greet on first interaction or when appropriate
        user_greeting = ""  # Remove automatic greeting
        price_text = price_info if price_info else ""
        
        if len(products) == 1:
            product = products[0]
            response = f"I found a great match for '{query}'{price_text}:\n\n"
            response += f"{product['name']} - ${product['price']}\n"
            response += f"Category: {product['category']}\n"
            response += f"{product['description'][:100]}...\n\n"
        else:
            response = f"I found {len(products)} products matching '{query}'{price_text}:\n\n"
            for i, product in enumerate(products, 1):
                response += f"{i}. {product['name']} - ${product['price']}\n"
                response += f"   Category: {product['category']}\n"
                if product.get('relevance_score'):
                    response += f"   Relevance: {product['relevance_score']}/5\n"
                response += "\n"
        
        response += "Would you like more details about any of these products?"
        return response
    
    def generate_simple_chat_response(self, message_lower, username, memory_context):
        """Generate simple template-based chat responses when LLM is unavailable"""
        
        # Smart greeting logic - only greet when appropriate
        def should_greet():
            """Determine if we should include a greeting"""
            greetings = ['hello', 'hi', 'hey', 'good morning', 'good afternoon', 'good evening']
            return any(greeting in message_lower for greeting in greetings)
        
        # Only use username in greeting for initial hello, not every response
        user_greeting = f"Hello {username}! " if should_greet() and username and username != "unknown_user" else ""
        
        # Greeting responses
        if any(word in message_lower for word in ['hello', 'hi', 'hey']):
            return f"{user_greeting}Welcome to Agentic AI Store! I'm here to help you with anything you need. How can I assist you today?"
        
        # Thank you responses
        if any(phrase in message_lower for phrase in ['thank you', 'thanks']):
            return "You're very welcome! Is there anything else I can help you with?"
        
        # How are you responses
        if any(phrase in message_lower for phrase in ['how are you', 'how do you do']):
            return "I'm doing great and ready to help you with your shopping needs! What can I assist you with today?"
        
        # Help requests
        if 'help' in message_lower:
            return "I'd be happy to help! I can assist you with finding products, checking categories, or answering questions about our store. What would you like to do?"
        
        # Default conversational response
        return "I'm here to help you with your shopping needs at Agentic AI Store. You can ask me to find products, browse categories, or just chat! What would you like to do?"
    
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

    def filter_relevant_products(self, products, query, max_products=3):
        """Simple product filtering"""
        return products[:max_products] if products else []

    def handle_product_search(self, message, user_id=None, username=None):
        """Smart product search with enhanced LLM prompting"""
        try:
            # Get products from vector search
            category = self.extract_category_from_message(message)
            price_range = self.extract_price_range_from_message(message)
            
            # Search products
            if price_range:
                min_price, max_price = price_range
                products = get_vector_service().search_products_by_price_range(
                    min_price=min_price, max_price=max_price, category_filter=category, k=5
                )
            else:
                products = get_vector_service().search_products(message, k=5, category_filter=category)
            
            if not products:
                response = "I couldn't find products matching your request. Could you try different keywords?"
                if user_id:
                    self.store_user_memory(user_id, message, response, "product_search", {}, username)
                return {"response": response, "products": [], "intent": "product_search"}
            
            # Enhanced LLM prompt for better responses
            products_text = "\n".join([f"• {p['name']} - ${p['price']} ({p['category']})" for p in products[:3]])
            price_text = f" within ${price_range[0]}-${price_range[1]}" if price_range else ""
            
            prompt = f"""You are a helpful e-commerce assistant. A customer searched: "{message}"{price_text}

PRODUCTS FOUND:
{products_text}

RESPOND with:
1. Brief acknowledgment of their search
2. Present the products naturally
3. Mention key features/price if relevant
4. Ask if they want more details

Keep it conversational, helpful, and under 100 words. NO markdown formatting."""
            
            # Generate response
            if self.groq_client and not self.use_local_fallback:
                try:
                    response = self.groq_client.chat.completions.create(
                        messages=[{"role": "user", "content": prompt}],
                        model="llama-3.3-70b-versatile", 
                        temperature=0.7,
                        max_tokens=120,
                        timeout=8
                    )
                    bot_response = response.choices[0].message.content.strip()
                    bot_response = self.clean_response_for_production(bot_response)
                except Exception:
                    bot_response = f"I found {len(products)} products for '{message}'{price_text}:\n\n{products_text}\n\nWould you like more details about any of these?"
            else:
                bot_response = f"I found {len(products)} products for '{message}'{price_text}:\n\n{products_text}\n\nWould you like more details about any of these?"
            
            # Add product links
            product_links = "\n".join([f"🔗 http://localhost:5173/products/{p['id']}" for p in products[:3]])
            bot_response += f"\n\nProduct Links:\n{product_links}"
            
            if user_id:
                self.store_user_memory(user_id, message, bot_response, "product_search", 
                                     {"products_found": len(products)}, username)
            
            return {"response": bot_response, "products": products, "intent": "product_search"}
            
        except Exception as e:
            logger.error(f"Product search error: {e}")
            return {"response": "Sorry, I'm having trouble searching right now. Please try again.", 
                   "products": [], "intent": "product_search"}
    
    def handle_product_specific(self, message, user_id=None, username=None):
        """Smart specific product handler"""
        try:
            import re
            
            # Extract product ID from message
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
            
            # Get product by ID or search
            if product_id:
                product = get_vector_service().get_product_by_id(product_id)
                if not product:
                    response = f"I couldn't find product with ID {product_id}. Please check the product ID or try searching by name."
                    if user_id:
                        self.store_user_memory(user_id, message, response, "product_specific", {}, username)
                    return {"response": response, "products": [], "intent": "product_specific"}
                products = [product]
            else:
                products = get_vector_service().search_products(message, k=1)
            
            if not products:
                response = "I couldn't find that specific product. Could you provide more details or check the product name/ID?"
                if user_id:
                    self.store_user_memory(user_id, message, response, "product_specific", {}, username)
                return {"response": response, "products": [], "intent": "product_specific"}
            
            product = products[0]
            
            # Smart LLM response or simple fallback
            if self.groq_client and not self.use_local_fallback:
                prompt = f"""User wants details about this specific product:

PRODUCT: {product['name']} (ID: {product['id']})
PRICE: ${product['price']}
CATEGORY: {product['category']}
DESCRIPTION: {product['description']}

RESPOND with:
1. Product name and ID
2. Price and category
3. Brief description
Keep it professional and under 80 words. NO markdown."""
                
                try:
                    response = self.groq_client.chat.completions.create(
                        messages=[{"role": "user", "content": prompt}],
                        model="llama-3.3-70b-versatile",
                        temperature=0.3,
                        max_tokens=100,
                        timeout=6
                    )
                    bot_response = response.choices[0].message.content.strip()
                    bot_response = self.clean_response_for_production(bot_response)
                except Exception:
                    bot_response = f"Product ID {product['id']}: {product['name']}\nPrice: ${product['price']}\nCategory: {product['category']}\n\n{product['description'][:100]}..."
            else:
                bot_response = f"Product ID {product['id']}: {product['name']}\nPrice: ${product['price']}\nCategory: {product['category']}\n\n{product['description'][:100]}..."
            
            # Add product link
            product_link = f"http://localhost:5173/products/{product['id']}"
            bot_response += f"\n\nProduct Link:\n{product_link}"
            
            if user_id:
                self.store_user_memory(user_id, message, bot_response, "product_specific", 
                                     {"product_id": product['id'], "product_name": product['name']}, username)
            
            return {"response": bot_response, "products": [product], "intent": "product_specific"}
            
        except Exception as e:
            logger.error(f"Product specific error: {e}")
            return {"response": "Sorry, I couldn't retrieve the product details right now. Please try again.", 
                   "products": [], "intent": "product_specific"}
    
    def handle_category_browse(self, message, user_id=None, username=None):
        """Smart category browsing with enhanced LLM"""
        try:
            category = self.extract_category_from_message(message)
            
            if not category:
                categories = get_vector_service().get_categories()
                response = f"I can help you browse our categories! We have: {', '.join(categories)}. Which category interests you?"
                if user_id:
                    self.store_user_memory(user_id, message, response, "category_browse", {}, username)
                return {"response": response, "products": [], "categories": categories, "intent": "category_browse"}
            
            products = get_vector_service().get_products_by_category(category, limit=5)
            
            if not products:
                response = f"I couldn't find products in {category} right now. Try another category or search for specific items!"
                if user_id:
                    self.store_user_memory(user_id, message, response, "category_browse", {}, username)
                return {"response": response, "products": [], "intent": "category_browse"}
            
            # Smart LLM response or simple fallback
            products_text = "\n".join([f"• {p['name']} - ${p['price']}" for p in products[:3]])
            
            if self.groq_client and not self.use_local_fallback:
                prompt = f"""User wants to browse "{category}" category.

PRODUCTS FOUND:
{products_text}

RESPOND with:
1. Welcome them to the category
2. Show the products naturally  
3. Encourage exploration
Keep it conversational and under 100 words. NO markdown."""
                
                try:
                    response = self.groq_client.chat.completions.create(
                        messages=[{"role": "user", "content": prompt}],
                        model="llama-3.3-70b-versatile",
                        temperature=0.7,
                        max_tokens=100,
                        timeout=6
                    )
                    bot_response = response.choices[0].message.content.strip()
                    bot_response = self.clean_response_for_production(bot_response)
                except Exception:
                    bot_response = f"Here are our top {category} products:\n\n{products_text}\n\nWould you like to see more details about any of these?"
            else:
                bot_response = f"Here are our top {category} products:\n\n{products_text}\n\nWould you like to see more details about any of these?"
            
            # Add product links
            product_links = "\n".join([f"🔗 http://localhost:5173/products/{p['id']}" for p in products[:3]])
            bot_response += f"\n\nProduct Links:\n{product_links}"
            
            if user_id:
                self.store_user_memory(user_id, message, bot_response, "category_browse", 
                                     {"category": category, "products_shown": len(products)}, username)
            
            return {"response": bot_response, "products": products, "category": category, "intent": "category_browse"}
            
        except Exception as e:
            logger.error(f"Category browse error: {e}")
            return {"response": "Sorry, I couldn't load categories right now. Try searching for specific products!", 
                   "intent": "category_browse"}
    
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
            
            # Store enhanced memory
            if user_id:
                extra_context = {
                    "issue_id": issue.id,
                    "issue_status": issue.status,
                    "issue_type": "customer_support"
                }
                self.store_user_memory(user_id, message, bot_response, "issue_report", extra_context, username)
            
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
    
    def handle_general_chat(self, message, user_id=None, username=None):
        """Smart general conversation with enhanced LLM prompting"""
        try:
            message_lower = message.lower().strip()
            
            # Handle name questions smartly
            if "what's my name" in message_lower or "who am i" in message_lower:
                if username and username != "unknown_user":
                    response = f"Your name is {username}! How can I help you today?"
                else:
                    response = "I don't have your name yet. What should I call you?"
                
                if user_id:
                    self.store_user_memory(user_id, message, response, "general_chat", {}, username)
                return {"response": response, "intent": "general_chat"}
            
            if "what's your name" in message_lower or "who are you" in message_lower:
                response = "I'm your AI shopping assistant for Agentic AI Store! I help you find products and answer questions. What can I help you with?"
                if user_id:
                    self.store_user_memory(user_id, message, response, "general_chat", {}, username)
                return {"response": response, "intent": "general_chat"}
            
            # Enhanced LLM conversation
            if self.groq_client and not self.use_local_fallback:
                memory_context = self.get_user_memory_context(user_id, message, limit=3)
                
                prompt = f"""You are a friendly AI assistant for "Agentic AI Store". 

CONTEXT: {memory_context if memory_context else "New conversation"}
USER MESSAGE: "{message}"
USERNAME: {username if username and username != "unknown_user" else "Customer"}

RESPOND naturally and helpfully:
- If greeting, welcome them warmly to our store
- If thanking, acknowledge gracefully
- If asking about capabilities, mention product search & help
- Keep it conversational and under 80 words
- NO markdown formatting"""
                
                try:
                    response = self.groq_client.chat.completions.create(
                        messages=[{"role": "user", "content": prompt}],
                        model="llama-3.3-70b-versatile",
                        temperature=0.8,
                        max_tokens=100,
                        timeout=6
                    )
                    bot_response = response.choices[0].message.content.strip()
                    bot_response = self.clean_response_for_production(bot_response)
                except Exception:
                    bot_response = self.generate_simple_chat_response(message_lower, username, "")
            else:
                bot_response = self.generate_simple_chat_response(message_lower, username, "")
            
            if user_id:
                self.store_user_memory(user_id, message, bot_response, "general_chat", {}, username)
            
            return {"response": bot_response, "intent": "general_chat"}
            
        except Exception as e:
            logger.error(f"General chat error: {e}")
            return {"response": "Hello! How can I help you today?", "intent": "general_chat"}
    
    def handle_price_range_search(self, message, user_id=None, username=None):
        """Handle price range based product search with username support"""
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
                product_links += f"http://localhost:5173/products/{product['id']}\n"
            
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
            
            # Store enhanced memory
            if user_id:
                extra_context = {
                    "price_range": f"${min_price}-${max_price}" if min_price > 0 else f"under ${max_price}",
                    "category_filter": category,
                    "products_found": len(products),
                    "top_products": [p['name'] for p in products[:3]]
                }
                self.store_user_memory(user_id, message, bot_response, "price_range_search", extra_context, username)
            
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
        """Smart message processing with enhanced LLM responses"""
        try:
            if not message or not message.strip():
                return {"response": "Please send me a message and I'll help you!", "intent": "general_chat"}
            
            # Store/retrieve user info
            if user_id and username:
                self.store_user_profile(user_id, username, user_email)
            elif user_id and not username:
                username = self.get_user_name_from_memory(user_id)
            
            # Detect intent using smart LLM
            intent = self.detect_intent(message)
            logger.info(f"Intent: {intent} | User: {username or 'unknown'}")
            
            # Route to handlers
            if intent == "product_search":
                return self.handle_product_search(message, user_id, username)
            elif intent == "product_specific":
                return self.handle_product_specific(message, user_id, username)
            elif intent == "category_browse":
                return self.handle_category_browse(message, user_id, username)
            elif intent == "issue_report":
                return self.handle_issue_report(message, user_id, user_email, username)
            else:  # general_chat
                return self.handle_general_chat(message, user_id, username)
                
        except Exception as e:
            logger.error(f"Processing error: {e}")
            return {"response": "Sorry, I encountered an error. Please try again.", "intent": "general_chat"}

    def clear_user_memory(self, user_id):
        """Clear all memory for a specific user"""
        if not self.memory or not user_id:
            return False
        
        try:
            # Mem0 doesn't have direct clear method, so we'll add a clear marker
            clear_message = [
                {"role": "system", "content": "Memory cleared - fresh conversation start"}
            ]
            self.memory.add(clear_message, user_id=str(user_id))
            logger.info(f"Cleared memory for user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Error clearing user memory: {e}")
            return False

# Global instance - will be reloaded with new settings
chatbot_service = None

def get_chatbot_service():
    """Get or create chatbot service instance"""
    global chatbot_service
    if chatbot_service is None:
        chatbot_service = ChatbotService()
    return chatbot_service

# For backward compatibility
chatbot_service = get_chatbot_service()
