from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.contrib.auth import get_user_model
from .issue_models import Issue
from .issue_serializers import IssueSerializer
import os
import pandas as pd
import re
from sentence_transformers import SentenceTransformer
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from groq import Groq
import pickle
import json
from django.conf import settings
from django.core.cache import cache
from mem0 import MemoryClient

# Load products.csv and create FAISS vector store (load once)
products_csv_path = os.path.join(settings.BASE_DIR, 'products_list.csv')

# Check if CSV file exists
if not os.path.exists(products_csv_path):
    raise FileNotFoundError(f"Products CSV file not found at {products_csv_path}")

products_df = pd.read_csv(products_csv_path)
print(f"Loaded {len(products_df)} products from CSV")

# Create enhanced product texts with IDs for better matching
product_texts = []
product_id_mapping = {}
for _, row in products_df.iterrows():
    product_text = f"Product ID: {row['product_id']}. Product: {row['product_name']}. Description: {row['description']}. Price: ${row['price']}. Category: {row['category']}"
    product_texts.append(product_text)
    product_id_mapping[row['product_id']] = {
        'name': row['product_name'],
        'price': row['price'],
        'category': row['category'],
        'description': row['description']
    }

FAISS_INDEX_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'products_faiss.index')

# Load or create FAISS vectorstore
embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

# Initialize vectorstore as None first
vectorstore = None

def initialize_vectorstore():
    global vectorstore
    if vectorstore is None:
        print("Initializing vector store...")
        try:
            # Check if vector store exists and is valid
            if os.path.exists(FAISS_INDEX_PATH):
                try:
                    print("Loading existing vector store...")
                    vectorstore = FAISS.load_local(FAISS_INDEX_PATH, embeddings, allow_dangerous_deserialization=True)
                    print("Vector store loaded successfully!")
                    return
                except Exception as load_error:
                    print(f"Failed to load existing vector store: {load_error}")
                    print("Recreating vector store...")
            
            # Create new vector store
            print(f"Creating new vector store with {len(product_texts)} products...")
            vectorstore = FAISS.from_texts(product_texts, embeddings)
            
            # Save vector store
            print("Saving vector store...")
            vectorstore.save_local(FAISS_INDEX_PATH)
            print("Vector store created and saved successfully!")
            
        except Exception as e:
            print(f"Error in vector store creation: {e}")
            # If everything fails, recreate from scratch
            try:
                import shutil
                if os.path.exists(FAISS_INDEX_PATH):
                    shutil.rmtree(FAISS_INDEX_PATH)
                print("Creating vector store from scratch...")
                vectorstore = FAISS.from_texts(product_texts, embeddings)
                vectorstore.save_local(FAISS_INDEX_PATH)
                print("Vector store recreated successfully!")
            except Exception as final_error:
                print(f"Final error in vector store creation: {final_error}")
                raise final_error

# Set up Groq client
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY environment variable not set")
    
client = Groq(api_key=GROQ_API_KEY)

# Initialize Mem0 client for enhanced memory
MEM0_API_KEY = os.getenv('MEM0_API_KEY', 'm0-vP8D8VyS48o1BrrG48AQUqE6dai6O0MN07T5zrVw')
memory_client = MemoryClient(api_key=MEM0_API_KEY)

User = get_user_model()

# Chatbot memory functions
def get_chat_history_key(user_id):
    """Generate cache key for user's chat history"""
    return f"chatbot_history_{user_id}"

def get_chat_history(user_id):
    """Get user's chat history from cache"""
    key = get_chat_history_key(user_id)
    history = cache.get(key, [])
    return history

def save_chat_history(user_id, messages):
    """Save user's chat history to cache (1 week expiry for better memory)"""
    key = get_chat_history_key(user_id)
    # Keep only last 150 messages to store extended conversation context (increased from 100)
    if len(messages) > 150:
        messages = messages[-150:]
    cache.set(key, messages, timeout=604800)  # 1 week (7 days * 24 hours * 60 minutes * 60 seconds)

def add_to_chat_history(user_id, role, content):
    """Add a message to user's chat history"""
    history = get_chat_history(user_id)
    history.append({"role": role, "content": content})
    save_chat_history(user_id, history)

def clear_chat_history(user_id):
    """Clear user's chat history"""
    key = get_chat_history_key(user_id)
    cache.delete(key)

