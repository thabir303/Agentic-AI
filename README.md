# 🤖 Agentic AI E-commerce Chatbot

A complete AI-powered e-commerce chatbot system with Django REST Framework backend and React frontend.

## 🌟 Features

### ✨ Core Functionality
- **Pure Embedding-Based Search**: AI-powered product recommendations using advanced vector similarity search
- **Semantic Understanding**: No pattern matching - understands context and meaning of queries
- **Smart Context Memory**: Maintains conversation context across 20+ message history
- **Long-Term Memory (Mem0 Integration)**: Remembers previous user conversations and context using Mem0 memory service
- **Issue Reporting**: Customers can report platform issues directly through the chatbot
- **Admin Dashboard**: View and manage customer issues
- **Role-based Authentication**: Customer and Admin roles with different access levels

### 🔧 Technical Features
- **Vector Database**: FAISS for efficient product similarity search
- **AI Integration**: Groq LLM for intelligent conversation handling
- **LangChain Integration**: Used for building the semantic search pipeline and connecting LLMs with vector databases
- **Mem0 Memory Service**: Persistent, semantic memory for user conversations and context
- **Persistent Storage**: Vector embeddings saved locally for faster responses
- **JWT Authentication**: Secure token-based authentication
- **Responsive Design**: Modern UI with Tailwind CSS

## 🏗️ Project Structure

```
Agentic-AI/
├── backend/                     # Django REST API
│   ├── authentication/          # Auth, chatbot, models, views
│   ├── products_list.csv        # Product database
│   ├── products_faiss.index/    # Vector DB (FAISS)
│   ├── manage.py
│   └── ...                      # Django files
├── frontend/                    # React + Vite app
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── contexts/
│   │   ├── App.jsx
│   │   ├── main.jsx
│   │   └── index.css
│   ├── public/
│   ├── vite.config.js
│   ├── tailwind.config.js
│   └── package.json
├── .env                         # Environment variables (includes GROQ_API_KEY and MEM0_API_KEY)
└── README.md
```

## 🚀 Quick Start

