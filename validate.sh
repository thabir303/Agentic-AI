#!/bin/bash

# Agentic AI Project Setup and Validation Script

echo "🤖 Agentic AI Project Validator"
echo "==============================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if we're in the right directory
if [ ! -f "package.json" ] || [ ! -d "backend" ] || [ ! -d "frontend" ]; then
    echo -e "${RED}❌ Please run this script from the Agentic-AI project root directory${NC}"
    exit 1
fi

echo "📁 Checking project structure..."
if [ -d "backend" ] && [ -d "frontend" ] && [ -f ".env" ]; then
    echo -e "${GREEN}✅ Project structure looks good${NC}"
else
    echo -e "${RED}❌ Missing required directories or .env file${NC}"
    exit 1
fi

echo ""
echo "🔑 Checking environment variables..."
if grep -q "GROQ_API_KEY" .env && grep -q "ADMIN_EMAIL" .env; then
    echo -e "${GREEN}✅ Environment file configured${NC}"
    
    if grep -q "your_groq_api_key_here" .env; then
        echo -e "${YELLOW}⚠️  Warning: Please update GROQ_API_KEY with your actual API key${NC}"
    fi
else
    echo -e "${RED}❌ Environment file missing required variables${NC}"
    exit 1
fi

echo ""
echo "🐍 Checking Python dependencies..."
cd backend
if python -c "import django, rest_framework, groq, sentence_transformers, langchain_community" 2>/dev/null; then
    echo -e "${GREEN}✅ Python dependencies installed${NC}"
else
    echo -e "${YELLOW}⚠️  Installing Python dependencies...${NC}"
    pip install -r requirements.txt
fi

echo ""
echo "📊 Checking database..."
if python manage.py check 2>/dev/null; then
    echo -e "${GREEN}✅ Django configuration valid${NC}"
else
    echo -e "${YELLOW}⚠️  Running migrations...${NC}"
    python manage.py migrate
fi

cd ..

echo ""
echo "📦 Checking Node.js dependencies..."
cd frontend
if [ -d "node_modules" ] && [ -f "package-lock.json" ]; then
    echo -e "${GREEN}✅ Node.js dependencies installed${NC}"
else
    echo -e "${YELLOW}⚠️  Installing Node.js dependencies...${NC}"
    npm install
fi

cd ..

echo ""
echo "🚀 Starting development servers..."
echo "Backend will run on: http://localhost:8000"
echo "Frontend will run on: http://localhost:3000"
echo ""
echo "To start servers manually:"
echo "Terminal 1: cd backend && python manage.py runserver 8000"
echo "Terminal 2: cd frontend && npm start"
echo ""
echo -e "${GREEN}✅ Project validation complete!${NC}"
echo ""
echo "🎯 Demo Credentials:"
echo "Admin: admin@admin.com / admin123"
echo "Customer: Create new account via signup"
echo ""
echo "💬 Chatbot Examples:"
echo "- 'Show me smartphones'"
echo "- 'Product 5'"  
echo "- 'I have an issue with my order'"