# Enhanced Memory Functions with Mem0
def add_to_memory(user_id, messages):
    """Add conversation to Mem0 for long-term memory"""
    try:
        memory_client.add(messages, user_id=str(user_id))
        print(f"Added {len(messages)} messages to Mem0 for user {user_id}")
    except Exception as e:
        print(f"Mem0 add error: {e}")

def search_memory(user_id, query):
    """Search user's memory for relevant context"""
    try:
        results = memory_client.search(query, user_id=str(user_id))
        return results
    except Exception as e:
        print(f"Mem0 search error: {e}")
        return None

def get_user_memory_context(user_id, current_query):
    """Get relevant memory context for current query"""
    try:
        memory_results = search_memory(user_id, current_query)
        if memory_results and len(memory_results) > 0:
            context_text = "Relevant Past Context:\n"
            for i, result in enumerate(memory_results[:3], 1):
                context_text += f"{i}. {result.get('memory', result.get('content', 'No content'))}\n"
            return context_text
        return "No relevant past context found."
    except Exception as e:
        print(f"Memory context error: {e}")
        return "Memory context unavailable."

# Enhanced Product ID Detection and Direct Lookup
def extract_explicit_product_id(message):
    """Extract explicit product ID mentions from user message"""
    if not message:
        return None
    
    message_lower = message.lower().strip()
    
    # Patterns for explicit product ID mentions
    explicit_patterns = [
        r'\bid\s*[:\-]?\s*(\d+)\b',                    # "id 2", "id: 2", "id-2"
        r'\bproduct\s*id\s*[:\-]?\s*(\d+)\b',          # "product id 2", "product id: 2"  
        r'\bproduct\s+(\d+)\b',                        # "product 2"
        r'\bitem\s*[:\-]?\s*(\d+)\b',                  # "item 2", "item: 2"
        r'\b#\s*(\d+)\b',                              # "#2"
        r'\bnumber\s*[:\-]?\s*(\d+)\b',               # "number 2", "number: 2"
    ]
    
    for pattern in explicit_patterns:
        matches = re.findall(pattern, message_lower, re.IGNORECASE)
        if matches:
            try:
                product_id = int(matches[0])
                # Validate it exists in our product mapping
                if product_id in product_id_mapping:
                    return product_id
            except (ValueError, IndexError):
                continue
    
    return None

def get_direct_product_info(product_id):
    """Get direct product information from product_id_mapping"""
    if product_id and product_id in product_id_mapping:
        product_info = product_id_mapping[product_id]
        product_link = f"http://localhost:3000/products/{product_id}"
        
        response_text = f"Product Found:\n\n" \
                       f"Name: {product_info['name']}\n" \
                       f"ID: {product_id}\n" \
                       f"Price: ${product_info['price']}\n" \
                       f"Category: {product_info['category']}\n" \
                       f"Description: {product_info['description']}\n\n" \
                       f"View full details: {product_link}"
        return response_text
    return None

# Removed extract_product_id_from_query() function
# All product queries now use pure embedding-based vector search

