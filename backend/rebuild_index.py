#!/usr/bin/env python
"""
Rebuild vector index with new embedding model
"""
import os
import sys
import django
from pathlib import Path

# Add the project directory to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from authentication.vector_service import VectorDBService

def rebuild_index():
    print("🔄 Rebuilding vector index with mixedbread-ai/mxbai-embed-large-v1...")
    
    # Delete old index files
    vector_service = VectorDBService()
    
    if os.path.exists(vector_service.index_path):
        os.remove(vector_service.index_path)
        print(f"✅ Removed old index: {vector_service.index_path}")
    
    if os.path.exists(vector_service.metadata_path):
        os.remove(vector_service.metadata_path)
        print(f"✅ Removed old metadata: {vector_service.metadata_path}")
    
    # Force recreation of index
    vector_service.index = None
    vector_service.products_data = []
    
    print("🚀 Creating new index with mixedbread-ai model...")
    vector_service.load_or_create_index()
    
    print("✅ Index rebuilt successfully!")
    
    # Test the new index
    print("\n🧪 Testing new index...")
    results = vector_service.search_products("phone", k=5)
    
    print(f"Search results for 'phone':")
    for i, product in enumerate(results[:3], 1):
        print(f"  {i}. {product['name']} - ${product['price']} ({product['category']})")
    
    print("\n🎉 Vector index rebuild complete!")

if __name__ == "__main__":
    rebuild_index()
