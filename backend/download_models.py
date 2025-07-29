#!/usr/bin/env python3
"""
Pre-download Marqo embedding model to avoid runtime delays
"""

import os
import sys
from pathlib import Path

def download_marqo_model():
    """Download Marqo e-commerce embedding model"""
    print("🔄 Pre-downloading Marqo e-commerce embedding model...")
    print("This is a 2.61GB model, please be patient...")
    
    try:
        # Import required libraries
        from sentence_transformers import SentenceTransformer
        
        # Download the model
        model_name = "Marqo/marqo-ecommerce-embeddings-L"
        print(f"Downloading model: {model_name}")
        
        # This will download and cache the model
        model = SentenceTransformer(model_name)
        print("✅ Model downloaded successfully!")
        
        # Test the model with a simple embedding
        test_text = "stainless steel kitchen bowl"
        embedding = model.encode(test_text)
        print(f"✅ Model test successful! Embedding dimension: {len(embedding)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error downloading model: {e}")
        return False

def download_all_models():
    """Download all required models"""
    print("🚀 Downloading all required embedding models...")
    
    models_to_download = [
        "Marqo/marqo-ecommerce-embeddings-L",
     # Fallback model
    ]
    
    for model_name in models_to_download:
        try:
            print(f"\n📥 Downloading: {model_name}")
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer(model_name)
            print(f"✅ {model_name} downloaded successfully!")
        except Exception as e:
            print(f"❌ Failed to download {model_name}: {e}")

if __name__ == "__main__":
    print("=" * 60)
    print("🤖 Agentic AI - Model Download Script")
    print("=" * 60)
    
    # Check if sentence-transformers is installed
    try:
        import sentence_transformers
        print(f"✅ sentence-transformers version: {sentence_transformers.__version__}")
    except ImportError:
        print("❌ sentence-transformers not installed. Run: pip install sentence-transformers")
        sys.exit(1)
    
    # Download models
    success = download_marqo_model()
    
    if success:
        print("\n🎉 All models downloaded successfully!")
        print("You can now run the Django server without model download delays.")
    else:
        print("\n⚠️  Some models failed to download. Check your internet connection.")
        print("The application will fallback to automatic download when needed.")
    
    print("=" * 60)