def analyze_query_intent(message, chat_history):
    """
    Analyze user query to determine intent (pure embedding-based flow):
    - 'issue': User is reporting an issue
    - 'product_reference': User is asking about a previously mentioned product
    - 'new_product_search': User is searching for new products (all product queries use embedding search)
    """
    message_lower = message.lower().strip()
    
    # Check for issue reporting first (highest priority)
    issue_indicators = [
        'issue', 'problem', 'bug', 'error', 'complaint', 'not working', 
        'broken', 'fail', 'wrong', 'help', 'support', 'trouble', 'report',
        'complain', 'fix', 'solve', 'sorry', 'apologize', 'fault', 'defect',
        'damaged', 'disappointed', 'refund', 'return', 'exchange'
    ]
    
    # Strong issue patterns
    issue_patterns = [
        'i have a problem', 'there is an issue', 'not working properly',
        'can you help', 'need help', 'facing', 'experiencing', 'having trouble'
    ]
    
    has_issue_keyword = any(indicator in message_lower for indicator in issue_indicators)
    has_issue_pattern = any(pattern in message_lower for pattern in issue_patterns)
    
    if has_issue_keyword or has_issue_pattern:
        return 'issue'
    
    # Enhanced context detection for product references
    reference_indicators = [
        'what is', 'tell me', 'show me', 'describe', 'details', 'info',
        'name', 'price', 'cost', 'category', 'description', 'features',
        'specs', 'specification', 'about', 'more about', 'explain',
        'how much', 'where can', 'can i buy', 'available'
    ]
    
    # Context words that suggest referring to previous conversation
    context_words = [
        'that', 'this', 'it', 'its', 'the one', 'same', 'previous',
        'earlier', 'mentioned', 'above', 'before', 'last one',
        'the product', 'that product', 'this product'
    ]
    
    # Pronouns and references that almost always indicate context
    strong_context_indicators = [
        'that id', 'this id', 'its price', 'its name', 'that one',
        'the last one', 'what about it', 'tell me more', 'more info'
    ]
    
    has_reference = any(ref in message_lower for ref in reference_indicators)
    has_context = any(ctx in message_lower for ctx in context_words)
    has_strong_context = any(indicator in message_lower for indicator in strong_context_indicators)
    
    # Check if there's recent product discussion in chat history (extended search)
    has_recent_product = False
    if chat_history and len(chat_history) >= 2:
        # Look at last 12 messages for product mentions (increased from 10)
        recent_messages = chat_history[-12:] if len(chat_history) > 12 else chat_history
        for msg in reversed(recent_messages):
            if msg.get('role') == 'assistant':
                content = msg.get('content', '').lower()
                if any(keyword in content for keyword in ['product id:', 'name:', 'price:', 'category:']):
                    has_recent_product = True
                    break
    
    # Strong context indicators almost always mean reference
    if has_strong_context and has_recent_product:
        return 'product_reference'
    
    # If user has recent product discussion and uses reference language
    if has_recent_product and (has_context or (has_reference and len(message.split()) <= 6)):
        return 'product_reference'
    
    # Very short queries with context words likely refer to previous discussion
    if len(message.split()) <= 3 and has_context and chat_history:
        return 'product_reference'
    
    # Default to new product search - ALL product queries use embedding-based search
    return 'new_product_search'

def get_contextual_product_id(chat_history, message):
    """Extract product ID from context when user makes a reference query (enhanced context search)"""
    if not chat_history:
        return None
        
    # Look for the most recent product mention in chat history
    # Check last 15 messages for comprehensive context (increased from 12)
    recent_messages = chat_history[-15:] if len(chat_history) > 15 else chat_history
    
    for msg in reversed(recent_messages):
        if msg.get('role') == 'assistant':
            content = msg.get('content', '')
            # Look for product ID patterns (in order of specificity)
            id_patterns = [
                r'Product ID:\s*(\d+)',
                r'ID:\s*(\d+)', 
                r'http://localhost:3000/products/(\d+)',
                r'Product\s+ID\s*:\s*(\d+)',
                r'product\s+(\d+)',
                r'Product\s+(\d+)',
                r'\bID\s+(\d+)',
                r'product_id[:\s]+(\d+)'
            ]
            
            for pattern in id_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                if matches:
                    # Return the last (most recent) product ID found
                    try:
                        return int(matches[-1])
                    except (ValueError, IndexError):
                        continue
    
    # If no specific product ID found, look for explicit product ID mentions
    # in user's own messages (in case they mentioned a product earlier)
    for msg in reversed(recent_messages):
        if msg.get('role') == 'user':
            content = msg.get('content', '')
            # Only check for explicit product ID patterns, not random numbers
            explicit_patterns = [
                r'\bproduct\s+id\s*[:\-]?\s*(\d+)\b',
                r'\bid\s*[:\-]\s*(\d+)\b',
                r'\bproduct\s+number\s*[:\-]?\s*(\d+)\b',
            ]
            for pattern in explicit_patterns:
                match = re.search(pattern, content.lower(), re.IGNORECASE)
                if match:
                    try:
                        return int(match.group(1))
                    except (ValueError, IndexError):
                        continue
    
    return None

def is_issue_query(query):
    """Determine if the query is about reporting an issue - more flexible detection"""
    issue_keywords = [
        'issue', 'problem', 'bug', 'error', 'complaint', 'not working', 
        'broken', 'fail', 'wrong', 'help', 'support', 'trouble', 'report',
        'complain', 'fix', 'solve', 'sorry', 'apologize', 'fault'
    ]
    query_lower = query.lower()
    
    # Check for issue patterns
    issue_patterns = [
        'i have',
        'there is',
        'can you help',
        'need help',
        'facing',
        'experiencing',
        "isn't functioning",
        'not working properly',
    ]
    
    # Check keywords and patterns
    has_issue_keyword = any(keyword in query_lower for keyword in issue_keywords)
    has_issue_pattern = any(pattern in query_lower for pattern in issue_patterns)
    
    return has_issue_keyword or has_issue_pattern

