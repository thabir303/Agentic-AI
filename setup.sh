#!/bin/bash
"""
Setup script for Agentic AI project
This script will install dependencies and pre-download all required models
"""

set -e  # Exit on any error

echo "🚀 Setting up Agentic AI Project"
echo "=" * 60

# Check Python version
python3 --version || { echo "❌ Python 3 not found"; exit 1; }

# Create and activate virtual environment
if [ ! -d ".venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv .venv
fi

echo "🔄 Activating virtual environment..."
source .venv/bin/activate

# Install backend dependencies
echo "📥 Installing backend dependencies..."
cd backend
pip install -r requirements.txt

# Download models
echo "🤖 Pre-downloading embedding models..."
python3 download_models.py

# Install frontend dependencies
echo "📥 Installing frontend dependencies..."
cd ../frontend
npm install

echo "✅ Setup completed successfully!"
echo ""
echo "🚀 To start the project:"
echo "Backend: cd backend && source ../.venv/bin/activate && python manage.py runserver"
echo "Frontend: cd frontend && npm run dev"