### Prerequisites
- Python 3.8+
- Node.js 14+
- npm or yarn
- Groq API key (get from https://console.groq.com/)
- Mem0 API key (get from https://mem0.ai/)

### Installation & Setup

1. **Clone and Navigate**
   ```bash
   git clone https://github.com/thabir303/Agentic-AI.git
   cd Agentic-AI
   ```

2. **Environment Setup**
   Add your Groq and Mem0 API keys to `.env`:
   ```
   GROQ_API_KEY=your_actual_groq_api_key_here
   MEM0_API_KEY=your_actual_mem0_api_key_here
   ADMIN_EMAIL=admin@admin.com
   ADMIN_PASSWORD=admin123
   ```

3. **Backend Setup**
   ```bash
   cd backend
   pip install -r requirements.txt
   python manage.py migrate
   ```

4. **Frontend Setup**
   ```bash
   cd ../frontend
   npm install
   ```

5. **Start Development Servers**
   
   Terminal 1 (Backend):
   ```bash
   cd backend
   python manage.py runserver 8000
   ```
   
   Terminal 2 (Frontend):
   ```bash
   cd frontend
   npm run dev
   ```

6. **Access the Application**
   - Frontend: http://localhost:5173
   - Backend API: http://localhost:8000

## 👥 User Accounts

### Demo Credentials

**Admin Access:**
- Email: `admin@admin.com`
- Password: `admin123`
- Features: View customer issues, access admin dashboard

**Customer Access:**
- Create new account via signup form
- Features: Product search, issue reporting

## 🛍️ Using the Chatbot

### How Mem0 Memory Works
- The chatbot uses Mem0 to store and retrieve long-term user conversation context.
- This enables the assistant to remember previous queries, preferences, and issues across sessions.
- Mem0 enhances semantic understanding and personalized responses.

### Product Search Examples
```
Show me smartphones
I need electronics under $500
What accessories do you have?
Items for gaming
Wireless devices
Books about cooking
Fitness equipment
Home gadgets
```

**Note:** The chatbot uses pure embedding-based search. Numbers in queries like "I need 5 laptops" won't be treated as product IDs.

### Issue Reporting Examples
```
I have an issue with my order
The website is not working properly
Problem with product 10
I need help with checkout
```

## 🔧 API Endpoints

### Authentication
- `POST /auth/signup/` - Customer registration
- `POST /auth/signin/` - User login (customer/admin)

### Chatbot
- `POST /auth/chatbot/` - Chat with AI assistant (requires authentication)

### Admin
- `GET /auth/admin/issues/` - View customer issues (admin only)

### Memory Service
- Mem0 is used internally by the backend for storing and searching user conversation memory.
- No direct public API, but all chatbot interactions benefit from Mem0-powered context.

## 📊 Data Flow

1. **Product Search (Pure Embedding + Mem0 Memory)**:
   - User query → Vector embedding → FAISS similarity search → Mem0 context retrieval → LLM processing → Response with product links

2. **Issue Reporting**:
   - User issue → Context analysis → Database storage → Mem0 memory update → Admin notification

3. **Authentication**:
   - Login → JWT token → Stored in localStorage → API authentication

## 🎨 Frontend Components

- **AuthPage**: Login/signup forms with role-based routing
- **HomePage**: Customer dashboard with product search
- **IssuesPage**: Admin dashboard for issue management
- **Chatbot**: Floating chat interface with AI responses

## 🔒 Security Features

- JWT-based authentication
- Role-based access control
- CORS protection
- Input validation and sanitization
- Secure password handling

## 🐛 Troubleshooting

### Common Issues

1. **FAISS Index Error**
   ```bash
   rm -rf backend/products_faiss.index
   # Restart backend server
   ```

2. **Missing Dependencies**
   ```bash
   cd backend && pip install -r requirements.txt
   cd frontend && npm install
   ```

3. **API Connection Issues**
   - Ensure proxy is configured in frontend/vite.config.js
   - Check that both servers are running
   - Verify CORS settings in Django

4. **Groq API Issues**
   - Verify API key in .env file
   - Check Groq service status
   - Ensure sufficient API credits

5. **Mem0 API Issues**
  - Ensure MEM0_API_KEY is set in `.env`
  - Check Mem0 service status at https://mem0.ai/
  - Review backend logs for memory errors

## 📈 Performance Optimization

- Vector database cached locally (no rebuild needed)
- JWT tokens for stateless authentication
- Efficient similarity search with FAISS
- Lazy loading of vector embeddings
- Optimized React components

## 🛠️ Development

### Adding New Products
1. Update `backend/products_list.csv`
2. Delete `backend/products_faiss.index/`
3. Restart backend (will rebuild vector database)

### Customizing AI Responses
- Modify system prompts in `authentication/chatbot_service.py`
- Adjust similarity search parameters
- Update product text formatting

### Customizing Memory Features
- Mem0 integration is handled in `authentication/chatbot_service.py`
- You can adjust how memory is stored and retrieved for more personalized or context-aware responses

### Frontend Customization
- Modify styles in `frontend/src/index.css`
- Update components in `frontend/src/pages/`
- Configure routing and authentication logic

## 📝 API Response Examples

**Product Search Response:**
```json
{
  "response": "Here are some great smartphones:\n\nAbility Basic 77 (ID: 1)\nPrice: $875.24\nCategory: Smartphones\nDescription: Fly mission more others...\n\nView Product: http://localhost:5173/products/1"
}
```

**Issue Reporting Response:**
```json
{
  "response": "Your issue has been reported to the admin. They will review it shortly. Thank you for your feedback!"
}
```

## 🌐 Production Deployment

1. **Environment Variables**
   - Set production GROQ_API_KEY and MEM0_API_KEY
   - Configure production database
   - Update ALLOWED_HOSTS in Django settings

2. **Build Frontend**
   ```bash
   cd frontend && npm run build
   ```

3. **Static Files**
   ```bash
   cd backend && python manage.py collectstatic
   ```

4. **Database**
   ```bash
   python manage.py migrate --settings=backend.settings_production
   ```

## 🔄 Updates & Maintenance

- **Vector Database**: Automatically rebuilds when products_list.csv changes
- **Dependencies**: Regular updates recommended for security
- **API Keys**: Monitor usage and rotate as needed
- **Database**: Regular backups recommended for production

---

**Happy Chatting! 🤖✨**

## 🧠 About LangChain

LangChain is used in Agentic AI to connect large language models (LLMs) with the FAISS vector database. It enables semantic product search, conversational retrieval, and context-aware responses by chaining together embeddings, retrieval, and LLMs in the backend.