# Query Understanding and Context Analysis System
def preprocess_and_understand_query(message, chat_history, vectorstore):
    """
    Advanced query preprocessing inspired by RAG pattern:
    1. Analyze query context and intent
    2. Extract relevant information from chat history
    3. Retrieve contextual product information
    4. Prepare structured context for LLM
    """
    
    # Step 1: Basic query analysis
    intent_analysis = {
        'intent': analyze_query_intent(message, chat_history),
        'has_product_reference': False,
        'contextual_product_id': None,
        'query_type': 'unknown',
        'confidence': 0.0
    }
    
    # Step 2: Context extraction from chat history
    context_info = extract_conversation_context(chat_history)
    
    # Step 3: Enhanced intent classification
    if intent_analysis['intent'] == 'product_reference':
        intent_analysis['contextual_product_id'] = get_contextual_product_id(chat_history, message)
        intent_analysis['has_product_reference'] = intent_analysis['contextual_product_id'] is not None
        intent_analysis['confidence'] = 0.9 if intent_analysis['has_product_reference'] else 0.3
    
    # Step 4: Enhanced vector similarity search for ALL product queries
    vector_context = None
    if intent_analysis['intent'] in ['new_product_search', 'product_reference']:
        # Check if user is asking for specific product ID
        potential_id = extract_explicit_product_id(message)
        
        if potential_id:
            # For specific product ID queries, search for exact ID match first
            id_specific_query = f"Product ID: {potential_id}"
            docs_and_scores = vectorstore.similarity_search_with_score(id_specific_query, k=10)
        else:
            # For general queries, use original message
            docs_and_scores = vectorstore.similarity_search_with_score(message, k=10)
        
        if docs_and_scores:
            # Use a more lenient threshold for better recall
            relevant_docs = [
                {'content': doc.page_content, 'score': score} 
                for doc, score in docs_and_scores if score < 1.2  # Increased threshold
            ]
            
            # If searching for specific ID and no good matches, try broader search
            if potential_id and len(relevant_docs) == 0:
                broader_query = f"Product {potential_id} ID {potential_id}"
                docs_and_scores = vectorstore.similarity_search_with_score(broader_query, k=10)
                relevant_docs = [
                    {'content': doc.page_content, 'score': score} 
                    for doc, score in docs_and_scores if score < 1.5
                ]
            
            vector_context = {
                'relevant_products': relevant_docs,
                'search_quality': 'high' if len(relevant_docs) >= 3 else 'medium' if relevant_docs else 'low',
                'total_found': len(relevant_docs),
                'searched_for_id': potential_id
            }
    
    # Step 5: Prepare structured understanding result
    understanding = {
        'intent': intent_analysis,
        'conversation_context': context_info,
        'vector_context': vector_context,
        'processed_query': message.strip(),
        'requires_llm': intent_analysis['intent'] == 'new_product_search' or 
                       (intent_analysis['intent'] == 'product_reference' and not intent_analysis['has_product_reference'])
    }
    
    return understanding

def extract_conversation_context(chat_history):
    """Extract key context information from conversation history (enhanced memory version)"""
    if not chat_history or len(chat_history) < 2:
        return {'has_context': False, 'recent_products': [], 'conversation_flow': 'new'}
    
    recent_products = []
    conversation_topics = []
    
    # Analyze last 20 messages for comprehensive context (increased from 12)
    recent_messages = chat_history[-20:] if len(chat_history) > 20 else chat_history
    
    for msg in recent_messages:
        if msg.get('role') == 'assistant':
            content = msg.get('content', '')
            # Extract product IDs mentioned
            product_ids = re.findall(r'Product ID:\s*(\d+)', content, re.IGNORECASE)
            for pid in product_ids:
                try:
                    recent_products.append(int(pid))
                except ValueError:
                    continue
            
            # Also extract from URLs
            url_ids = re.findall(r'http://localhost:3000/products/(\d+)', content)
            for uid in url_ids:
                try:
                    recent_products.append(int(uid))
                except ValueError:
                    continue
            
            # Identify conversation topics
            content_lower = content.lower()
            if 'price' in content_lower or 'cost' in content_lower:
                conversation_topics.append('pricing')
            if 'category' in content_lower:
                conversation_topics.append('category')
            if 'description' in content_lower or 'detail' in content_lower:
                conversation_topics.append('details')
            if 'feature' in content_lower or 'specification' in content_lower:
                conversation_topics.append('features')
    
    return {
        'has_context': len(recent_products) > 0,
        'recent_products': list(set(recent_products))[-8:],  # Last 8 unique products (increased from 5)
        'conversation_topics': list(set(conversation_topics)),
        'conversation_flow': 'contextual' if recent_products else 'exploratory'
    }

