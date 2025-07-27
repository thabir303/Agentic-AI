import React, { useState, useEffect } from 'react';
import { MessageCircle, X, Send, Plus, Trash2, Brain } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { chatbotAPI } from '../utils/api';

// Function to render plain text with clickable URLs
const renderMessageWithLinks = (text, navigate) => {
  console.log('renderMessageWithLinks called with text:', text.substring(0, 100) + '...');
  
  // Handle direct URLs (http://localhost:5173/products/:id)
  const urlRegex = /(https?:\/\/localhost:5173\/products\/(\d+))/g;
  
  const parts = [];
  let lastIndex = 0;
  let match;
  let linkCount = 0;
  
  // Process direct URLs
  while ((match = urlRegex.exec(text)) !== null) {
    linkCount++;
    console.log(`Found link ${linkCount}:`, match[1], 'Product ID:', match[2]);
    
    // Add text before the URL (but skip the URL itself)
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }
    
    const fullUrl = match[1];
    const productId = match[2];
    
    // Add the clickable URL as a link (replace the URL text)
    parts.push(
      <a
        key={`link-${match.index}`}
        href={fullUrl}
        className="text-blue-600 hover:text-blue-800 underline cursor-pointer font-medium inline-block my-1"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          console.log('🚀 Link clicked! Navigating to product:', productId);
          console.log('📍 Current URL:', window.location.href);
          console.log('🎯 Target URL:', `/products/${productId}`);
          
          try {
            console.log('🧭 Using React Router navigate...');
            navigate(`/products/${productId}`);
            console.log('✅ Navigation successful');
          } catch (error) {
            console.error('❌ Navigation error:', error);
            console.log('🔄 Falling back to window.location...');
            window.location.href = `/products/${productId}`;
          }
        }}
        onMouseOver={() => console.log(`🖱️ Hovering over product ${productId} link`)}
      >
        {fullUrl}
      </a>
    );
    
    lastIndex = match.index + match[0].length;
  }
  
  // Add remaining text
  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }
  
  console.log(`✅ Created ${linkCount} clickable links, total parts: ${parts.length}`);
  return parts.length > 0 ? parts : text;
};

