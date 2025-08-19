import os
import json
import re
import logging
from datetime import datetime
from huggingface_hub import InferenceClient
from mem0 import MemoryClient
from django.conf import settings
from .vector_service import get_vector_service
from .models import Issue
from .markdown_to_text import markdown_to_text

logger = logging.getLogger(__name__)

class ChatbotService:
    def __init__(self):
        # Initialize ONLY Hugging Face InferenceClient 
        hf_token = os.getenv('HF_TOKEN')
        if hf_token:
            try:
                self.hf_client = InferenceClient(
                    model="openai/gpt-oss-120b",
                    token=hf_token
                )
                # Test the connection
                test_response = self.hf_client.chat_completion(
                    messages=[{"role": "user", "content": "Hi"}],
                    max_tokens=10
                )
                logger.info("Hugging Face InferenceClient with openai/gpt-oss-120b initialized successfully")
                self.llm_client = 'huggingface'
            except Exception as e:
                logger.error(f"Failed to initialize Hugging Face client: {e}")
                logger.error("HuggingFace is required")
                self.hf_client = None
                self.llm_client = None
        else:
            logger.warning("No HF_TOKEN found")
            self.hf_client = None
            self.llm_client = None
        
        # Initialize mem0 client with API key  
        mem0_api_key = os.getenv('MEM0_API_KEY')
        self.use_mem0 = False
        
        if mem0_api_key:
            try:
                self.memory = MemoryClient(api_key=mem0_api_key)
                self.use_mem0 = True
                logger.info("Mem0 client initialized successfully with API key")
            except Exception as e:
                logger.error(f"Failed to initialize Mem0 client: {e}")
                logger.warning("Using local memory storage")
                self.memory = None
                self.use_mem0 = False
        else:
            logger.warning("No Mem0 API key found, using local memory storage")
            self.memory = None
            self.use_mem0 = False
            
        # Initialize local memory for backup storage
        self.local_memory = {}
        
        # Backward compatibility: alias memory_client to memory
        self.memory_client = self.memory
    
    def generate_llm_response(self, messages, temperature=0.7, max_tokens=5000):
        """Generate response using HuggingFace InferenceClient"""
        try:
            if self.llm_client == 'huggingface' and self.hf_client:
                # Use Hugging Face InferenceClient with openai/gpt-oss-120b
                response = self.hf_client.chat_completion(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                
                # Safely extract content with proper null checking
                if response and hasattr(response, 'choices') and response.choices:
                    content = response.choices[0].message.content
                    if content is not None:
                        result = content.strip()
                    else:
                        result = ""
                else:
                    result = ""
                
                # Debug empty responses from HuggingFace
                if not result:
                    logger.error("HuggingFace returned empty response")
                    return "I'm sorry, I couldn't generate a response. Please try rephrasing your question."
                
                return result
            
            else:
                logger.error("HuggingFace LLM client not available")
                return "I'm sorry, I'm currently unavailable. Please try again later."
                
        except Exception as e:
            logger.error(f"Error generating HuggingFace LLM response: {e}")
            return "I'm sorry, I'm currently experiencing technical difficulties. Please try again later."

    def get_user_memory_context(self, user_id, current_message, limit=5):
        """Enhanced memory retrieval prioritizing recent chronological context"""
        if not user_id:
            return ""
        
        try:
            if self.memory:
                # PRIORITY 1: Get recent chronological memories (most important for context)
                try:
                    recent_memories = self.memory.get_all(user_id=str(user_id), limit=limit)
                    if recent_memories:
                        # Extract and filter recent conversation context
                        relevant_memories = []
                        for memory in recent_memories:
                            # Try different possible memory text fields
                            memory_text = ""
                            if isinstance(memory, dict):
                                if 'memory' in memory:
                                    memory_text = memory['memory'].strip()
                                elif 'messages' in memory and memory['messages']:
                                    # Extract content from message format
                                    last_msg = memory['messages'][-1]
                                    if isinstance(last_msg, dict) and 'content' in last_msg:
                                        memory_text = last_msg['content'].strip()
                                elif 'content' in memory:
                                    memory_text = memory['content'].strip()
                            
                            if memory_text and len(memory_text) > 10:
                                if not self._is_current_conversation(memory_text, current_message):
                                    relevant_memories.append(memory_text)
                        
                        if relevant_memories:
                            context = "Recent conversation: " + " | ".join(relevant_memories[:3])
                            logger.info(f"Retrieved {len(relevant_memories)} recent memories for user {user_id}")
                            return context
                except Exception as e:
                    logger.debug(f"Recent memory retrieval failed: {e}")
                
                # PRIORITY 2: Keyword search if recent memories failed
                try:
                    memory_results = self.memory.search(current_message, user_id=str(user_id))
                    if memory_results:
                        # Filter and format relevant memories
                        relevant_memories = []
                        for memory in memory_results[:limit]:
                            memory_text = memory.get('memory', '').strip()
                            if memory_text and len(memory_text) > 10:
                                if not self._is_current_conversation(memory_text, current_message):
                                    relevant_memories.append(memory_text)
                        
                        if relevant_memories:
                            context = "Related context: " + " | ".join(relevant_memories[:3])
                            logger.info(f"Retrieved {len(relevant_memories)} search-based memories for user {user_id}")
                            return context
                except Exception as e:
                    logger.debug(f"Search-based memory retrieval failed: {e}")
                
                return ""
            else:
                # Use local memory (chronological order)
                user_memories = self.local_memory.get(str(user_id), [])
                if user_memories:
                    recent_memories = user_memories[-limit:]
                    context = "Previous context: " + " | ".join([mem['content'] for mem in recent_memories])
                    return context
                return ""
            
        except Exception as e:
            logger.error(f"Error retrieving user memory: {e}")
            # Use local memory
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
    
    def _analyze_memory_importance(self, message, memory_context):
        """Analyze how crucial memory context is for this specific message"""
        if not memory_context:
            return "none"
        
        message_lower = message.lower()
        context_lower = memory_context.lower()
        
        # CRITICAL: Message has pronouns/references that need context
        critical_indicators = [
            'that product', 'those items', 'it', 'them', 'this one', 'these',
            'my budget', 'my order', 'my preference', 'my last search',
            'continue', 'also looking for', 'additionally', 'furthermore',
            'tell me more', 'what about', 'how about', 'similar to',
            'what did i', 'what was i', 'remember when i', 'like before'
        ]
        
        if any(indicator in message_lower for indicator in critical_indicators):
            return "critical"
        
        # HIGH: Budget/gift scenarios often need product preferences from context
        # Also conversational continuity for general chat
        high_indicators = [
            'budget is', 'budget of', 'price range', 'for her', 'for him', 'gift for',
            'under $', 'around $', 'between $', 'looking for something',
            'thanks for', 'thank you for', 'following up', 'as you mentioned'
        ]
        
        if any(indicator in message_lower for indicator in high_indicators):
            # Check if context has product preferences or previous conversation
            if any(word in context_lower for word in ['likes', 'prefer', 'interested', 'wants', 'needs', 'searched', 'bought']):
                return "high"
        
        # MEDIUM: General follow-up questions and conversational continuity
        medium_indicators = [
            'and', 'also', 'plus', 'what else', 'anything else', 'other options',
            'what can you', 'how do you', 'tell me about', 'speaking of'
        ]
        
        if any(indicator in message_lower for indicator in medium_indicators):
            return "medium"
        
        # LOW: General greetings but with some personalization potential
        low_indicators = [
            'hello', 'hi', 'hey', 'good morning', 'how are you',
            'what\'s up', 'thanks', 'thank you'
        ]
        
        if any(indicator in message_lower for indicator in low_indicators) and context_lower:
            return "low"
        
        return "low"
    
    def store_user_memory(self, user_id, user_message, bot_response, intent, extra_context=None, username=None):
        """Enhanced memory storage with better context and username tracking"""
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
                # Use local memory
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
            # Use local storage when Mem0 fails
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
            logger.info(f"Stored backup local memory for user {user_id} ({username})")

    def store_user_profile(self, user_id, username, user_email=None):
        """Store user profile information in memory for personalization"""
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
                # Use local memory
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
            # Use local storage
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
            logger.info(f"Stored backup profile for user {user_id}: {username}")

    def get_user_name_from_memory(self, user_id):
        """Get username from memory (local or Mem0)"""
        if not user_id:
            return None
        
        try:
            # Try Mem0 first
            if self.use_mem0 and self.memory:
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
            
            # Check local memory
            if hasattr(self, 'local_memory') and str(user_id) in self.local_memory:
                memories = self.local_memory[str(user_id)]
                for memory in memories:
                    if memory.get('username') and memory.get('username') != 'unknown_user':
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

    def detect_hybrid_intent(self, message, user_context=""):
        """Simple intent wrapper - just use main detect_intent"""
        return self.detect_intent(message, user_context)
    
    def detect_intent_with_memory_requirement(self, message, user_context=""):
        """Enhanced intent detection that also determines if memory context is needed"""
        
        # DEBUG: Print intent detection process
        print(f"\n=== INTENT DETECTION DEBUG ===")
        print(f"Original message: '{message}'")
        print(f"User context: '{user_context[:100]}...' " if user_context else "No user context")
        
        
        prompt = f"""You are an intelligent AI assistant with deep e-commerce knowledge. Analyze the user's message to determine their intent and memory context.

USER MESSAGE: "{message}"
CONVERSATION CONTEXT: {user_context if user_context else "New conversation"}

INTENT ANALYSIS:
Identify the user's primary intent by carefully checking for price indicators FIRST:

CRITICAL INSTRUCTION: Look beyond the provided examples. Use semantic understanding, context clues, synonyms, and variations to detect related patterns that fall under each intent category, even if not explicitly listed in examples.

price_range_search: **PRIORITY INTENT** - Any message mentioning price/budget/cost constraints
  - Keywords: "above $X", "below $X", "under $X", "over $X", "between $X and $Y", "around $X", "budget", "cost","affordable", "price", "$X to $Y", "within $X", "less than $X", "more than $X", "up to $X", "maximum $X", "minimum $X" and so on...
  - Examples: "wireless mouse above $40", "books under 20 dollars", "laptop within my budget of $800"

product_search: General product discovery/asking WITHOUT price constraints
  - Only if NO price/budget/cost mentioned
  - Examples: "show me wireless gaming mouse", "good books", "laptop recommendations"
  - DETECT BEYOND EXAMPLES: Any product requests, recommendations, suggestions, discovery queries, or "find me" type messages without price constraints

product_specific: Inquiring about a specific product with product id
  - Examples: "product 154", "show me product id 23"
  - DETECT BEYOND EXAMPLES: Any reference to specific product numbers, IDs, codes, or direct product identification

category_browse: Exploring product categories
  - Categories: books, electronics, clothing, home & kitchen, toys & games
  - Examples: "show electronics", "browse books and clothing"
  - DETECT BEYOND EXAMPLES: Any requests to explore, view, browse, discover, or navigate product categories, sections, departments, or groups

general_chat: Casual conversation or help requests
  - Examples: "hello", "how are you", "thank you"
  - DETECT BEYOND EXAMPLES: Any greetings, casual talk, gratitude, general questions, conversational exchanges, or non-shopping related chat

issue_report: Reporting problems or service issues
  - Examples: "I have a problem", "this is broken", "complaint"
  - DETECT BEYOND EXAMPLES: Any complaints, problems, issues, concerns, dissatisfaction, bugs, errors, or service-related difficulties

CONTEXTUAL MEMORY ANALYSIS:
Does the message depend on previous conversations?

needs_memory: true: References or builds on past conversations (mentions "that", "it", "them", "my budget", "for her", "gift", follow-up questions, continuation words)

needs_memory: false: Independent request with no prior context required

ENHANCED MEMORY DETECTION:
- Budget/gift scenarios often need previous product preferences
- Follow-up questions ("tell me more", "what about") need context
- Pronoun references ("it", "that product", "those") need context  
- Continuation words ("also", "and", "additionally") need context
- Personal requests ("my order", "my preference") need context

SUGGESTIONS:
- Use past preferences if available to tailor responses.
- If no preferences, offer relevant suggestions based on the query.

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
                    print(f"✗ Invalid response format, using keyword detection")
                    raise ValueError("Invalid response format")
                    
            except (ValueError, KeyError) as e:
                
                logger.warning(f"Failed to parse LLM intent response: {e}, using keyword detection")
                return {
                    "intent": "intent not_detected",
                    "needs_memory": False,
                    "confidence": "low"
                }
                
        except Exception as e:
        
            logger.error(f"Enhanced intent detection failed: {e}")
            return {
                "intent": "intent_not_detected",
                "needs_memory": False,
                "confidence": "low"
            }

    def detect_intent(self, message, user_context=""):
        """Backward compatibility method - just returns intent name"""
        result = self.detect_intent_with_memory_requirement(message, user_context)
        return result["intent"]
    
    def clean_response_for_production(self, response_text):
        if not response_text:
            return response_text
        
        clean_text = markdown_to_text(response_text)
        
        clean_text = clean_text.replace('**', '').replace('*', '')
        clean_text = clean_text.replace('__', '').replace('_', '')
        
        lines = [line.strip() for line in clean_text.split('\n') if line.strip()]
        clean_text = '\n'.join(lines)
        
        clean_text = clean_text.replace('# ', '').replace('## ', '').replace('### ', '')
        clean_text = clean_text.replace('- ', '• ').replace('* ', '• ')
        
        return clean_text.strip()
    
    def handle_memory_query(self, message, user_id=None, username=None, memory_context=""):
        message_lower = message.lower()
        
        user_memory = ""
        if user_id and memory_context:
            # Parse some recent activities from memory
            recent_activities = []
            if 'search' in memory_context.lower():
                recent_activities.append("searched for products")
            if 'buy' in memory_context.lower() or 'purchase' in memory_context.lower():
                recent_activities.append("looked at purchasing items")
            if 'category' in memory_context.lower():
                recent_activities.append("browsed product categories")
            if 'price' in memory_context.lower():
                recent_activities.append("checked price ranges")
            
            if recent_activities:
                activities_text = ", ".join(recent_activities)
                user_memory = f"I remember you recently {activities_text}. "
        
        username_part = f"{username}, " if username and username != "unknown_user" else ""
        
        response = f"Yes {username_part}I do remember our previous conversations! {user_memory}"
        response += "I use this conversation history to provide you with better, more personalized assistance. "
        response += "This helps me understand your preferences and continue our conversations naturally. "
        response += "Is there something specific you'd like me to help you with today?"
        
        if user_id:
            self.store_user_memory(user_id, message, response, "memory_query", {}, username)
        
        return {"response": response, "intent": "general_chat"}

    def detect_memory_query(self, message):
        """Detect if the user is asking about memory/remembering"""
        message_lower = message.lower()
        memory_keywords = [
            'can you remember', 'do you remember', 'remember my', 'remember our',
            'previous search', 'past search', 'last search', 'before',
            'conversation history', 'chat history', 'our history',
            'what we talked about', 'what i said', 'what i asked'
        ]
        return any(keyword in message_lower for keyword in memory_keywords)

    def generate_simple_chat_response(self, message_lower, username, memory_context):
        """Generate simple template-based chat responses when LLM is unavailable"""
        
        # Smart greeting logic - only greet when appropriate
        def should_greet():
            """Determine if we should include a greeting"""
            greetings = ['hello', 'hi', 'hey', 'good morning', 'good afternoon', 'good evening']
            return any(greeting in message_lower for greeting in greetings)
        
        # Only use username in greeting for initial hello, not every response
        user_greeting = f"Hello {username}! " if should_greet() and username and username != "unknown_user" else ""
        
        # Memory/remember questions
        if any(phrase in message_lower for phrase in ['can you remember', 'remember my', 'previous search', 'past search', 'do you remember', 'memory', 'history']):
            return "Yes, I do remember our previous conversations! I use this memory to provide you with better, more personalized assistance. This helps me understand your preferences and continue our conversations naturally. What would you like me to help you with?"
        
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
    
    def extract_product_name_from_message(self, message, memory_context=""):
        """Extract product name from user message using LLM with memory context support"""
        print(f"\n=== PRODUCT NAME EXTRACTION DEBUG ===")
        print(f"Input message: '{message}'")
        print(f"Memory context: '{memory_context}' " if memory_context else "No memory context")
        
        if not self.llm_client:
            print("No LLM client available, returning None")
            print(f"=== END PRODUCT NAME DEBUG ===\n")
            return None
        
        # Enhanced prompt that considers memory context for connected conversations
        context_info = f"\nPREVIOUS CONTEXT: {memory_context}" if memory_context else ""
        
        prompt = f"""Extract the specific product name from this message. Consider conversation context for better understanding.

MESSAGE: "{message}"{context_info}

INTELLIGENT EXTRACTION RULES:
- Extract complete product descriptions with modifiers/adjectives (e.g., "philosophy books", "gaming laptop", "wireless headphones")
- Keep important descriptive words that specify the type/category (philosophy, gaming, wireless, etc.)
- If current message mentions price/budget and context shows product preferences, extract from context
- For "budget is $X" with previous product mentions, return the products from context
- For gift scenarios: use recipient preferences from context if available
- Return "none" only if no product type can be determined from message OR context
- Prioritize context-based products for budget/price-only messages

Look beyond the provided examples. Use semantic understanding, context clues, synonyms, and variations to detect related patterns that fall under each intent category, even if not explicitly listed in examples.
EXAMPLES:
- Message: "I want Philosophy Book" → Return: "philosophy books"
- Message: "some affordable sci-fi novel" → Return: "sci-fi novel"
- Message: "affordable Sci-Fi Adventure Novel" → Return: "sci-fi adventure novel"
- Message: "budget is $30" + Context: "likes books and jewelry" → Return: "books jewelry"
- Message: "I want gaming laptop" → Return: "gaming laptop"
- Message: "wireless headphones" → Return: "wireless headphones"
- Message: "cheap electronics" → Return: "electronics"
- Message: "budget kitchen items" → Return: "kitchen items"
- Message: "something nice" + No context → Return: "none"

RESPOND WITH ONLY THE PRODUCT NAME(S):"""
        
        try:
            response_text = self.generate_llm_response(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,   
                max_tokens=150  
            )
            
            print(f"LLM response: '{response_text}'")
            
            # Check if response is empty or None
            if not response_text:
                print(f"✗ Empty/None LLM response, returning None")
                print(f"=== END PRODUCT NAME DEBUG ===\n")
                return None
            
            # Convert to string if not already and check if it's a valid response
            response_text = str(response_text).strip()
            if not response_text or response_text == "":
                print(f"✗ Empty LLM response after processing, returning None")
                print(f"=== END PRODUCT NAME DEBUG ===\n")
                return None
            
            # Check for error messages
            if "sorry" in response_text.lower() or "technical difficulties" in response_text.lower():
                print(f"✗ LLM returned error message, returning None")
                print(f"=== END PRODUCT NAME DEBUG ===\n")
                return None
            
            product_name = response_text.lower()
            
            # Clean up response and remove common prefixes
            product_name = product_name.replace('product name:', '').strip()
            product_name = product_name.replace('answer:', '').strip()
            product_name = product_name.replace('result:', '').strip()
            product_name = product_name.replace('extracted product:', '').strip()
            
            if len(product_name) > 50:
                lines = product_name.split('\n')
                for line in reversed(lines):
                    if ':' in line and len(line.split(':')[-1].strip()) < 30:
                        extracted_part = line.split(':')[-1].strip()
                        if extracted_part and extracted_part != "none":
                            product_name = extracted_part
                            break
                    elif len(line.strip()) < 30 and line.strip() and not line.startswith('*'):
                        product_name = line.strip()
                        break
                
                if len(product_name) > 50:
                    print(f"✗ LLM response too verbose, returning None")
                    print(f"=== END PRODUCT NAME DEBUG ===\n")
                    return None
            
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
            
            # Fallback: Simple regex-based product extraction
            return self._extract_product_name_regex(message)

    def _extract_product_name_regex(self, message):
        """Fallback regex-based product name extraction"""
        import re
        
        # Common product patterns
        product_patterns = [
            r'(?:suggest|find|show|get|want|need|looking for|search)\s+(?:me\s+)?(?:some\s+)?(?:affordable\s+|cheap\s+|budget\s+)?(.*?)(?:\s+under|\s+below|\s+around|\s+for|\s*$)',
            r'(?:affordable|cheap|budget|inexpensive)\s+(.*?)(?:\s+under|\s+below|\s+around|\s+for|\s*$)',
            r'(.*?)\s+(?:under|below|around|for)\s+\$?\d+',
            r'(.*?)\s+(?:book|novel|laptop|phone|headphone|game|toy|clothing|shirt|dress)',
            # Specific pattern for sci-fi variants
            r'(?:sci-fi|science fiction|sci fiction|scifi)\s+(.*?)(?:\s|$)',
            r'(.*?)\s+(?:sci-fi|science fiction|sci fiction|scifi)(?:\s|$)',
        ]
        
        message_lower = message.lower().strip()
        
        for pattern in product_patterns:
            match = re.search(pattern, message_lower)
            if match:
                extracted = match.group(1).strip()
                # Clean up common words
                extracted = re.sub(r'\b(some|any|good|best|nice|great)\b', '', extracted).strip()
                if extracted and len(extracted) > 2:
                    print(f"✓ Regex extracted product name: '{extracted}'")
                    return extracted
        
        # If no pattern matches, try to extract nouns (basic approach)
        words = message_lower.split()
        product_keywords = ['book', 'novel', 'laptop', 'phone', 'headphone', 'game', 'toy', 'clothing', 'shirt', 'dress', 'electronics', 'kitchen', 'sci-fi', 'scifi', 'science', 'fiction']
        
        for keyword in product_keywords:
            if keyword in message_lower:
                # Look for descriptive words before the keyword
                for i, word in enumerate(words):
                    if keyword in word:
                        if i > 0:
                            product_name = f"{words[i-1]} {keyword}"
                            print(f"✓ Keyword-based extraction: '{product_name}'")
                            return product_name
                        else:
                            print(f"✓ Keyword-based extraction: '{keyword}'")
                            return keyword
        
        print(f"✗ No product name found via regex")
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
        print(f"\n=== PRICE RANGE EXTRACTION DEBUG ===")
        print(f"Input message: '{message}'")
        
        if self.llm_client:
            try:
                prompt = f"""Extract the price range from the user's message. Return exact numbers only.

MESSAGE: "{message}"

IMPORTANT: If the message contains words like "affordable", "cheap", "budget", "inexpensive", "low cost" WITHOUT specific numbers, provide appropriate price ranges based on the product category:

AFFORDABILITY GUIDELINES:
- Books/Novels: affordable = $5-$25, cheap = $5-$15, budget = $5-$20
- Electronics/Gadgets: affordable = $15-$100, cheap = $10-$50, budget = $20-$80  
- Clothing: affordable = $10-$50, cheap = $5-$30, budget = $10-$40
- Home/Kitchen: affordable = $10-$75, cheap = $5-$40, budget = $15-$60
- Toys/Games: affordable = $5-$30, cheap = $3-$20, budget = $8-$25
- General/Unknown category: affordable = $10-$50, cheap = $5-$30, budget = $10-$40

SPECIFIC PRICE EXAMPLES:
-For "under/below $X": return min_price: 0, max_price: X
-For "around $X": return min_price: (X-50), max_price: (X+50)
-For "over/greater than $X": return min_price: X, max_price: 9999
-For "between $X and $Y": return min_price: X, max_price: Y
-For "budget is $X": return min_price: 0, max_price: X
-For X-Y range: return min_price: X, max_price: Y
-For "affordable Sci-Fi Adventure Novel": return min_price: 5, max_price: 25
-For any other form of price mention (like $X, "$X to $Y", "$X range", or similar): use the best guess for price extraction.
-For queries with no specific price mentioned (like “affordable t-shirts” or vague references to price), provide an estimated price range based on typical market rates for similar products (e.g., affordable t-shirts typically range from $10 to $50).
- Use NUMBERS ONLY (no "infinity" or text)

RESPONSE FORMAT (exact format required):
min_price: [number]
max_price: [number]

If no price found: none"""

                response_text = self.generate_llm_response(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,  
                    max_tokens=100     
                )
                
                print(f"LLM price extraction response: '{response_text}'")
                
                if response_text and response_text.strip().lower() != "none":
                    # Enhanced parsing with smart handling
                    lines = response_text.strip().split('\n')
                    min_price = None
                    max_price = None
                    
                    for line in lines:
                        if ':' in line:
                            key, value = line.split(':', 1)
                            key = key.strip().lower()
                            value = value.strip().lower()
                            
                            try:
                                if key == "min_price":
                                    min_price = int(value)
                                elif key == "max_price":
                                    # Handle special cases for max_price
                                    if value in ['infinity', 'inf', 'unlimited', 'no limit']:
                                        max_price = 9999  # Set reasonable upper limit
                                    else:
                                        max_price = int(value)
                            except ValueError:
                                # If parsing fails, try to extract numbers from the value
                                import re
                                numbers = re.findall(r'\d+', value)
                                if numbers:
                                    try:
                                        if key == "min_price":
                                            min_price = int(numbers[0])
                                        elif key == "max_price":
                                            max_price = int(numbers[0])
                                    except (ValueError, IndexError):
                                        continue
                    
                    # Validate and adjust the extracted range
                    if min_price is not None and max_price is not None:
                        # Ensure max_price is reasonable and greater than min_price
                        if max_price <= 0 or max_price > 50000:  # Cap at reasonable limit
                            max_price = 9999
                        if min_price < 0:
                            min_price = 0
                        if max_price <= min_price:
                            # If max is not greater than min, adjust based on context
                            if min_price == 0:
                                max_price = min_price + 1000  # Default range
                            else:
                                max_price = min_price + 500   # Reasonable increment
                        
                        print(f"✓ LLM extracted price range: ({min_price}, {max_price})")
                        print(f"=== END PRICE RANGE DEBUG ===\n")
                        return (min_price, max_price)
                    else:
                        print(f"✗ LLM response missing min_price or max_price, using regex")
                else:
                    print(f"✗ LLM returned 'none' or empty, using regex")
                    
            except Exception as e:
                print(f"✗ LLM price extraction failed: {e}, using regex")
        else:
            print("No LLM client available, using regex approach")
        
        # Use enhanced regex patterns
        print("Using regex for price extraction...")
        return self._extract_price_range_regex(message)

    # Filters the relevant products based on the user's query and a maximum number of products to return.
    def filter_relevant_products(self, products, query, max_products=3):
        return products[:max_products] if products else []

    def handle_product_search(self, message, user_id=None, username=None, memory_context=""):
        try:
            # Use provided memory context
            if memory_context:
                logger.info(f"Product search using memory context: {memory_context}...")
            
            # Enhanced product search with memory context awareness - NO price range extraction
            category = self.extract_category_from_message(message)
            
            # Smart product extraction considering memory context importance  
            product_name = self.extract_product_name_from_message(message, memory_context)
            
            # If no specific product found but we have memory context, try to extract preferences
            if (not product_name or product_name == "none") and memory_context:
                memory_importance = self._analyze_memory_importance(message, memory_context)
                if memory_importance in ["critical", "high"]:
                    # Try to extract product preferences from memory context directly
                    import re
                    
                    # Look for product mentions in memory context
                    product_pattern = r'(?:likes?|prefer|interested|want|need)(?:s)?\s+([^|.]+?)(?:\s*\||$|\.|,)'
                    match = re.search(product_pattern, memory_context.lower())
                    if match:
                        memory_products = match.group(1).strip()
                        if memory_products and len(memory_products) > 3:
                            product_name = memory_products
                            logger.info(f"Extracted product preferences from memory: '{product_name}'")
            
            # Use extracted product name for cleaner vector search, fallback to original message
            search_query = product_name if product_name and product_name != "none" else message
            
            # Enhance with memory preferences if available
            if memory_context and "likes" in memory_context.lower():
                import re
                likes_match = re.search(r'likes\s+([^|]+)', memory_context.lower())
                if likes_match:
                    preferences = likes_match.group(1).strip()
                    search_query += f" {preferences}"
                    logger.info(f"Enhanced search query with preferences: {search_query}")
            
            logger.info(f"Vector search query: '{search_query}' (extracted from: '{message}')")
            
            # Search products without price filtering (price range is handled by separate intent)
            products = get_vector_service().search_products(search_query, k=5, category_filter=category)
            
            if not products:
                response = "I couldn't find products matching your request. Could you try different keywords?"
                if user_id:
                    self.store_user_memory(user_id, message, response, "product_search", {}, username)
                return {"response": response, "products": [], "intent": "product_search"}
            
            # Enhanced LLM prompt for better responses (removed price_text)
            products_text = "\n".join([f"• {p['name']} - ${p['price']} ({p['category']})" for p in products[:5]])
            
            # Include memory context in prompt if available
            context_prompt = f"\nPREVIOUS CONTEXT: {memory_context}" if memory_context else ""
            
            prompt = f"""You are a helpful e-commerce assistant. A customer searched: "{message}"{context_prompt}

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
                bot_response = f"I found {len(products)} products for '{message}':\n\n{products_text}\n\nWould you like more details about any of these?"
            
            # Add product links
            product_links = "\n".join([f"🔗 http://localhost:5173/products/{p['id']}" for p in products])
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
                logger.info(f"Product specific using memory context: {memory_context}...")
            
            import re
            
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
            
            # Smart LLM response or simple template response
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
        """Smart category browsing with enhanced LLM and memory-aware suggestions"""
        try:
            # Use provided memory context
            if memory_context:
                logger.info(f"Category browse using memory context: {memory_context}...")
            
            category = self.extract_category_from_message(message)
            
            # Enhanced category detection using memory context
            if not category and memory_context:
                # Try to extract category preferences from memory context
                import re
                categories = get_vector_service().get_categories()
                for cat in categories:
                    if cat.lower() in memory_context.lower():
                        category = cat
                        logger.info(f"Found category '{category}' from memory context")
                        break
            
            if not category:
                categories = get_vector_service().get_categories()
                
                # Memory-aware category suggestion
                if memory_context:
                    context_prompt = f"\nPREVIOUS CONTEXT: {memory_context}"
                    suggestion_prompt = f"""User wants to browse categories: "{message}"{context_prompt}

Available categories: {', '.join(categories)}

Based on their message and previous context, suggest 1-2 most relevant categories and explain why.
Keep it helpful and under 80 words. NO markdown."""
                    
                    try:
                        response = self.generate_llm_response(
                            messages=[{"role": "user", "content": suggestion_prompt}],
                            temperature=0.7,
                            max_tokens=200
                        )
                        response = self.clean_response_for_production(response)
                    except Exception:
                        response = f"I can help you browse our categories! We have: {', '.join(categories)}. Which category interests you?"
                else:
                    response = f"I can help you browse our categories! We have: {', '.join(categories)}. Which category interests you?"
                
                if user_id:
                    self.store_user_memory(user_id, message, response, "category_browse", {"available_categories": categories}, username)
                return {"response": response, "products": [], "categories": categories, "intent": "category_browse"}
            
            products = get_vector_service().get_products_by_category(category, limit=5)
            
            if not products:
                response = f"I couldn't find products in {category} right now. Try another category or search for specific items!"
                if user_id:
                    self.store_user_memory(user_id, message, response, "category_browse", {}, username)
                return {"response": response, "products": [], "intent": "category_browse"}
            
            # Smart LLM response or simple template response
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
        """Handle issue reporting with memory-aware context understanding"""
        try:
            # Use provided memory context
            if memory_context:
                logger.info(f"Issue report using memory context: {memory_context}...")
            
            # Enhanced issue context extraction using memory
            issue_context = ""
            if memory_context:
                # Try to extract product or order related context from memory
                import re
                product_match = re.search(r'product\s+(?:id\s+)?(\d+|[a-zA-Z]+(?:\s+[a-zA-Z]+)*)', memory_context.lower())
                order_match = re.search(r'order|purchase|bought|ordered', memory_context.lower())
                
                if product_match or order_match:
                    issue_context = f" [Related context: {memory_context[:100]}...]"
                    logger.info(f"Enhanced issue with context: {issue_context}")
            
            # Create issue in database with enhanced context
            issue = Issue.objects.create(
                username=username or "Anonymous",
                email=user_email or "",
                message=message + issue_context,  # Add context to issue message
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
    
    def _extract_price_range_regex(self, message):
        """Fallback regex-based price range extraction with enhanced patterns"""
        import re
        
        price_range_patterns = [
            # Affordable and budget-friendly patterns (NEW)
            (r'affordable.*(?:book|novel|fiction)', lambda m: (5, 25)),
            (r'affordable.*(?:electronic|gadget|device)', lambda m: (15, 100)),
            (r'affordable.*(?:cloth|shirt|pant|dress)', lambda m: (10, 50)),
            (r'affordable.*(?:kitchen|home)', lambda m: (10, 75)),
            (r'affordable.*(?:toy|game)', lambda m: (5, 30)),
            (r'(?:cheap|budget|inexpensive|low.?cost).*(?:book|novel|fiction)', lambda m: (5, 25)),
            (r'(?:cheap|budget|inexpensive|low.?cost).*(?:electronic|gadget|device)', lambda m: (15, 100)),
            (r'(?:cheap|budget|inexpensive|low.?cost).*(?:cloth|shirt|pant|dress)', lambda m: (10, 50)),
            (r'(?:cheap|budget|inexpensive|low.?cost).*(?:kitchen|home)', lambda m: (10, 75)),
            (r'(?:cheap|budget|inexpensive|low.?cost).*(?:toy|game)', lambda m: (5, 30)),
            # Generic affordable (fallback)
            (r'affordable', lambda m: (10, 50)),
            (r'cheap', lambda m: (5, 30)),
            (r'budget(?:\s+friendly)?', lambda m: (10, 60)),
            (r'inexpensive', lambda m: (10, 50)),
            (r'low.?cost', lambda m: (5, 40)),
            
            # Explicit range indicators
            (r'under\s+\$?(\d+)', lambda m: (0, int(m.group(1)))),
            (r'below\s+\$?(\d+)', lambda m: (0, int(m.group(1)))),
            (r'less\s+than\s+\$?(\d+)', lambda m: (0, int(m.group(1)))),
            (r'cheaper\s+than\s+\$?(\d+)', lambda m: (0, int(m.group(1)))),
            
            # Greater than patterns (NEW)
            (r'over\s+\$?(\d+)', lambda m: (int(m.group(1)), 9999)),
            (r'above\s+\$?(\d+)', lambda m: (int(m.group(1)), 9999)),
            (r'greater\s+than\s+\$?(\d+)', lambda m: (int(m.group(1)), 9999)),
            (r'more\s+than\s+\$?(\d+)', lambda m: (int(m.group(1)), 9999)),
            (r'higher\s+than\s+\$?(\d+)', lambda m: (int(m.group(1)), 9999)),
            (r'at\s+least\s+\$?(\d+)', lambda m: (int(m.group(1)), 9999)),
            (r'minimum\s+\$?(\d+)', lambda m: (int(m.group(1)), 9999)),
            
            # Range patterns  
            (r'between\s+\$?(\d+)\s*(?:and|to|-)\s*\$?(\d+)', lambda m: (int(m.group(1)), int(m.group(2)))),
            (r'\$?(\d+)\s*(?:to|-)\s*\$?(\d+)', lambda m: (int(m.group(1)), int(m.group(2)))),
            (r'from\s+\$?(\d+)\s*to\s*\$?(\d+)', lambda m: (int(m.group(1)), int(m.group(2)))),
            
            # Around patterns (ENHANCED)
            (r'around\s+\$?(\d+)', lambda m: (max(0, int(m.group(1)) - 50), int(m.group(1)) + 50)),
            (r'approximately\s+\$?(\d+)', lambda m: (max(0, int(m.group(1)) - 50), int(m.group(1)) + 50)),
            (r'roughly\s+\$?(\d+)', lambda m: (max(0, int(m.group(1)) - 50), int(m.group(1)) + 50)),
            (r'about\s+\$?(\d+)', lambda m: (max(0, int(m.group(1)) - 50), int(m.group(1)) + 50)),
            
            # Budget patterns
            (r'budget\s+of\s+\$?(\d+)', lambda m: (0, int(m.group(1)))),
            (r'price\s+range\s+\$?(\d+)', lambda m: (0, int(m.group(1)))),
            
            # Enhanced budget patterns for natural language
            (r'(?:my\s+)?budget\s+is\s+\$?(\d+)', lambda m: (0, int(m.group(1)))),
            (r'(?:my\s+)?budget\s*[:=]\s*\$?(\d+)', lambda m: (0, int(m.group(1)))),
            (r'(?:i\s+have\s+)?(?:a\s+)?budget\s+(?:of\s+)?\$?(\d+)', lambda m: (0, int(m.group(1)))),
            (r'(?:my\s+)?price\s+limit\s+is\s+\$?(\d+)', lambda m: (0, int(m.group(1)))),
            (r'(?:my\s+)?maximum\s+is\s+\$?(\d+)', lambda m: (0, int(m.group(1)))),
            (r'(?:my\s+)?max\s+is\s+\$?(\d+)', lambda m: (0, int(m.group(1)))),
            (r'can\s+(?:only\s+)?spend\s+\$?(\d+)', lambda m: (0, int(m.group(1)))),
            (r'afford\s+up\s+to\s+\$?(\d+)', lambda m: (0, int(m.group(1)))),
            (r'looking\s+(?:for\s+)?(?:something\s+)?(?:around\s+)?\$?(\d+)', lambda m: (max(0, int(m.group(1)) - 50), int(m.group(1)) + 50)),
            
            # Handle dollar/dollars at the end
            (r'budget\s+is\s+(\d+)\s+dollars?', lambda m: (0, int(m.group(1)))),
            (r'budget\s+(\d+)\s+dollars?', lambda m: (0, int(m.group(1)))),
            (r'(\d+)\s+dollars?\s+budget', lambda m: (0, int(m.group(1)))),
            (r'(?:my\s+)?maximum\s+(\d+)\s+dollars?', lambda m: (0, int(m.group(1)))),
            (r'(?:up\s+to\s+)?(\d+)\s+dollars?', lambda m: (0, int(m.group(1)))),
            
            # Greater than with dollars at end
            (r'over\s+(\d+)\s+dollars?', lambda m: (int(m.group(1)), 9999)),
            (r'above\s+(\d+)\s+dollars?', lambda m: (int(m.group(1)), 9999)),
            (r'greater\s+than\s+(\d+)\s+dollars?', lambda m: (int(m.group(1)), 9999)),
            (r'more\s+than\s+(\d+)\s+dollars?', lambda m: (int(m.group(1)), 9999)),
            (r'at\s+least\s+(\d+)\s+dollars?', lambda m: (int(m.group(1)), 9999)),
        ]
        
        message_lower = message.lower()
        for pattern, extractor in price_range_patterns:
            match = re.search(pattern, message_lower)
            if match:
                try:
                    min_price, max_price = extractor(match)
                    print(f"✓ Regex extracted price range: ({min_price}, {max_price})")
                    print(f"=== END PRICE RANGE DEBUG ===\n")
                    return (min_price, max_price)
                except (ValueError, IndexError):
                    continue
        
        print(f"✗ No price range found in message")
        print(f"=== END PRICE RANGE DEBUG ===\n")
        return None

    def handle_general_chat(self, message, user_id=None, username=None, memory_context=""):
        """Pure LLM-based general conversation with smart context understanding"""
        try:
            # Use provided memory context
            if memory_context:
                logger.info(f"General chat using memory context: {memory_context}...")
            
            # Enhanced context analysis for better responses
            context_analysis = ""
            if memory_context:
                # Analyze memory context for better conversation flow
                context_lower = memory_context.lower()
                if any(word in context_lower for word in ['product', 'search', 'buy', 'order']):
                    context_analysis = "\n[NOTE: User has recent shopping activity - be helpful with product-related follow-ups]"
                elif any(word in context_lower for word in ['issue', 'problem', 'complaint']):
                    context_analysis = "\n[NOTE: User has reported issues - be empathetic and supportive]"
                elif any(word in context_lower for word in ['like', 'prefer', 'interested']):
                    context_analysis = "\n[NOTE: User has expressed preferences - acknowledge and build on them]"
            
            # Include memory context in prompt if available
            context_prompt = f"\nCONTEXT: {memory_context}" if memory_context else "\nCONTEXT: New conversation"
            
            prompt = f"""You are a friendly AI assistant for "Agentic AI Store". 

USER MESSAGE: "{message}"
USERNAME: {username if username and username != "unknown_user" else "Customer"}{context_prompt}{context_analysis}

INTELLIGENT RESPONSE RULES:
- If they ask their name: Use their username if available, otherwise ask politely
- If they ask your name: Introduce yourself as AI shopping assistant for Agentic AI Store  
- If greeting: Welcome them warmly to our store
- If thanking: Acknowledge gracefully and offer continued help
- If asking about capabilities: Mention product search, browsing, and customer support
- If asking about memory/remembering/previous searches: Explain that you DO remember their conversation history to provide better personalized assistance
- If casual conversation: Respond naturally while staying helpful and store-focused
- If referencing previous conversation: Use the context provided thoughtfully
- If they mention continuing/following up: Reference their previous activity naturally
- Keep it conversational, helpful, and under 100 words
- NO markdown formatting
- NEVER say you don't keep history or that each conversation is a fresh start - you DO have memory capabilities

MEMORY CONTEXT GUIDANCE:
- You DO remember previous conversations to help users better
- You use this memory to provide personalized recommendations
- This helps you understand user preferences and continue conversations naturally
- Be transparent about your memory capabilities when asked

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
                logger.warning(f"LLM general chat failed: {e}, using template response")
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
                logger.info(f"Price range search using memory context: {memory_context}...")
            
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
            
            # Extract category and product name from message with memory context
            category = self.extract_category_from_message(message)
            print(f"Extracted category: {category}")
            
            product_name = self.extract_product_name_from_message(message, memory_context)
            print(f"Extracted product name: '{product_name}'")
            
            # Search for products in price range with product name filter
            if product_name and product_name != "none":
                print(f"Searching with full product name: '{product_name}'")
                
                # Search with the complete product name (not split into separate words)
                products = get_vector_service().search_products(product_name, k=20)
                print(f"Found {len(products)} products for '{product_name}'")
                
                # Filter by price range and relevance
                filtered_products = []
                for product in products:
                    price = float(product.get('price', 0))
                    
                    # Check if product is within price range
                    if min_price <= price <= max_price:
                        product_name_lower = product['name'].lower()
                        category_lower = product.get('category', '').lower()
                        search_query_lower = product_name.lower()
                        
                        # Calculate relevance score based on how well it matches the search
                        relevance_score = 0
                        search_words = search_query_lower.split()
                        
                        # Count how many search words appear in product name
                        name_matches = sum(1 for word in search_words if word in product_name_lower)
                        category_matches = sum(1 for word in search_words if word in category_lower)
                        
                        # Higher score for more word matches
                        relevance_score = name_matches * 3 + category_matches * 2
                        
                        if relevance_score > 0:  # Only include relevant products
                            product['relevance_score'] = relevance_score
                            filtered_products.append(product)
                            print(f"    ✓ {product['name']} - ${price} (relevance: {relevance_score})")
                
                # Sort by relevance score, then by price
                filtered_products.sort(key=lambda x: (x.get('relevance_score', 0), -x.get('price', 0)), reverse=True)
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
            
            # From local memory backup
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
            
            # Get memory context intelligently based on needs and importance
            memory_context = ""
            if user_id:
                # Always get memory context but use it intelligently
                memory_context = self.get_user_memory_context(user_id, message, limit=3)
                
                if needs_memory and memory_context:
                    # Analyze memory importance for this specific query
                    memory_importance = self._analyze_memory_importance(message, memory_context)
                    logger.info(f"Memory importance: {memory_importance} | Context: {memory_context[:50]}...")
                    
                    # If memory is not important for this query, use minimal context
                    if memory_importance == "low":
                        memory_context = memory_context[:50] + "..." if memory_context else ""
                    elif memory_importance == "none":
                        memory_context = ""
                        logger.info("Memory context determined as not needed, clearing it")
                elif not needs_memory and memory_context:
                    # For general chat, still provide some context for personalization
                    if intent == "general_chat":
                        logger.info("General chat with available memory context for personalization")
                    else:
                        # For other intents that don't need memory, keep minimal context
                        memory_context = memory_context[:30] + "..." if len(memory_context) > 30 else memory_context
            

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