def prepare_contextual_llm_prompt(understanding, message, user_id=None):
    """Prepare an enhanced prompt based on query understanding (embedding-focused with Mem0 memory)"""
    
    # Get memory context if user_id provided
    memory_context = ""
    if user_id:
        memory_context = get_user_memory_context(user_id, message)
    
    base_prompt = """You are an intelligent e-commerce assistant with advanced context understanding.

QUERY ANALYSIS:
- Intent: {intent}
- Context Available: {has_context}
- Confidence: {confidence}

CONVERSATION CONTEXT:
{conversation_context}

LONG-TERM MEMORY CONTEXT:
{memory_context}

CRITICAL INSTRUCTIONS FOR ENHANCED PRODUCT SEARCH:
1. FIRST CHECK: If user mentions specific product ID (like "id 2", "product 2"), look for exact match in vector results
2. ALWAYS use ONLY the vector search results provided below for product recommendations
3. Extract product IDs ONLY from the "Product ID: X" format in vector search results
4. NEVER guess or create product IDs from user's numbers (like "5 items" ≠ product ID 5)
5. If user asks about specific product ID but it's not in vector results, say "I couldn't find that specific product in my search results"
6. For contextual queries ("that product", "this item"), refer to conversation history
7. ALWAYS include clickable links: http://localhost:3000/products/[PRODUCT_ID_HERE]
8. Be conversational and maintain context across multiple turns
9. Use plain text formatting (no markdown)
10. If no relevant products found, suggest more specific search terms
11. Remember up to 20 previous conversation messages for context
12. Focus on semantic similarity rather than exact keyword matching
13. Present multiple relevant options when available
14. If vector search has low quality, acknowledge limitations and suggest refinement

CURRENT USER QUERY: {message}

VECTOR SEARCH RESULTS:
{vector_context}

Please provide a helpful response based on the vector search results, conversation context, and memory context. Do not make up product information."""

    # Format the prompt with understanding data
    formatted_prompt = base_prompt.format(
        intent=understanding['intent']['intent'],
        has_context=understanding['conversation_context']['has_context'],
        confidence=understanding['intent']['confidence'],
        conversation_context=format_conversation_context(understanding['conversation_context']),
        memory_context=memory_context,
        message=message,
        vector_context=format_vector_context(understanding['vector_context']) if understanding['vector_context'] else "No specific product matches found for this query. Please ask the user to be more specific about what they're looking for."
    )
    
    return formatted_prompt

def format_conversation_context(context_info):
    """Format conversation context for LLM prompt"""
    if not context_info['has_context']:
        return "No previous product discussion in this conversation."
    
    context_text = f"Conversation Flow: {context_info['conversation_flow']}\n"
    if context_info['recent_products']:
        context_text += f"Recently Discussed Products: {', '.join(map(str, context_info['recent_products']))}\n"
    if context_info['conversation_topics']:
        context_text += f"Topics Covered: {', '.join(context_info['conversation_topics'])}\n"
    
    return context_text