const Chatbot = () => {
  const navigate = useNavigate();
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState([
    {
      id: 1,
      text: "Hello! I'm your AI assistant. How can I help you with our products today?",
      isBot: true,
      timestamp: new Date(),
      isTyping: false
    }
  ]);
  const [inputMessage, setInputMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [typingMessage, setTypingMessage] = useState(null);

  const clearMemory = async () => {
    try {
      await chatbotAPI.clearMemory();
      // Clear local chat as well
      clearChat();
      // Add a system message to indicate memory was cleared
      setMessages([
        {
          id: 1,
          text: "Hello! I'm your AI assistant. My memory has been cleared and we're starting fresh. How can I help you with our products today?",
          isBot: true,
          timestamp: new Date(),
          isTyping: false
        }
      ]);
    } catch (error) {
      console.error('Failed to clear memory:', error);
      // Still clear local chat even if API fails
      clearChat();
    }
  };

  const clearChat = () => {
    // Clear any ongoing typing
    if (typingMessage) {
      clearInterval(typingMessage.intervalId);
      setTypingMessage(null);
    }
    
    setMessages([
      {
        id: 1,
        text: "Hello! I'm your AI assistant. How can I help you with our products today?",
        isBot: true,
        timestamp: new Date(),
        isTyping: false
      }
    ]);
  };

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (typingMessage) {
        clearInterval(typingMessage.intervalId);
      }
    };
  }, [typingMessage]);

  const newChat = () => {
    clearChat();
    setIsOpen(true);
  };

  const typeMessage = (fullText, messageId) => {
    let currentText = '';
    let currentIndex = 0;

    const typeInterval = setInterval(() => {
      if (currentIndex < fullText.length) {
        currentText += fullText[currentIndex];
        
        setMessages(prev => prev.map(msg => 
          msg.id === messageId 
            ? { ...msg, text: currentText, isTyping: true }
            : msg
        ));
        
        currentIndex++;
      } else {
        // Typing complete
        setMessages(prev => prev.map(msg => 
          msg.id === messageId 
            ? { ...msg, text: fullText, isTyping: false }
            : msg
        ));
        setTypingMessage(null);
        clearInterval(typeInterval);
      }
    }, 15); // Faster typing speed (was 3ms, now 15ms for better visibility)

    setTypingMessage({ intervalId: typeInterval, messageId });
  };

  const sendMessage = async () => {
    if (!inputMessage.trim() || loading || typingMessage) return;

    const userMessage = {
      id: Date.now(),
      text: inputMessage,
      isBot: false,
      timestamp: new Date(),
      isTyping: false
    };

    setMessages(prev => [...prev, userMessage]);
    const currentInput = inputMessage;
    setInputMessage('');
    setLoading(true);

    // Add placeholder bot message that will be typed
    const botMessageId = Date.now() + 1;
    const placeholderBotMessage = {
      id: botMessageId,
      text: '',
      isBot: true,
      timestamp: new Date(),
      isTyping: true
    };

    setMessages(prev => [...prev, placeholderBotMessage]);

    try {
      const response = await chatbotAPI.sendMessage(currentInput);

      // Start typing effect
      typeMessage(response.data.response, botMessageId);

    } catch (error) {
      const errorText = "Sorry, I'm having trouble connecting. Please try again later.";
      
      // Type the error message
      typeMessage(errorText, botMessageId);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <>
      {/* New Chat Button (only when chatbot is closed) */}
      {!isOpen && (
        <button
          onClick={newChat}
          className="fixed bottom-24 right-6 w-12 h-12 bg-green-600 hover:bg-green-700 text-white rounded-full shadow-lg transition-all duration-300 flex items-center justify-center z-50"
          title="New Chat"
        >
          <Plus size={20} />
        </button>
      )}

      {/* Chat Toggle Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={`fixed bottom-6 right-6 w-14 h-14 bg-blue-600 hover:bg-blue-700 text-white rounded-full shadow-lg transition-all duration-300 flex items-center justify-center z-50 ${
          isOpen ? 'bg-red-600 hover:bg-red-700' : ''
        }`}
      >
        {isOpen ? <X size={24} /> : <MessageCircle size={24} />}
      </button>

      {/* Chat Window */}
      {isOpen && (
        <div className="fixed bottom-24 right-6 w-96 h-[600px] bg-white rounded-lg shadow-2xl border z-50 flex flex-col">
          {/* Header */}
          <div className="bg-blue-600 text-white p-4 rounded-t-lg flex justify-between items-center">
            <div>
              <h3 className="font-semibold">AI Assistant</h3>
              <p className="text-blue-100 text-sm">Ask me about our products!</p>
            </div>
            <div className="flex space-x-2">
              <button
                onClick={clearMemory}
                className="bg-purple-500 hover:bg-purple-400 p-2 rounded-lg transition-colors"
                title="Clear Memory & Chat"
              >
                <Brain size={18} />
              </button>
              <button
                onClick={clearChat}
                className="bg-blue-500 hover:bg-blue-400 p-2 rounded-lg transition-colors"
                title="Clear Chat Only"
              >
                <Trash2 size={18} />
              </button>
            </div>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3 max-h-[480px]">
            {messages.map((message) => (
              <div
                key={message.id}
                className={`flex ${message.isBot ? 'justify-start' : 'justify-end'}`}
              >
                <div
                  className={`max-w-[280px] p-3 rounded-lg ${
                    message.isBot
                      ? 'bg-gray-100 text-gray-800'
                      : 'bg-blue-600 text-white'
                  }`}
                >
                  <div className="text-sm whitespace-pre-wrap">
                    {message.isBot ? (
                      <span>
                        {renderMessageWithLinks(message.text, navigate)}
                        {message.isTyping && (
                          <span className="animate-pulse">▋</span>
                        )}
                      </span>
                    ) : (
                      message.text
                    )}
                  </div>
                  <p className={`text-xs mt-1 ${
                    message.isBot ? 'text-gray-500' : 'text-blue-100'
                  }`}>
                    {message.timestamp.toLocaleTimeString()}
                  </p>
                </div>
              </div>
            ))}
          </div>

          {/* Input */}
          <div className="p-4 border-t">
            <div className="flex space-x-2">
              <textarea
                value={inputMessage}
                onChange={(e) => setInputMessage(e.target.value)}
                onKeyPress={handleKeyPress}
                placeholder="Ask about products or report an issue..."
                className="flex-1 p-2 border rounded-lg resize-none h-10 focus:outline-none focus:ring-2 focus:ring-blue-500"
                rows="1"
                disabled={loading || typingMessage}
              />
              <button
                onClick={sendMessage}
                disabled={!inputMessage.trim() || loading || typingMessage}
                className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 text-white p-2 rounded-lg transition-colors"
              >
                <Send size={18} />
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default Chatbot;
