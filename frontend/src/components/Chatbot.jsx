import React, { useState, useEffect, useRef } from 'react';
import { MessageCircle, X, Send, Plus, Trash2, Brain, Maximize2, Minimize2 } from 'lucide-react';
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
  const [showSuggestions, setShowSuggestions] = useState(true);
  const [isExpanded, setIsExpanded] = useState(false);
  const suggestions = [
    'Show me popular products',
    'Find budget headphones',
    'Browse laptop category',
    'What did I search before?',
  ];
  const scrollRef = useRef(null);
  const abortTypingRef = useRef(false);

  // Auto scroll to bottom when messages change
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
    }
  }, [messages]);

  // Hide suggestions after first user message
  useEffect(() => {
    const hasUser = messages.some(m => !m.isBot);
    if (hasUser) setShowSuggestions(false);
  }, [messages]);

  // Improved realistic typing function
  const typeMessage = (fullText, messageId) => {
    abortTypingRef.current = false;
    let currentText = '';
    let index = 0;

    const typeNext = () => {
      if (abortTypingRef.current) {
        // Finish instantly
        setMessages(prev => prev.map(msg => msg.id === messageId ? { ...msg, text: fullText, isTyping: false } : msg));
        setTypingMessage(null);
        return;
      }
      if (index < fullText.length) {
        currentText += fullText[index];
        index += 1;
        setMessages(prev => prev.map(msg => msg.id === messageId ? { ...msg, text: currentText, isTyping: true } : msg));
        // Variable delay: slower after punctuation, random jitter
        const char = fullText[index - 1];
        let base = 15 + Math.random() * 15; // 15-30ms
        if ('.!?'.includes(char)) base += 250 + Math.random() * 150; // pause after sentence
        else if (',;:' .includes(char)) base += 120 + Math.random() * 100;
        setTimeout(typeNext, base);
      } else {
        setMessages(prev => prev.map(msg => msg.id === messageId ? { ...msg, text: fullText, isTyping: false } : msg));
        setTypingMessage(null);
      }
    };

    setTypingMessage({ messageId });
    typeNext();
  };

  const skipTyping = () => {
    abortTypingRef.current = true;
  };

  const clearMemory = async () => {
    try {
      await chatbotAPI.clearMemory();
      clearChat();
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
      typeMessage(response.data.response, botMessageId);
    } catch (error) {
      typeMessage("Sorry, I'm having trouble connecting. Please try again later.", botMessageId);
    } finally {
      setLoading(false);
    }
  };

  const handleSuggestion = (text) => {
    setInputMessage(text);
    setTimeout(() => sendMessage(), 50);
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
        <div className={`fixed z-50 flex flex-col overflow-hidden rounded-xl border border-gray-200 bg-white shadow-2xl transition-all duration-300 ${
          isExpanded ? 'right-6 bottom-6 w-[900px] h-[700px] max-w-[95vw] max-h-[85vh]' : 'bottom-24 right-6 w-96 h-[640px]'
        }`}>
          {/* Header */}
          <div className="bg-gradient-to-r from-blue-600 to-blue-500 text-white p-4 rounded-t-xl flex justify-between items-center">
            <div className="space-y-0.5">
              <h3 className="font-semibold flex items-center gap-2">🤖 AI Assistant <span className="w-2 h-2 bg-emerald-400 rounded-full animate-pulse" /></h3>
              <p className="text-blue-100 text-xs">Ask about products, prices, categories, issues</p>
            </div>
            <div className="flex space-x-2">
              <button
                onClick={() => setIsExpanded(e => !e)}
                className="bg-blue-400/40 hover:bg-blue-400 p-2 rounded-lg transition-colors"
                title={isExpanded ? 'Collapse' : 'Expand'}
              >
                {isExpanded ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
              </button>
              <button
                onClick={clearMemory}
                className="bg-purple-500/80 hover:bg-purple-500 p-2 rounded-lg transition-colors"
                title="Clear Memory & Chat"
              >
                <Brain size={16} />
              </button>
              <button
                onClick={clearChat}
                className="bg-blue-500/80 hover:bg-blue-500 p-2 rounded-lg transition-colors"
                title="Clear Chat Only"
              >
                <Trash2 size={16} />
              </button>
            </div>
          </div>

          {/* Suggestions */}
          {showSuggestions && (
            <div className="px-4 pt-3 flex flex-wrap gap-2">
              {suggestions.map(s => (
                <button
                  key={s}
                  onClick={() => handleSuggestion(s)}
                  className="text-xs px-3 py-1.5 rounded-full bg-gray-100 hover:bg-blue-100 text-gray-700 hover:text-blue-700 transition-colors border border-gray-200"
                >
                  {s}
                </button>
              ))}
            </div>
          )}

            {/* Messages */}
            <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 pt-3 pb-2 space-y-3 max-h-[520px] scrollbar-thin scrollbar-thumb-gray-300 scrollbar-track-transparent">
              {messages.map((message, idx) => {
                const isBot = message.isBot;
                const isTyping = message.isTyping;
                return (
                  <div key={message.id} className={`flex ${isBot ? 'justify-start' : 'justify-end'} group`}>
                    {isBot && (
                      <div className="mr-2 mt-1 text-lg select-none">🤖</div>
                    )}
                    <div
                      className={`relative max-w-[75%] p-3 rounded-2xl text-sm leading-relaxed shadow-sm border transition-colors ${
                        isBot ? 'bg-gray-50 border-gray-200 text-gray-800' : 'bg-blue-600 border-blue-600 text-white'
                      }`}
                    >
                      <div className="whitespace-pre-wrap">{isBot ? (
                        <span>{renderMessageWithLinks(message.text, navigate)}{isTyping && <span className="animate-pulse">▋</span>}</span>
                      ) : message.text}</div>
                      <div className={`mt-1 text-[10px] tracking-wide ${isBot ? 'text-gray-500' : 'text-blue-100'}`}>
                        {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </div>
                      {isBot && isTyping && (
                        <button
                          onClick={skipTyping}
                          className="absolute -bottom-5 left-0 text-[10px] text-blue-500 hover:underline"
                        >Skip</button>
                      )}
                    </div>
                    {!isBot && (
                      <div className="ml-2 mt-1 text-lg select-none">🙋</div>
                    )}
                  </div>
                );
              })}
            </div>

          {/* Input */}
          <div className="p-3 border-t bg-gray-50">
            <div className="flex items-end space-x-2">
              <div className="flex-1 relative">
                <textarea
                  value={inputMessage}
                  onChange={(e) => setInputMessage(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
                  }}
                  placeholder={typingMessage ? 'Wait for the assistant to finish...' : 'Ask about products or pricing...'}
                  className="w-full p-3 pr-10 border rounded-xl resize-none h-12 focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white text-sm disabled:bg-gray-100"
                  rows="1"
                  disabled={loading || typingMessage}
                />
                <span className="absolute right-2 bottom-2 text-[10px] text-gray-400">Enter ↵</span>
              </div>
              <button
                onClick={sendMessage}
                disabled={!inputMessage.trim() || loading || typingMessage}
                className="h-12 aspect-square flex items-center justify-center bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 text-white rounded-xl transition-colors shadow"
                title="Send"
              >
                {loading ? <div className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" /> : <Send size={18} />}
              </button>
            </div>
            {typingMessage && (
              <div className="mt-2 text-[11px] text-gray-500 flex items-center gap-1"><span className="w-2 h-2 bg-emerald-400 rounded-full animate-pulse" />Assistant is typing...</div>
            )}
          </div>
        </div>
      )}
    </>
  );
};

export default Chatbot;