def format_vector_context(vector_context):
    """Format vector search results for LLM prompt (robust product_id extraction with ID search info)"""
    if not vector_context or not vector_context['relevant_products']:
        searched_id = vector_context.get('searched_for_id') if vector_context else None
        if searched_id:
            return f"No products found for Product ID: {searched_id}. The specific product ID {searched_id} was not found in our database."
        return "No relevant products found in the database."
    
    total_found = vector_context.get('total_found', len(vector_context['relevant_products']))
    search_quality = vector_context.get('search_quality', 'medium')
    searched_id = vector_context.get('searched_for_id')
    
    context_text = f"Search Quality: {search_quality} | Total Found: {total_found}"
    if searched_id:
        context_text += f" | Searched for Product ID: {searched_id}"
    context_text += "\n\n"
    
    context_text += "Relevant Products from Vector Search:\n"
    
    import re
    # Show top 5 products (increased from 3)
    for i, product in enumerate(vector_context['relevant_products'][:5], 1):
        content = product['content']
        similarity_score = 1 - product['score'] if product['score'] <= 1 else 0.1
        # Try to extract product_id from content
        match = re.search(r"Product ID[:\s]*([0-9]+)", content)
        product_id = match.group(1) if match else "N/A"
        
        # Highlight if this matches the searched ID
        id_match_indicator = " ⭐ EXACT MATCH" if searched_id and product_id == str(searched_id) else ""
        
        # Add product link if product_id found
        if product_id != "N/A":
            link = f"http://localhost:3000/products/{product_id}"
            context_text += f"{i}. {content}{id_match_indicator}\n   Product Link: {link}\n   Relevance Score: {similarity_score:.3f}\n\n"
        else:
            context_text += f"{i}. {content}{id_match_indicator}\n   Product Link: Not available\n   Relevance Score: {similarity_score:.3f}\n\n"
    
    if total_found > 5:
        context_text += f"... and {total_found - 5} more products available.\n"
    
    return context_text

# Enhanced processing function
def process_query_with_understanding(message, chat_history, vectorstore, client, user_id):
    """
    Process user query with comprehensive understanding (RAG-like approach):
    1. Check for explicit product ID mentions first
    2. Understand query context and intent
    3. Handle direct responses for clear intents
    4. Use LLM with enhanced context for complex queries
    """
    
    # Step 1: Check for explicit product ID mentions FIRST
    explicit_product_id = extract_explicit_product_id(message)
    if explicit_product_id:
        direct_response = get_direct_product_info(explicit_product_id)
        if direct_response:
            return {'response': direct_response, 'direct_response': True}
    
    # Step 2: Understand the query comprehensively
    understanding = preprocess_and_understand_query(message, chat_history, vectorstore)
    
    # Step 3: Handle direct responses for clear intents
    intent = understanding['intent']['intent']
    
    # Direct issue handling
    if intent == 'issue':
        # For issues, only check for explicit product ID mentions in context
        product_id = explicit_product_id
        if not product_id and chat_history:
            contextual_id = get_contextual_product_id(chat_history, message)
            if contextual_id:
                product_id = contextual_id
        
        return {
            'response': 'Your issue has been reported to the admin. They will review it shortly. Thank you for your feedback!',
            'direct_response': True,
            'product_id': product_id,
            'is_issue': True
        }
    
    # Step 4: ALL OTHER PRODUCT QUERIES use enhanced embedding-based LLM processing with direct lookup fallback
    if intent in ['new_product_search', 'product_reference'] or understanding['requires_llm']:
        try:
            # Prepare enhanced prompt with vector search results and memory context
            enhanced_prompt = prepare_contextual_llm_prompt(understanding, message, user_id)
            
            # Build chat messages with extended conversation history
            chat_messages = [{"role": "system", "content": enhanced_prompt}]
            
            # Add significantly more chat history for better memory (last 20 messages)
            recent_history = chat_history[-20:] if len(chat_history) > 20 else chat_history
            for msg in recent_history[:-1]:  # Exclude current message
                chat_messages.append(msg)
            
            # Add current query
            chat_messages.append({"role": "user", "content": message})
            
            # Call LLM with enhanced context and vector search results
            chat_completion = client.chat.completions.create(
                messages=chat_messages,
                model="llama-3.3-70b-versatile",
                temperature=0.2,  # Lower temperature for more consistent responses
                max_tokens=5000
            )
            
            response_text = chat_completion.choices[0].message.content
            
            # Add conversation to Mem0 for long-term memory
            conversation_messages = [
                {"role": "user", "content": message},
                {"role": "assistant", "content": response_text}
            ]
            add_to_memory(user_id, conversation_messages)
            
            return {'response': response_text, 'direct_response': False}
            
        except Exception as e:
            print(f"LLM processing error: {str(e)}")
            import traceback
            traceback.print_exc()  # Print full traceback for debugging
            
            # If LLM fails but we have an explicit product ID, try direct lookup
            if explicit_product_id:
                direct_response = get_direct_product_info(explicit_product_id)
                if direct_response:
                    return {'response': direct_response, 'direct_response': True}
            
            return {
                'response': 'I apologize, but I encountered an error while processing your request. Please try again.',
                'direct_response': True,
                'error': True
            }
    
    # Fallback response
    return {
        'response': 'I couldn\'t understand your query clearly. Could you please rephrase it?',
        'direct_response': True
    }

