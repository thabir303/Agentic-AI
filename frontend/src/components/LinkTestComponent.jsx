import React from 'react';
import { useNavigate } from 'react-router-dom';

const LinkTestComponent = () => {
  const navigate = useNavigate();

  const testText = `Here are some products:
  
Product Link 1:
http://localhost:5173/products/1

Product Link 2:  
http://localhost:5173/products/2

Check out these amazing items!`;

  // Function to render plain text with clickable URLs
  const renderMessageWithLinks = (text, navigate) => {
    // Handle direct URLs (http://localhost:5173/products/:id)
    const urlRegex = /(https?:\/\/localhost:5173\/products\/(\d+))/g;
    
    const parts = [];
    let lastIndex = 0;
    let match;
    
    // Process direct URLs
    while ((match = urlRegex.exec(text)) !== null) {
      // Add text before the URL
      if (match.index > lastIndex) {
        parts.push(text.slice(lastIndex, match.index));
      }
      
      const fullUrl = match[1];
      const productId = match[2];
      
      // Add the clickable URL as a button
      parts.push(
        <button
          key={match.index}
          className="text-blue-600 hover:text-blue-800 underline cursor-pointer font-medium block my-1 bg-transparent border-none p-0 text-left"
          onClick={() => {
            console.log('Navigating to product:', productId);
            navigate(`/products/${productId}`);
          }}
        >
          🔗 View Product {productId} →
        </button>
      );
      
      lastIndex = match.index + match[0].length;
    }
    
    // Add remaining text
    if (lastIndex < text.length) {
      parts.push(text.slice(lastIndex));
    }
    
    return parts.length > 0 ? parts : text;
  };

  return (
    <div className="p-4 border-2 border-blue-300 m-4">
      <h2 className="text-xl font-bold mb-4">Link Test Component</h2>
      <div className="whitespace-pre-wrap bg-gray-100 p-4 rounded">
        {renderMessageWithLinks(testText, navigate)}
      </div>
      
      <div className="mt-4">
        <h3 className="font-bold">Manual Test:</h3>
        <button 
          className="bg-blue-500 text-white px-4 py-2 rounded mr-2"
          onClick={() => navigate('/products/1')}
        >
          Navigate to Product 1
        </button>
        <button 
          className="bg-green-500 text-white px-4 py-2 rounded"
          onClick={() => navigate('/products/2')}
        >
          Navigate to Product 2
        </button>
      </div>
    </div>
  );
};

export default LinkTestComponent;
