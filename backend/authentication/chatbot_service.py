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
        if groq_api_key and not self.use_local_fallback:
            try:
                self.groq_client = Groq(api_key=groq_api_key)
                logger.info("Groq client initialized successfully as backup")
                # If no primary LLM is set, use Groq
                if not self.llm_client:
                    self.llm_client = 'groq'
                    logger.info("Using Groq as primary LLM client")
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
                
                result = response.text.strip() if response.text else ""
                
                # Debug empty responses from Gemini
                if not result:
                    print(f"⚠️ Gemini returned empty response, trying Groq fallback")
                    logger.warning("Gemini returned empty response, falling back to Groq")
                    raise Exception("Empty Gemini response")
                
                return result
                
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
        """Simple fallback intent detection with spelling correction"""
        import re
        
        # Normalize common spelling variations/errors
        normalized_message = message_lower
        
        # Common spelling corrections for earbuds
        earbuds_variations = [
            ('earbuds', 'earbuds'), ('earphones', 'earbuds'), ('ear buds', 'earbuds'),
            ('earbud', 'earbuds'), ('ear phones', 'earbuds'), ('headphones', 'headphones'),
            ('headphone', 'headphones'), ('head phones', 'headphones')
        ]
        
        for variation, correct in earbuds_variations:
            normalized_message = normalized_message.replace(variation, correct)
        
        # Price range patterns (highest priority after product ID) - must have price indicator
        price_indicators = ['under $', 'below $', 'less than $', 'cheaper than $', 'between $', 'budget of $', 'around $']
        number_with_price = ['under 5', 'under 10', 'under 20', 'under 30', 'under 40', 'under 50', 'under 100', 'under 200', 'under 300', 'under 500', 'under 1000',
                            'below 20', 'below 30', 'below 40', 'below 50', 'below 100', 'below 200', 'below 500',
                            'between 50', 'between 100', 'around 100', 'around 200']
        
        if any(phrase in normalized_message for phrase in price_indicators + number_with_price):
            # Also check if there are digits indicating price
            if re.search(r'\b\d+\s*(dollars?|$)?\b', normalized_message):
                return "price_range_search"
        
        # Product ID patterns (highest priority)
        if any(phrase in normalized_message for phrase in ['product id', 'show product', 'product number', 'product 5', 'give me product', 'show me product']):
            return "product_specific"
        
        # Issue/problem patterns
        if any(phrase in normalized_message for phrase in ['problem', 'issue', 'complaint', 'broken', 'not working', 'defective', 'missing', 'wrong order', 'damaged']):
            return "issue_report"
        
        # Personal questions
        if any(phrase in normalized_message for phrase in ["what's my name", "who am i", "what's your name", "who are you"]):
            return "general_chat"
        
        # Greetings and social
        if any(word in normalized_message for word in ['hello', 'hi', 'hey', 'thanks', 'thank you', 'how are you', 'good morning', 'good afternoon', 'good evening']):
            return "general_chat"
        
        # Help and capabilities
        if any(phrase in normalized_message for phrase in ['help me', 'can you help', 'what can you do', 'how does this work', 'capabilities']):
            return "general_chat"
            
        # Category browsing
        if any(word in normalized_message for word in ['category', 'browse', 'section', 'electronics', 'clothing', 'home', 'kitchen', 'explore']):
            return "category_browse"
            
        # Product search keywords (broader) - include earbuds and common audio products
        product_keywords = ['find', 'search', 'need', 'want', 'buy', 'looking for', 'show me', 'get me', 'steel', 'bowl', 'phone', 'kitchen', 'laptop', 'headphones', 'mouse', 'keyboard', 'earbuds', 'speaker', 'wireless', 'bluetooth']
        if any(word in normalized_message for word in product_keywords):
            return "product_search"
        
        return "general_chat"

    def detect_intent_with_memory_requirement(self, message, user_context=""):
        """Enhanced intent detection that also determines if memory context is needed"""
        
        # DEBUG: Print intent detection process
        print(f"\n=== INTENT DETECTION DEBUG ===")
        print(f"Original message: '{message}'")
        
        # If LLM API is disabled, use simple fallback
        if not self.llm_client:
            simple_intent = self.simple_keyword_intent_detection(message.lower())
            print(f"Using simple fallback, detected intent: {simple_intent}")
            print(f"=== END INTENT DEBUG ===\n")
            return {
                "intent": simple_intent,
                "needs_memory": False,
                "confidence": "low"
            }
        
        prompt = f"""You are an intelligent AI assistant with deep e-commerce knowledge. Analyze the user's message to determine their intent and memory context.

USER MESSAGE: "{message}"
CONVERSATION CONTEXT: {user_context if user_context else "New conversation"}

INTENT ANALYSIS:
Identify the user's primary intent:

product_search: Discovering products based on needs

product_specific: Inquiring about a specific product

category_browse: Exploring product categories

price_range_search: Searching within a price range

general_chat: Casual conversation or help requests

issue_report: Reporting problems or service issues

CONTEXTUAL MEMORY:
Does the message depend on previous conversations?

needs_memory: true: References or builds on past conversations

needs_memory: false: Independent request with no prior context required

SUGGESTIONS:

Use past preferences if available to tailor responses.

If no preferences are provided, offer relevant suggestions based on the query.

OUTPUT FORMAT:
intent: [intent_name]
needs_memory: [true/false]
confidence: [high/medium/low]"""
        
        try:
            response_text = self.generate_llm_response(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=2000
            )
            
            print(f"LLM response: '{response_text}'")
            
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
                
                print(f"Parsed result: {result}")
                
                # Validate the response
                valid_intents = ["product_search", "product_specific", "category_browse", "price_range_search", "general_chat", "issue_report"]
                if result.get("intent") in valid_intents and "needs_memory" in result:
                    print(f"✓ Valid intent detected: {result['intent']}, Memory: {result['needs_memory']}")
                    print(f"=== END INTENT DEBUG ===\n")
                    logger.info(f"Intent: {result['intent']}, Memory needed: {result['needs_memory']}, Confidence: {result.get('confidence', 'unknown')}")
                    return result
                else:
                    print(f"✗ Invalid response format, using fallback")
                    raise ValueError("Invalid response format")
                    
            except (ValueError, KeyError) as e:
                print(f"✗ Failed to parse LLM response: {e}")
                simple_intent = self.simple_keyword_intent_detection(message.lower())
                print(f"Using simple fallback: {simple_intent}")
                print(f"=== END INTENT DEBUG ===\n")
                logger.warning(f"Failed to parse LLM intent response: {e}, using fallback")
                return {
                    "intent": simple_intent,
                    "needs_memory": False,
                    "confidence": "low"
                }
                
        except Exception as e:
            print(f"✗ LLM intent detection failed: {e}")
            simple_intent = self.simple_keyword_intent_detection(message.lower())
            print(f"Using simple fallback: {simple_intent}")
            print(f"=== END INTENT DEBUG ===\n")
            logger.error(f"Enhanced intent detection failed: {e}")
            return {
                "intent": simple_intent,
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
    
    def extract_product_name_from_message(self, message):
        """Extract product name from user message using LLM with minimal fallback"""
        print(f"\n=== PRODUCT NAME EXTRACTION DEBUG ===")
        print(f"Input message: '{message}'")
        
        if not self.llm_client:
            print("No LLM client available, returning None")
            print(f"=== END PRODUCT NAME DEBUG ===\n")
            return None
        
        # Use LLM for intelligent product name extraction
        prompt = f"""Extract the specific product name from this message. Be concise and precise.

MESSAGE: "{message}"

RULES:
- Extract only the main product type (laptop, headphones, etc.)
- Remove price constraints, locations, and descriptive words
- For "gift" requests: suggest specific product categories if context allows, otherwise return "none"
- Return "none" for vague requests like "something nice"
- Keep technical specs only if they define the product (wireless, bluetooth)

RESPOND WITH ONLY THE PRODUCT NAME :"""
        
        try:
            response_text = self.generate_llm_response(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,  # Lower temperature for more consistent extraction
                max_tokens=150     # Much lower token limit for concise responses
            )
            
            print(f"LLM response: '{response_text}'")
            
            # Check if response is empty or None
            if not response_text or response_text.strip() == "":
                print(f"✗ Empty LLM response, returning None")
                print(f"=== END PRODUCT NAME DEBUG ===\n")
                return None
            
            product_name = response_text.strip().lower()
            
            # Clean up response and remove common prefixes
            product_name = product_name.replace('product name:', '').strip()
            product_name = product_name.replace('answer:', '').strip()
            product_name = product_name.replace('result:', '').strip()
            product_name = product_name.replace('extracted product:', '').strip()
            
            # If response is too verbose (more than 50 chars), try to extract the actual product name
            if len(product_name) > 50:
                # Look for actual product name at the end or in specific patterns
                lines = product_name.split('\n')
                for line in reversed(lines):
                    # Look for lines that contain actual product names
                    if ':' in line and len(line.split(':')[-1].strip()) < 30:
                        extracted_part = line.split(':')[-1].strip()
                        if extracted_part and extracted_part != "none":
                            product_name = extracted_part
                            break
                    elif len(line.strip()) < 30 and line.strip() and not line.startswith('*'):
                        product_name = line.strip()
                        break
                
                # If still too long, return None
                if len(product_name) > 50:
                    print(f"✗ LLM response too verbose, returning None")
                    print(f"=== END PRODUCT NAME DEBUG ===\n")
                    return None
            
            # Clean up response
            if product_name and product_name != "none" and len(product_name) > 1:
                # Remove any extra quotation marks or formatting
                product_name = product_name.replace('"', '').replace("'", '').strip()
                
                # Check if it's actually a meaningful product name
                if product_name in ['gift', 'something', 'item', 'thing', 'stuff', 'product']:
                    print(f"✗ Generic term '{product_name}', returning None")
                    print(f"=== END PRODUCT NAME DEBUG ===\n")
                    return None
                
                print(f"✓ Extracted product name: '{product_name}'")
                print(f"=== END PRODUCT NAME DEBUG ===\n")
                return product_name
            
            print(f"✗ No valid product name found in LLM response: '{product_name}'")
            print(f"=== END PRODUCT NAME DEBUG ===\n")
            return None
            
        except Exception as e:
            print(f"✗ LLM extraction failed: {e}")
            print(f"=== END PRODUCT NAME DEBUG ===\n")
            return None

    def _extract_product_name_regex(self, message):
        """Helper method for regex-based product name extraction"""
        message_lower = message.lower()
        
        # Common product keywords that we should look for
        product_keywords = {
            'earbuds', 'earphones', 'headphones', 'speakers', 'mouse', 'keyboard', 
            'laptop', 'computer', 'phone', 'tablet', 'chair', 'desk', 'bowl', 
            'spoon', 'knife', 'plate', 'cup', 'mug', 'bottle', 'bag', 'watch',
            'shoes', 'shirt', 'jacket', 'pants', 'socks', 'hat', 'tv', 'monitor',
            'camera', 'microphone', 'cable', 'charger', 'case', 'stand', 'holder'
        }
        
        # Look for product keywords first
        found_products = []
        words = message_lower.split()
        
        for word in words:
            # Check exact matches
            if word in product_keywords:
                found_products.append(word)
            # Check partial matches (for compound words)
            for product in product_keywords:
                if product in word and len(word) > len(product):
                    found_products.append(product)
        
        if found_products:
            return found_products[0]
        
        # If no specific product found, try to extract by removing price terms
        price_terms = ['under', 'below', 'less than', 'cheaper than', 'between', 'budget of', 'around', 'price range', '$', 'dollars', 'dollar', 'less', 'than']
        stop_words = ['i', 'want', 'need', 'looking', 'for', 'good', 'quality', 'the', 'a', 'an', 'show', 'me', 'find', 'get']
        
        # Remove price indicators and numbers
        message_clean = re.sub(r'\b\d+\s*(dollars?|$)?\b', '', message_lower)
        message_clean = re.sub(r'\$\d+', '', message_clean)
        
        # Remove price terms
        for term in price_terms:
            message_clean = message_clean.replace(term, ' ')
        
        # Remove stop words
        words = message_clean.split()
        filtered_words = [word for word in words if word not in stop_words and len(word) > 2]
        
        if filtered_words:
            return ' '.join(filtered_words[:2])  # Take first 2 meaningful words
        
        return None

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

    def handle_product_search(self, message, user_id=None, username=None, memory_context=""):
        """Smart product search with enhanced LLM prompting"""
        try:
            # Use provided memory context
            if memory_context:
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
    
    def handle_product_specific(self, message, user_id=None, username=None, memory_context=""):
        """Smart specific product handler"""
        try:
            # Use provided memory context  
            if memory_context:
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
    
    def handle_category_browse(self, message, user_id=None, username=None, memory_context=""):
        """Smart category browsing with enhanced LLM"""
        try:
            # Use provided memory context
            if memory_context:
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
    
    def handle_issue_report(self, message, user_id=None, user_email=None, username=None, memory_context=""):
        """Handle issue reporting"""
        try:
            # Use provided memory context
            if memory_context:
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
    
    def handle_general_chat(self, message, user_id=None, username=None, memory_context=""):
        """Pure LLM-based general conversation with smart context understanding"""
        try:
            # Use provided memory context
            if memory_context:
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
    
    def handle_price_range_search(self, message, user_id=None, username=None, memory_context=""):
        """Handle price range based product search with username support"""
        try:
            # Use provided memory context
            if memory_context:
                logger.info(f"Price range search using memory context: {memory_context[:50]}...")
            
            # DEBUG: Print original message
            print(f"\n=== PRICE RANGE SEARCH DEBUG ===")
            print(f"Original message: '{message}'")
            
            # Extract price range
            price_range = self.extract_price_range_from_message(message)
            print(f"Extracted price range: {price_range}")
            
            if not price_range:
                return {
                    "response": "I couldn't understand the price range you're looking for. Could you please specify it more clearly? For example: 'products under $50' or 'between $20 to $100'",
                    "products": [],
                    "intent": "price_range_search"
                }
            
            min_price, max_price = price_range
            print(f"Price range: ${min_price} - ${max_price}")
            
            # Extract category and product name from message
            category = self.extract_category_from_message(message)
            print(f"Extracted category: {category}")
            
            product_name = self.extract_product_name_from_message(message)
            print(f"Extracted product name: '{product_name}'")
            
            # Search for products in price range with product name filter
            if product_name and product_name != "none":
                print(f"Searching with product name: '{product_name}'")
                # First search by product name and then filter by price
                products = get_vector_service().search_products(product_name, k=30)  # Get more for filtering
                print(f"Found {len(products)} products for '{product_name}'")
                
                # Filter by relevance and price range
                filtered_products = []
                product_keywords = product_name.lower().split()
                
                for product in products:
                    price = float(product.get('price', 0))
                    product_name_lower = product['name'].lower()
                    category_lower = product.get('category', '').lower()
                    
                    # Check relevance - product name should contain keywords
                    relevance_score = 0
                    for keyword in product_keywords:
                        if keyword in product_name_lower:
                            relevance_score += 2  # Higher score for name match
                        elif keyword in category_lower:
                            relevance_score += 1  # Lower score for category match
                    
                    # Only include if relevant AND within price range
                    if relevance_score > 0 and min_price <= price <= max_price:
                        product['relevance_score'] = relevance_score
                        filtered_products.append(product)
                        print(f"  ✓ {product['name']} - ${price} (relevance: {relevance_score})")
                    elif min_price <= price <= max_price:
                        print(f"  ✗ {product['name']} - ${price} (irrelevant: {relevance_score})")
                    else:
                        print(f"  ✗ {product['name']} - ${price} (outside price range)")
                
                # Sort by relevance score (highest first) and take top results
                filtered_products.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
                products = filtered_products[:10]  # Limit to 10 results
                print(f"Final filtered products: {len(products)}")
            else:
                print("No specific product name found, searching by price range only")
                # Search by price range only
                products = get_vector_service().search_products_by_price_range(
                    min_price=min_price, 
                    max_price=max_price, 
                    category_filter=category,
                    k=10
                )
                print(f"Found {len(products)} products in price range")
            
            print(f"=== END DEBUG ===\n")
            
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
            product_name_text = f" for '{product_name}'" if product_name and product_name != "none" else ""
            category_text = f" in {category}" if category else ""
            
            products_text = ""
            product_links = ""
            for i, product in enumerate(products[:5], 1):
                products_text += f"{i}. {product['name']} - ${product['price']}\n   Category: {product['category']}\n   {product['description'][:80]}...\n\n"
                product_links += f"http://localhost:5173/products/{product['id']}\n"
            
            # Include memory context in prompt if available
            context_prompt = f"\nPREVIOUS CONTEXT: {memory_context}" if memory_context else ""
            
            # Enhanced prompt that considers memory context
            if memory_context and not product_name:
                # When we have context but no specific product name, use context to understand what they want
                prompt = f"""You are a helpful e-commerce assistant. User is specifying a budget for their previous request: "{message}"{context_prompt}

Based on the context and their budget {price_text}, I found {len(products)} suitable products:
{products_text}

RESPOND with a brief, natural response that:
1. References their previous conversation context
2. Confirms the budget fits their needs  
3. Highlights the relevant products
4. Encourages them to check the options

Keep it conversational, helpful, and under 80 words. NO markdown formatting."""
            else:
                prompt = f"""You are a helpful e-commerce assistant. User is looking for products{product_name_text} in price range {price_text}{category_text}: "{message}"{context_prompt}

Found {len(products)} products matching their criteria:
{products_text}

RESPOND with a brief, natural response that:
1. Confirms their search
2. Mentions the number of products found
3. Highlights the products
4. Encourages them to check the links

Keep it conversational, helpful, and under 80 words. NO markdown formatting."""
            
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
            
            # Get memory context once if needed for any intent
            memory_context = ""
            if needs_memory and user_id:
                memory_context = self.get_user_memory_context(user_id, message, limit=3)
                logger.info(f"Using memory context: {memory_context[:50]}...")
            
            # Route to handlers with memory context
            if intent == "product_search":
                return self.handle_product_search(message, user_id, username, memory_context)
            elif intent == "product_specific":
                return self.handle_product_specific(message, user_id, username, memory_context)
            elif intent == "category_browse":
                return self.handle_category_browse(message, user_id, username, memory_context)
            elif intent == "price_range_search":
                return self.handle_price_range_search(message, user_id, username, memory_context)
            elif intent == "issue_report":
                return self.handle_issue_report(message, user_id, user_email, username, memory_context)
            else:  # general_chat
                return self.handle_general_chat(message, user_id, username, memory_context)
                
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