class ChatbotView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        # Initialize vectorstore if not already done
        initialize_vectorstore()
        
        message = request.data.get('message', '')
        clear_history = request.data.get('clear_history', False)
        
        # Clear history if requested
        if clear_history:
            clear_chat_history(request.user.id)
            return Response({'response': 'Chat history cleared!'})
        
        if not message.strip():
            return Response({'response': 'Please enter a message.'})
        
        try:
            user_id = request.user.id
            
            # Add user message to history
            add_to_chat_history(user_id, "user", message)
            
            # Get chat history for context analysis
            chat_history = get_chat_history(user_id)
            
            # Use enhanced query understanding system
            result = process_query_with_understanding(message, chat_history, vectorstore, client, user_id)
            
            # Handle issue reporting - ensure it goes to admin and saves to DB (extended keyword matching)
            issue_keywords = [
                'issue', 'problem', 'bug', 'error', 'complaint', 'not working', 
                'broken', 'fail', 'wrong', 'help', 'support', 'trouble', 'report',
                'complain', 'fix', 'solve', 'sorry', 'apologize', 'fault', 'defect',
                'damaged', 'disappointed', 'refund', 'return', 'exchange', 'warranty',
                'malfunction', 'defective', 'concern', 'unsatisfied', 'unhappy'
            ]
            
            if result.get('is_issue', False) or (result.get('direct_response') and any(keyword in message.lower() for keyword in issue_keywords)):
                product_id = result.get('product_id', None)  # Default to None if not found
                try:
                    # Create issue in database
                    issue = Issue.objects.create(
                        user=request.user, 
                        issue=message, 
                        product_id=product_id  # This can be None, which is fine
                    )
                    print(f"Issue created successfully: ID {issue.id}, User: {request.user.username}, Product ID: {product_id}")
                except Exception as issue_error:
                    print(f"Error creating issue: {issue_error}")
            
            response_text = result['response']
            
            # Add assistant response to history
            add_to_chat_history(user_id, "assistant", response_text)
            
            return Response({'response': response_text})
            
        except Exception as e:
            print(f"Chatbot error: {str(e)}")
            import traceback
            traceback.print_exc()
            
            # Handle different types of errors gracefully
            if 'product_id' in str(e):
                error_response = 'I encountered an issue while processing product information. Please try rephrasing your query.'
            elif 'vector' in str(e).lower():
                error_response = 'I encountered an issue with product search. Please try again with different keywords.'
            else:
                error_response = 'I apologize, but I encountered an error while processing your request. Please try again.'
            
            # Still add error response to history for context
            try:
                add_to_chat_history(request.user.id, "assistant", error_response)
            except:
                pass  # If history fails too, just continue
                
            return Response({
                'response': error_response
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def get(self, request):
        """Get user's chat history"""
        try:
            user_id = request.user.id
            history = get_chat_history(user_id)
            return Response({'history': history})
        except Exception as e:
            return Response({
                'error': 'Failed to fetch chat history'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class AdminIssuesView(APIView):
    permission_classes = [permissions.IsAdminUser]
    
    def get(self, request):
        try:
            issues = Issue.objects.select_related('user').order_by('-created_at')
            serializer = IssueSerializer(issues, many=True)
            return Response({'issues': serializer.data})
        except Exception as e:
            return Response({
                'error': 'Failed to fetch issues'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class ProductsView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """Get all products from CSV"""
        try:
            products_list = []
            for _, row in products_df.iterrows():
                products_list.append({
                    'id': row['product_id'],
                    'name': row['product_name'],
                    'description': row['description'],
                    'price': row['price'],
                    'category': row['category']
                })
            return Response({'products': products_list})
        except Exception as e:
            return Response({
                'error': 'Failed to fetch products'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class ProductDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, product_id):
        """Get specific product by ID"""
        try:
            product_id = int(product_id)
            if product_id in product_id_mapping:
                product_info = product_id_mapping[product_id]
                product_data = {
                    'id': product_id,
                    'name': product_info['name'],
                    'description': product_info['description'],
                    'price': product_info['price'],
                    'category': product_info['category']
                }
                return Response({'product': product_data})
            else:
                return Response({
                    'error': 'Product not found'
                }, status=status.HTTP_404_NOT_FOUND)
        except (ValueError, TypeError):
            return Response({
                'error': 'Invalid product ID'
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                'error': 'Failed to fetch product'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
