import os
import json
import re
import logging
from datetime import datetime
from groq import Groq
import google.generativeai as genai
from huggingface_hub import InferenceClient
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
        
        # Initialize Hugging Face InferenceClient with Groq provider (Primary choice)
        hf_token = os.getenv('HF_TOKEN')
        if hf_token and not self.use_local_fallback:
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
                logger.warning("Falling back to Groq client")
                self.hf_client = None
                self.llm_client = None
        else:
            logger.warning("No HF_TOKEN found or local fallback enabled")
            self.hf_client = None
            self.llm_client = None
        
        # Initialize Groq client as secondary fallback
        groq_api_key = os.getenv('GROQ_API_KEY')
        if groq_api_key and not self.use_local_fallback:
            try:
                self.groq_client = Groq(api_key=groq_api_key)
                logger.info("Groq client initialized successfully as backup")
                # If no primary LLM is set, use Groq
                if not self.llm_client:
                    self.llm_client = 'groq'
            except Exception as e:
                logger.error(f"Failed to initialize Groq client: {e}")
                self.groq_client = None
        else:
            logger.warning("No Groq API key found or local fallback enabled")
            self.groq_client = None
        
        # Initialize Gemini client as tertiary fallback
        gemini_api_key = os.getenv('GEMINI_API_KEY')
        if gemini_api_key and not self.use_local_fallback:
            try:
                genai.configure(api_key=gemini_api_key)
                # Use faster flash model to avoid rate limits
                self.gemini_model = genai.GenerativeModel('gemini-2.5-pro')
                logger.info("Gemini 2.5 Pro client initialized successfully as tertiary backup")
                # If no primary LLM is set, use Gemini
                if not self.llm_client:
                    self.llm_client = 'gemini'
            except Exception as e:
                logger.error(f"Failed to initialize Gemini client: {e}")
                self.gemini_model = None
        else:
            logger.warning("No Gemini API key found or local fallback enabled")
            self.gemini_model = None
        
        # Set final LLM client if not set yet
        if not self.llm_client:
            logger.warning("No LLM client available, using local fallback")
        
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
        """Generate response using available LLM (HuggingFace primary, Groq/Gemini fallback)"""
        try:
            if self.llm_client == 'huggingface' and self.hf_client:
                # Use Hugging Face InferenceClient with openai/gpt-oss-120b
                response = self.hf_client.chat_completion(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                
                result = response.choices[0].message.content.strip()
                
                # Debug empty responses from HuggingFace
                if not result:
                    print(f"⚠️ HuggingFace returned empty response, trying Groq fallback")
                    logger.warning("HuggingFace returned empty response, falling back to Groq")
                    raise Exception("Empty HuggingFace response")
                
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
                
            elif self.llm_client == 'gemini' and self.gemini_model:
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
            
            else:
                logger.error("No LLM client available")
                return "I'm sorry, I'm currently unavailable. Please try again later."
                
        except Exception as e:
            logger.error(f"Error generating LLM response: {e}")
            # Try fallback chain: HF -> Groq -> Gemini
            if self.llm_client == 'huggingface' and self.groq_client:
                try:
                    logger.info("Falling back to Groq after HuggingFace failure")
                    response = self.groq_client.chat.completions.create(
                        messages=messages,
                        model="llama-3.3-70b-versatile",
                        temperature=temperature,
                        max_tokens=max_tokens
                    )
                    return response.choices[0].message.content.strip()
                except Exception as groq_error:
                    logger.error(f"Groq fallback also failed: {groq_error}")
                    if self.gemini_model:
                        try:
                            logger.info("Falling back to Gemini after Groq failure")
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
                            response = self.gemini_model.generate_content(prompt)
                            return response.text.strip() if response.text else "I'm sorry, I'm having trouble processing your request."
                        except Exception as gemini_error:
                            logger.error(f"All LLM clients failed: {gemini_error}")
            
            elif self.llm_client == 'groq' and self.gemini_model:
                try:
                    logger.info("Falling back to Gemini after Groq failure")
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
                    response = self.gemini_model.generate_content(prompt)
                    return response.text.strip() if response.text else "I'm sorry, I'm having trouble processing your request."
                except Exception as gemini_error:
                    logger.error(f"Gemini fallback also failed: {gemini_error}")
                    
            return "I'm sorry, I'm currently experiencing technical difficulties. Please try again later."

    def get_user_memory_context(self, user_id, current_message, limit=5):
        """Enhanced memory retrieval prioritizing recent chronological context over keyword search"""
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
                
                # PRIORITY 2: Fallback to keyword search if recent memories failed
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
                # Fallback to local memory (chronological order)
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
        print(f"User context: '{user_context[:100]}...' " if user_context else "No user context")
        
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
    
    def handle_memory_query(self, message, user_id=None, username=None, memory_context=""):
        """Handle specific questions about memory and conversation history"""
        message_lower = message.lower()
        
        # Get user's actual memory to show
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
        print(f"Memory context: '{memory_context[:200]}...' " if memory_context else "No memory context")
        
        if not self.llm_client:
            print("No LLM client available, returning None")
            print(f"=== END PRODUCT NAME DEBUG ===\n")
            return None
        
        # Enhanced prompt that considers memory context for connected conversations
        context_info = f"\nPREVIOUS CONTEXT: {memory_context}" if memory_context else ""
        
        prompt = f"""Extract the specific product name from this message. Consider conversation context for better understanding.

MESSAGE: "{message}"{context_info}

INTELLIGENT EXTRACTION RULES:
- If current message mentions price/budget and context shows product preferences, extract from context
- For "budget is $X" with previous product mentions, return the products from context
- Extract main product types: laptop, books, led tv, headphones, etc.
- For gift scenarios: use recipient preferences from context if available
- Return "none" only if no product type can be determined from message OR context
- Prioritize context-based products for budget/price-only messages

EXAMPLES:
- Message: "budget is $30" + Context: "likes books and jewelry" → Return: "books jewelry"
- Message: "I want laptop" → Return: "laptop"
- Message: "something nice" + No context → Return: "none"

RESPOND WITH ONLY THE PRODUCT NAME(S):"""
        
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
        """Extract price range from user message using LLM primarily with regex fallback"""
        print(f"\n=== PRICE RANGE EXTRACTION DEBUG ===")
        print(f"Input message: '{message}'")
        
        # PRIORITY 1: Use LLM for intelligent price range extraction
        if self.llm_client:
            try:
                prompt = f"""Extract the price range from the user's message. Return exact numbers only.

MESSAGE: "{message}"

RULES:
- For "under/below $X": return min_price: 0, max_price: X
- For "around $X": return min_price: (X-50), max_price: (X+50)  
- For "over/greater than $X": return min_price: X, max_price: 9999
- For "between $X and $Y": return min_price: X, max_price: Y
- For "budget is $X": return min_price: 0, max_price: X
- Use NUMBERS ONLY (no "infinity" or text)

RESPONSE FORMAT (exact format required):
min_price: [number]
max_price: [number]

If no price found: none"""

                response_text = self.generate_llm_response(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,  # Very low temperature for consistent extraction
                    max_tokens=100    # Short response needed
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
                        print(f"✗ LLM response missing min_price or max_price, falling back to regex")
                else:
                    print(f"✗ LLM returned 'none' or empty, falling back to regex")
                    
            except Exception as e:
                print(f"✗ LLM price extraction failed: {e}, falling back to regex")
        else:
            print("No LLM client available, using regex approach")
        
        # PRIORITY 2: Fallback to enhanced regex patterns
        print("Using regex fallback for price extraction...")
        return self._extract_price_range_regex(message)
    
    def _extract_price_range_regex(self, message):
        """Fallback regex-based price range extraction with enhanced patterns"""
        import re
        
        price_range_patterns = [
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

    def filter_relevant_products(self, products, query, max_products=3):
        """Simple product filtering"""
        return products[:max_products] if products else []

    def handle_product_search(self, message, user_id=None, username=None, memory_context=""):
        """Smart product search with enhanced LLM prompting and memory-aware product filtering"""
        try:
            # Use provided memory context
            if memory_context:
                logger.info(f"Product search using memory context: {memory_context[:50]}...")
            
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
            
            # Regular product search with memory context enhanced query
            search_query = message
            if memory_context and "likes" in memory_context.lower():
                # Extract product preferences from memory for better search
                import re
                likes_match = re.search(r'likes\s+([^|]+)', memory_context.lower())
                if likes_match:
                    preferences = likes_match.group(1).strip()
                    search_query += f" {preferences}"
                    logger.info(f"Enhanced search query with preferences: {search_query}")
            
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
        """Smart category browsing with enhanced LLM and memory-aware suggestions"""
        try:
            # Use provided memory context
            if memory_context:
                logger.info(f"Category browse using memory context: {memory_context[:50]}...")
            
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
        """Handle issue reporting with memory-aware context understanding"""
        try:
            # Use provided memory context
            if memory_context:
                logger.info(f"Issue report using memory context: {memory_context[:50]}...")
            
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
    
    def handle_general_chat(self, message, user_id=None, username=None, memory_context=""):
        """Pure LLM-based general conversation with smart context understanding"""
        try:
            # Use provided memory context
            if memory_context:
                logger.info(f"General chat using memory context: {memory_context[:50]}...")
            
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
            
            # Extract category and product name from message with memory context
            category = self.extract_category_from_message(message)
            print(f"Extracted category: {category}")
            
            product_name = self.extract_product_name_from_message(message, memory_context)
            print(f"Extracted product name: '{product_name}'")
            
            # Search for products in price range with product name filter
            if product_name and product_name != "none":
                print(f"Searching with product name: '{product_name}'")
                
                # Handle multiple product types (like "books jewelry")
                product_types = product_name.lower().split()
                all_filtered_products = []
                
                for product_type in product_types:
                    if len(product_type) > 2:  # Skip very short words
                        print(f"  Searching for product type: '{product_type}'")
                        # Search by each product type
                        products = get_vector_service().search_products(product_type, k=20)
                        print(f"  Found {len(products)} products for '{product_type}'")
                        
                        # Filter by relevance and price range
                        for product in products:
                            price = float(product.get('price', 0))
                            product_name_lower = product['name'].lower()
                            category_lower = product.get('category', '').lower()
                            
                            # Check relevance - product name or category should contain keywords
                            relevance_score = 0
                            if product_type in product_name_lower:
                                relevance_score += 3  # Highest score for name match
                            elif product_type in category_lower:
                                relevance_score += 2  # Medium score for category match
                            elif any(keyword in product_name_lower for keyword in [product_type[:4]]):  # Partial match
                                relevance_score += 1
                            
                            # Only include if relevant AND within price range AND not already added
                            if (relevance_score > 0 and min_price <= price <= max_price and 
                                not any(p['id'] == product['id'] for p in all_filtered_products)):
                                product['relevance_score'] = relevance_score
                                product['matched_type'] = product_type
                                all_filtered_products.append(product)
                                print(f"    ✓ {product['name']} - ${price} (relevance: {relevance_score}, type: {product_type})")
                
                # Sort by relevance score and price
                all_filtered_products.sort(key=lambda x: (x.get('relevance_score', 0), -x.get('price', 0)), reverse=True)
                products = all_filtered_products[:10]  # Limit to 10 results
                print(f"Final filtered products across all types: {len(products)}")
                
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
            
            # Check for memory-specific queries first
            if self.detect_memory_query(message):
                logger.info("Memory query detected - using dedicated handler")
                return self.handle_memory_query(message, user_id, username, memory_context)
            
            # Route to handlers with intelligent memory context
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
