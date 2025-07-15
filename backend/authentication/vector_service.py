import os
import pandas as pd
import faiss
import numpy as np
import pickle
import json
from pathlib import Path
from django.conf import settings
from langchain_huggingface import HuggingFaceEmbeddings
import logging

logger = logging.getLogger(__name__)

class VectorDBService:
    def __init__(self):
        self.embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            model_kwargs={'device': 'cpu'},
            encode_kwargs={'normalize_embeddings': True}
        )
        self.index = None
        self.products_data = []
        self.index_path = os.path.join(settings.BASE_DIR, 'vector_index.faiss')
        self.metadata_path = os.path.join(settings.BASE_DIR, 'products_metadata.pkl')
        self.load_or_create_index()
    
    def load_csv_data(self, csv_path=None):
        """Load and process CSV data"""
        if csv_path is None:
            csv_path = os.path.join(settings.BASE_DIR, 'products_list.csv')
        
        try:
            df = pd.read_csv(csv_path)
            products = []
            
            for _, row in df.iterrows():
                # Create rich text for better embeddings
                text_content = f"""
                Product: {row['product_name']}
                Category: {row['category']} 
                Description: {row['description']}
                Price: ${row['price']}
                """.strip()
                
                product_data = {
                    'id': int(row['product_id']),
                    'name': row['product_name'],
                    'description': row['description'],
                    'price': float(row['price']),
                    'category': row['category'],
                    'text_content': text_content
                }
                products.append(product_data)
            
            logger.info(f"Loaded {len(products)} products from CSV")
            return products
            
        except Exception as e:
            logger.error(f"Error loading CSV data: {e}")
            return []
    
    def create_embeddings(self, products):
        """Create embeddings for products"""
        texts = [product['text_content'] for product in products]
        try:
            embeddings = self.embeddings.embed_documents(texts)
            logger.info(f"Created embeddings for {len(embeddings)} products")
            return np.array(embeddings).astype('float32')
        except Exception as e:
            logger.error(f"Error creating embeddings: {e}")
            return np.array([])
    
    def create_index(self, embeddings):
        """Create FAISS index"""
        if len(embeddings) == 0:
            return None
            
        dimension = embeddings.shape[1]
        # Use IndexIVFFlat for better performance with larger datasets
        quantizer = faiss.IndexFlatIP(dimension)  # Inner product for cosine similarity
        index = faiss.IndexIVFFlat(quantizer, dimension, min(100, len(embeddings)//10))
        
        # Train the index
        index.train(embeddings)
        index.add(embeddings)
        
        logger.info(f"Created FAISS index with {index.ntotal} vectors")
        return index
    
    def save_index(self):
        """Save index and metadata to disk"""
        try:
            if self.index:
                faiss.write_index(self.index, self.index_path)
            
            with open(self.metadata_path, 'wb') as f:
                pickle.dump(self.products_data, f)
                
            logger.info("Index and metadata saved successfully")
        except Exception as e:
            logger.error(f"Error saving index: {e}")
    
    def load_index(self):
        """Load index and metadata from disk"""
        try:
            if os.path.exists(self.index_path) and os.path.exists(self.metadata_path):
                self.index = faiss.read_index(self.index_path)
                
                with open(self.metadata_path, 'rb') as f:
                    self.products_data = pickle.load(f)
                
                logger.info(f"Loaded index with {len(self.products_data)} products")
                return True
        except Exception as e:
            logger.error(f"Error loading index: {e}")
        return False
    
    def load_or_create_index(self):
        """Load existing index or create new one"""
        if not self.load_index():
            logger.info("Creating new vector index...")
            self.rebuild_index()
    
    def rebuild_index(self, csv_path=None):
        """Rebuild the entire index from CSV"""
        products = self.load_csv_data(csv_path)
        if not products:
            logger.error("No products loaded, cannot create index")
            return False
        
        embeddings = self.create_embeddings(products)
        if len(embeddings) == 0:
            logger.error("No embeddings created, cannot create index")
            return False
        
        self.index = self.create_index(embeddings)
        self.products_data = products
        self.save_index()
        return True
    
    def search_products(self, query, k=5, category_filter=None):
        """Search for products based on query"""
        if not self.index or not self.products_data:
            return []
        
        try:
            # Create embedding for query
            query_embedding = self.embeddings.embed_query(query)
            query_vector = np.array([query_embedding]).astype('float32')
            
            # Search in FAISS
            scores, indices = self.index.search(query_vector, min(k*2, len(self.products_data)))
            
            results = []
            for score, idx in zip(scores[0], indices[0]):
                if idx < len(self.products_data):
                    product = self.products_data[idx].copy()
                    product['similarity_score'] = float(score)
                    
                    # Apply category filter if specified
                    if category_filter and product['category'].lower() != category_filter.lower():
                        continue
                    
                    results.append(product)
                    
                    if len(results) >= k:
                        break
            
            logger.info(f"Found {len(results)} products for query: {query}")
            return results
            
        except Exception as e:
            logger.error(f"Error searching products: {e}")
            return []
    
    def search_products_by_price_range(self, min_price=0, max_price=None, category_filter=None, k=10):
        """Search products by price range with optional category filter"""
        try:
            # Filter products by price range
            filtered_products = []
            
            for product in self.products_data:
                price = product['price']
                
                # Check price range
                if price < min_price:
                    continue
                if max_price is not None and price > max_price:
                    continue
                
                # Check category filter
                if category_filter and product['category'].lower() != category_filter.lower():
                    continue
                
                filtered_products.append(product)
            
            # Sort by price (ascending)
            filtered_products.sort(key=lambda x: x['price'])
            
            # Return top k products
            return filtered_products[:k]
            
        except Exception as e:
            logger.error(f"Error searching products by price range: {e}")
            return []
    
    def get_product_by_id(self, product_id):
        """Get specific product by ID"""
        for product in self.products_data:
            if product['id'] == product_id:
                return product
        return None
    
    def get_categories(self):
        """Get all unique categories"""
        categories = list(set(product['category'] for product in self.products_data))
        return sorted(categories)
    
    def get_products_by_category(self, category, limit=20):
        """Get products by category"""
        products = [p for p in self.products_data if p['category'].lower() == category.lower()]
        return products[:limit]
    
    def get_all_products(self, limit=None):
        """Get all products with optional limit"""
        if limit:
            return self.products_data[:limit]
        return self.products_data

# Global instance
vector_service = None

def get_vector_service():
    """Get or create the vector service instance"""
    global vector_service
    if vector_service is None:
        vector_service = VectorDBService()
    return vector_service
