import React from 'react';
import { Link } from 'react-router-dom';
import { ShoppingBag, Users, MessageCircle, Star } from 'lucide-react';

const HomePage = () => {
  const features = [
    {
      icon: <ShoppingBag className="w-8 h-8 text-blue-600" />,
      title: "Smart Product Search",
      description: "Find exactly what you need with our AI-powered search and recommendations."
    },
    {
      icon: <MessageCircle className="w-8 h-8 text-green-600" />,
      title: "AI Assistant",
      description: "Get instant help from our intelligent chatbot available on every page."
    },
    {
      icon: <Users className="w-8 h-8 text-purple-600" />,
      title: "User-Friendly",
      description: "Seamless experience for both customers and administrators."
    },
    {
      icon: <Star className="w-8 h-8 text-yellow-600" />,
      title: "Quality Products",
      description: "Curated selection of high-quality products across multiple categories."
    }
  ];

  const stats = [
    { label: "Products", value: "500+" },
    { label: "Categories", value: "12" },
    { label: "Happy Customers", value: "10K+" },
    { label: "AI Responses", value: "24/7" }
  ];

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Hero Section */}
      <section className="bg-gradient-to-r from-blue-600 to-indigo-700 text-white">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20">
          <div className="text-center">
            <h1 className="text-4xl md:text-6xl font-bold mb-6">
              Welcome to the Future of <span className="text-yellow-300">Shopping</span>
            </h1>
            <p className="text-xl md:text-2xl mb-8 text-blue-100 max-w-3xl mx-auto">
              Experience our AI-powered e-commerce platform with intelligent product recommendations 
              and instant customer support.
            </p>
            <div className="flex flex-col sm:flex-row gap-4 justify-center">
              <Link
                to="/products"
                className="bg-white text-blue-600 hover:bg-gray-100 font-semibold py-3 px-8 rounded-lg transition-colors"
              >
                Browse Products
              </Link>
              <button className="border-2 border-white text-white hover:bg-white hover:text-blue-600 font-semibold py-3 px-8 rounded-lg transition-colors">
                Learn More
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* Stats Section */}
      <section className="py-16 bg-white">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-8">
            {stats.map((stat, index) => (
              <div key={index} className="text-center">
                <div className="text-3xl md:text-4xl font-bold text-blue-600 mb-2">
                  {stat.value}
                </div>
                <div className="text-gray-600 font-medium">{stat.label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section className="py-20 bg-gray-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl font-bold text-gray-900 mb-4">
              Why Choose Our Platform?
            </h2>
            <p className="text-xl text-gray-600 max-w-3xl mx-auto">
              We combine cutting-edge AI technology with exceptional user experience 
              to deliver the best online shopping platform.
            </p>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-8">
            {features.map((feature, index) => (
              <div key={index} className="bg-white p-6 rounded-xl shadow-sm hover:shadow-md transition-shadow">
                <div className="mb-4">{feature.icon}</div>
                <h3 className="text-xl font-semibold text-gray-900 mb-2">
                  {feature.title}
                </h3>
                <p className="text-gray-600">{feature.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-20 bg-blue-600">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <h2 className="text-3xl md:text-4xl font-bold text-white mb-4">
            Ready to Start Shopping?
          </h2>
          <p className="text-xl text-blue-100 mb-8 max-w-2xl mx-auto">
            Explore our vast collection of products and experience the power of AI-assisted shopping.
          </p>
          <Link
            to="/products"
            className="bg-white text-blue-600 hover:bg-gray-100 font-semibold py-3 px-8 rounded-lg transition-colors inline-block"
          >
            View All Products
          </Link>
        </div>
      </section>
    </div>
  );
};

export default HomePage;
