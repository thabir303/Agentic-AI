import os
import pandas as pd
from fastapi import FastAPI, Request
from pydantic import BaseModel
from langchain.embeddings import OpenAIEmbeddings
from langchain.vectorstores import FAISS
from langchain.llms import ChatGroq
from langchain.chains import ConversationalRetrievalChain

# Load products_list.csv and create FAISS vector store
products_df = pd.read_csv('../products_list.csv')
product_texts = [
    f"Product: {row['product_name']}. Description: {row['description']}. Price: {row['price']}. Category: {row['category']}. Link: {row['link']}"
    for _, row in products_df.iterrows()
]

# Use GROQ API key from environment
GROQ_API_KEY = os.getenv('GROQ_API_KEY')

embeddings = OpenAIEmbeddings()
vectorstore = FAISS.from_texts(product_texts, embeddings)
llm = ChatGroq(api_key=GROQ_API_KEY)
qa_chain = ConversationalRetrievalChain.from_llm(llm, vectorstore.as_retriever())

app = FastAPI()

# In-memory issue store (replace with DB in production)
issues = []

class ChatRequest(BaseModel):
    user: str
    message: str

class Issue(BaseModel):
    user: str
    issue: str
    product_id: int = None

@app.post('/chatbot/')
async def chatbot_endpoint(req: ChatRequest):
    # Check for issue reporting intent (simple keyword match for demo)
    if 'issue' in req.message.lower() or 'problem' in req.message.lower():
        issues.append({'user': req.user, 'issue': req.message})
        return {'response': 'Your issue has been reported to the admin.'}
    # Otherwise, answer product queries
    result = qa_chain({'question': req.message, 'chat_history': []})
    return {'response': result['answer']}

@app.get('/admin/issues/')
async def get_issues():
    return {'issues': issues}
