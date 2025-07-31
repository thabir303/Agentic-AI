import os
import json
import re
import logging
from datetime import datetime
from groq import Groq
import google.generativeai as genai
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
        
        # Initialize Gemini client with API key (Primary choice)
        gemini_api_key = os.getenv('GEMINI_API_KEY')
        if gemini_api_key and not self.use_local_fallback:
            try:
                genai.configure(api_key=gemini_api_key)
                # Use faster flash model to avoid rate limits
                self.gemini_model = genai.GenerativeModel('gemini-2.5-pro')
                # Test the connection
                test_response = self.gemini_model.generate_content("Hi")
                logger.info("Gemini 2.5 Pro client initialized successfully")
                self.llm_client = 'gemini'
            except Exception as e:
                logger.error(f"Failed to initialize Gemini client: {e}")
                logger.warning("Falling back to Groq client")
                self.gemini_model = None
                self.llm_client = None
        else:
            logger.warning("No Gemini API key found or local fallback enabled")
            self.gemini_model = None
            self.llm_client = None
        
        # Initialize Groq client as fallback
        groq_api_key = os.getenv('GROQ_API_KEY')
        if groq_api_key and not self.use_local_fallback and not self.llm_client:
            try:
                self.groq_client = Groq(api_key=groq_api_key)
                logger.info("Groq client initialized as fallback")
                self.llm_client = 'groq'
            except Exception as e:
                logger.error(f"Failed to initialize Groq client: {e}")
                self.groq_client = None
        else:
            if self.use_local_fallback:
                logger.warning("Local fallback mode enabled, Groq client disabled")
            else:
                logger.warning("No Groq API key found or Gemini is primary")
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
    
    def generate_llm_response(self, messages, temperature=0.7, max_tokens=5000):
        """Generate response using available LLM (Gemini primary, Groq fallback)"""
        try:
            if self.llm_client == 'gemini' and self.gemini_model:
                # Convert messages to Gemini format
                prompt_parts = []
                for msg in messages:
                    role = msg.get('role', 'user')
                    content = msg.get('content', '')
                    if role == 'system':
                        prompt_parts.append(f"System: {content}")
                    elif role == 'user':
                        prompt_parts.append(f"User: {content}")
                    elif role == 'assistant':
                        prompt_parts.append(f"Assistant: {content}")
                
                prompt = "\n".join(prompt_parts)
                
                # Generate response with Gemini
                response = self.gemini_model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        temperature=temperature,
                        max_output_tokens=max_tokens,
                    )
                )
                
                return response.text.strip()
                
            elif self.llm_client == 'groq' and self.groq_client:
                # Use Groq as fallback
                response = self.groq_client.chat.completions.create(
                    messages=messages,
                    model="llama-3.3-70b-versatile",
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                return response.choices[0].message.content.strip()
            
            else:
                logger.error("No LLM client available")
                return "I'm sorry, I'm currently unavailable. Please try again later."
                
        except Exception as e:
            logger.error(f"Error generating LLM response: {e}")
            # Try fallback if primary fails
            if self.llm_client == 'gemini' and self.groq_client:
                try:
                    logger.info("Falling back to Groq after Gemini failure")
                    response = self.groq_client.chat.completions.create(
                        messages=messages,
                        model="llama-3.3-70b-versatile",
                        temperature=temperature,
                        max_tokens=max_tokens
                    )
                    return response.choices[0].message.content.strip()
                except Exception as fallback_error:
                    logger.error(f"Fallback also failed: {fallback_error}")
            
            return "I'm experiencing technical difficulties. Please try again in a moment."
    
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

    def detect_intent_with_memory_requirement(self, message, user_context=""):
        """Enhanced intent detection that also determines if memory context is needed"""
        
        # If LLM API is disabled, use simple fallback
        if not self.llm_client:
            return {
                "intent": self.simple_keyword_intent_detection(message.lower()),
                "needs_memory": False,
                "confidence": "low"
            }
        
        prompt = f"""You are an intelligent e-commerce assistant that analyzes user messages to determine:
1. PRIMARY INTENT
2. WHETHER PREVIOUS CONVERSATION CONTEXT/MEMORY IS NEEDED

USER MESSAGE: "{message}"
AVAILABLE CONTEXT: {user_context if user_context else "New conversation"}

AVAILABLE INTENTS:
1. product_search - User wants to find/discover products 
2. product_specific - User wants details about a specific product (mentions product ID)
3. category_browse - User wants to explore product categories
4. general_chat - Greetings, personal questions, casual conversation
5. issue_report - Problems, complaints, technical issues

MEMORY REQUIREMENTS ANALYSIS:
- NEEDS MEMORY: If user references previous conversation ("that product", "the one you showed", "like before", "continue our chat", "remember when", "as I mentioned")
- NEEDS MEMORY: If asking personal questions ("what's my name", "my previous orders", "our last conversation")
- NEEDS MEMORY: If follow-up questions ("more details", "tell me about that", "the other options")
- NO MEMORY: If completely new topic, greeting, specific product ID, clear standalone query

EXAMPLES:
"Hi there!" → intent: general_chat, needs_memory: false
"Show me stainless steel bowls" → intent: product_search, needs_memory: false  
"What's my name?" → intent: general_chat, needs_memory: true
"Tell me more about that product" → intent: product_specific, needs_memory: true
"I want the jacket you showed earlier" → intent: product_search, needs_memory: true
"Product ID 123 details" → intent: product_specific, needs_memory: false
"Browse electronics" → intent: category_browse, needs_memory: false
"Thanks for the help!" → intent: general_chat, needs_memory: false
"My order is missing" → intent: issue_report, needs_memory: false

RESPOND in this exact format:
intent: intent_name
needs_memory: true/false
confidence: high/medium/low"""
        
        try:
            response_text = self.generate_llm_response(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=2000
            )
            
            # Parse simple text response
            try:
                lines = response_text.strip().split('\n')
                result = {}
                
                for line in lines:
                    if ':' in line:
                        key, value = line.split(':', 1)
                        key = key.strip().lower()
                        value = value.strip().lower()
                        
                        if key == "intent":
                            result["intent"] = value
                        elif key == "needs_memory":
                            result["needs_memory"] = value == "true"
                        elif key == "confidence":
                            result["confidence"] = value
                
                # Validate the response
                valid_intents = ["product_search", "product_specific", "category_browse", "general_chat", "issue_report"]
                if result.get("intent") in valid_intents and "needs_memory" in result:
                    logger.info(f"Intent: {result['intent']}, Memory needed: {result['needs_memory']}, Confidence: {result.get('confidence', 'unknown')}")
                    return result
                else:
                    raise ValueError("Invalid response format")
                    
            except (ValueError, KeyError) as e:
                logger.warning(f"Failed to parse LLM intent response: {e}, using fallback")
                return {
                    "intent": self.simple_keyword_intent_detection(message.lower()),
                    "needs_memory": False,
                    "confidence": "low"
                }
                
        except Exception as e:
            logger.error(f"Enhanced intent detection failed: {e}")
            return {
                "intent": self.simple_keyword_intent_detection(message.lower()),
                "needs_memory": False,
                "confidence": "low"
            }

    def detect_intent(self, message, user_context=""):
        """Backward compatibility method - just returns intent name"""
        result = self.detect_intent_with_memory_requirement(message, user_context)
        return result["intent"]
    
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

    def handle_product_search(self, message, user_id=None, username=None, needs_memory=False):
        """Smart product search with enhanced LLM prompting"""
        try:
            # Get memory context only if needed
            memory_context = ""
            if needs_memory and user_id:
                memory_context = self.get_user_memory_context(user_id, message, limit=3)
                logger.info(f"Product search using memory context: {memory_context[:50]}...")
            
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
            products_text = "\n".join([f"• {p['name']} - ${p['price']} ({p['category']})" for p in products[:5]])
            price_text = f" within ${price_range[0]}-${price_range[1]}" if price_range else ""
            
            # Include memory context in prompt if available
            context_prompt = f"\nPREVIOUS CONTEXT: {memory_context}" if memory_context else ""
            
            prompt = f"""You are a helpful e-commerce assistant. A customer searched: "{message}"{price_text}{context_prompt}

PRODUCTS FOUND:
{products_text}

RESPOND with:
1. Brief acknowledgment of their search
2. Present the products naturally
3. Mention key features/price if relevant
4. Ask if they want more details

Keep it conversational, helpful, and under 100 words. NO markdown formatting."""
            
            # Generate response
            try:
                bot_response = self.generate_llm_response(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.7,
                    max_tokens=5000
                )
                bot_response = self.clean_response_for_production(bot_response)
            except Exception:
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
    
    def handle_product_specific(self, message, user_id=None, username=None, needs_memory=False):
        """Smart specific product handler"""
        try:
            # Get memory context only if needed (e.g., "that product", "the one you showed")
            memory_context = ""
            if needs_memory and user_id:
                memory_context = self.get_user_memory_context(user_id, message, limit=3)
                logger.info(f"Product specific using memory context: {memory_context[:50]}...")
            
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
            
            # Include memory context in prompt if available
            context_prompt = f"\nPREVIOUS CONTEXT: {memory_context}" if memory_context else ""
            
            # Smart LLM response or simple fallback
            prompt = f"""User wants details about this specific product: "{message}"{context_prompt}

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
                bot_response = self.generate_llm_response(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=5000
                )
                bot_response = self.clean_response_for_production(bot_response)
            except Exception:
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
    
    def handle_category_browse(self, message, user_id=None, username=None, needs_memory=False):
        """Smart category browsing with enhanced LLM"""
        try:
            # Get memory context only if needed
            memory_context = ""
            if needs_memory and user_id:
                memory_context = self.get_user_memory_context(user_id, message, limit=3)
                logger.info(f"Category browse using memory context: {memory_context[:50]}...")
            
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
            
            # Include memory context in prompt if available
            context_prompt = f"\nPREVIOUS CONTEXT: {memory_context}" if memory_context else ""
            
            prompt = f"""User wants to browse "{category}" category: "{message}"{context_prompt}

PRODUCTS FOUND:
{products_text}

RESPOND with:
1. Welcome them to the category
2. Show the products naturally  
3. Encourage exploration
Keep it conversational and under 100 words. NO markdown."""
            
            try:
                bot_response = self.generate_llm_response(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.7,
                    max_tokens=5000
                )
                bot_response = self.clean_response_for_production(bot_response)
            except Exception:
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
    
    def handle_issue_report(self, message, user_id=None, user_email=None, username=None, needs_memory=False):
        """Handle issue reporting"""
        try:
            # Get memory context only if needed (for contextual issues)
            memory_context = ""
            if needs_memory and user_id:
                memory_context = self.get_user_memory_context(user_id, message, limit=3)
                logger.info(f"Issue report using memory context: {memory_context[:50]}...")
            
            # Create issue in database
            issue = Issue.objects.create(
                username=username or "Anonymous",
                email=user_email or "",
                message=message,
                status="pending"
            )
            
            # Include memory context in prompt if available
            context_prompt = f"\nPREVIOUS CONTEXT: {memory_context}" if memory_context else ""
            
            # Generate empathetic response
            prompt = f"""
            A user has reported an issue: "{message}"{context_prompt}
            
            Provide a helpful, empathetic response that:
            1. Acknowledges their concern
            2. Assures them it will be addressed
            3. Provides an issue reference number: #{issue.id}
            4. Offers additional assistance
            Keep it professional and caring, under 150 words.
            
            Response:"""
            
            bot_response = self.generate_llm_response(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.6,
                max_tokens=5000
            )
            
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
    
    def handle_general_chat(self, message, user_id=None, username=None, needs_memory=False):
        """Pure LLM-based general conversation with smart context understanding"""
        try:
            # Enhanced LLM conversation with smart context understanding
            memory_context = ""
            if needs_memory and user_id:
                memory_context = self.get_user_memory_context(user_id, message, limit=3)
                logger.info(f"General chat using memory context: {memory_context[:50]}...")
            
            # Include memory context in prompt if available
            context_prompt = f"\nCONTEXT: {memory_context}" if memory_context else "\nCONTEXT: New conversation"
            
            prompt = f"""You are a friendly AI assistant for "Agentic AI Store". 

USER MESSAGE: "{message}"
USERNAME: {username if username and username != "unknown_user" else "Customer"}{context_prompt}

INTELLIGENT RESPONSE RULES:
- If they ask their name: Use their username if available, otherwise ask politely
- If they ask your name: Introduce yourself as AI shopping assistant for Agentic AI Store  
- If greeting: Welcome them warmly to our store
- If thanking: Acknowledge gracefully and offer continued help
- If asking about capabilities: Mention product search, browsing, and customer support
- If casual conversation: Respond naturally while staying helpful and store-focused
- If referencing previous conversation: Use the context provided
- Keep it conversational, helpful, and under 100 words
- NO markdown formatting

RESPOND naturally and contextually:"""
            
            try:
                bot_response = self.generate_llm_response(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.8,
                    max_tokens=5000
                )
                bot_response = self.clean_response_for_production(bot_response)
                
                # Special handling for name questions using LLM context
                message_lower = message.lower()
                if ("what's my name" in message_lower or "who am i" in message_lower) and username and username != "unknown_user":
                    bot_response = f"Your name is {username}! {bot_response}"
                
            except Exception as e:
                logger.warning(f"LLM general chat failed: {e}, using fallback")
                bot_response = self.generate_simple_chat_response(message.lower(), username, memory_context)
            
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
            
            bot_response = self.generate_llm_response(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=5200
            )
            
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

    def get_user_context_for_intent(self, user_id, username=None):
        """Get relevant user context for intent detection"""
        if not user_id:
            return "New conversation"
            
        try:
            # Try to get recent conversations from memory
            context_parts = []
            
            # From Mem0 memory
            if self.memory:
                try:
                    recent_memories = self.memory.get_all(user_id=str(user_id), limit=3)
                    if recent_memories:
                        for memory in recent_memories:
                            if 'messages' in memory and memory['messages']:
                                last_msg = memory['messages'][-1]['content'][:50]
                                context_parts.append(f"Recent: {last_msg}")
                except Exception as e:
                    logger.debug(f"Could not get Mem0 context: {e}")
            
            # From local memory fallback
            if hasattr(self, 'local_memory') and str(user_id) in self.local_memory:
                recent_local = self.local_memory[str(user_id)][-2:]  # Last 2 conversations
                for memory in recent_local:
                    context_parts.append(f"Previous intent: {memory.get('intent', 'unknown')}")
            
            # Add username context
            if username:
                context_parts.append(f"User: {username}")
            
            return " | ".join(context_parts) if context_parts else "New conversation"
            
        except Exception as e:
            logger.debug(f"Error getting user context: {e}")
            return "New conversation"

    def process_message(self, message, user_id=None, user_email=None, username=None):
        """Smart message processing with enhanced LLM responses and memory management"""
        try:
            if not message or not message.strip():
                return {"response": "Please send me a message and I'll help you!", "intent": "general_chat"}
            
            # Store/retrieve user info
            if user_id and username:
                self.store_user_profile(user_id, username, user_email)
            elif user_id and not username:
                username = self.get_user_name_from_memory(user_id)
            
            # Get user context for better intent detection
            user_context = self.get_user_context_for_intent(user_id, username)
            
            # Enhanced intent detection with memory requirement analysis
            intent_result = self.detect_intent_with_memory_requirement(message, user_context)
            intent = intent_result["intent"]
            needs_memory = intent_result["needs_memory"]
            confidence = intent_result.get("confidence", "unknown")
            
            logger.info(f"Intent: {intent} | Memory needed: {needs_memory} | Confidence: {confidence} | User: {username or 'unknown'}")
            
            # Route to handlers with memory requirement
            if intent == "product_search":
                return self.handle_product_search(message, user_id, username, needs_memory)
            elif intent == "product_specific":
                return self.handle_product_specific(message, user_id, username, needs_memory)
            elif intent == "category_browse":
                return self.handle_category_browse(message, user_id, username, needs_memory)
            elif intent == "issue_report":
                return self.handle_issue_report(message, user_id, user_email, username, needs_memory)
            else:  # general_chat
                return self.handle_general_chat(message, user_id, username, needs_memory)
                
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
