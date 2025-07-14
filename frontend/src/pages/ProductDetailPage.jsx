import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, ShoppingCart, Star, Heart, Share2 } from 'lucide-react';

const ProductDetailPage = () => {
  const { id } = useParams();
  const [product, setProduct] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedImage, setSelectedImage] = useState(0);

  useEffect(() => {
    fetchProduct();
  }, [id]);

  const fetchProduct = async () => {
    try {
      setLoading(true);
      // Simulated product data - in real app this would come from your Django API
      const simulatedProduct = {
        id: parseInt(id),
        product_name: `Amazing Product ${id}`,
        description: `This is a comprehensive description of Product ${id}. It features cutting-edge technology, premium materials, and exceptional craftsmanship. Perfect for users who demand quality and performance.`,
        price: (Math.random() * 1000 + 50).toFixed(2),
        category: ['Smartphones', 'Laptops', 'Electronics', 'Furniture', 'Clothing'][Math.floor(Math.random() * 5)],
        rating: (4 + Math.random()).toFixed(1),
        reviews: Math.floor(Math.random() * 500 + 50),
        inStock: Math.random() > 0.2,
        images: [
          `https://picsum.photos/600/600?random=${id}`,
          `https://picsum.photos/600/600?random=${id + 100}`,
          `https://picsum.photos/600/600?random=${id + 200}`,
          `https://picsum.photos/600/600?random=${id + 300}`
        ],
        features: [
          'Premium quality materials',
          'Advanced technology integration',
          'User-friendly design',
          'Excellent durability',
          'Warranty included'
        ],
        specifications: {
          'Brand': `Brand ${Math.floor(Math.random() * 10 + 1)}`,
          'Model': `Model-${id}`,
          'Weight': `${(Math.random() * 5 + 0.5).toFixed(1)} lbs`,
          'Dimensions': `${Math.floor(Math.random() * 20 + 10)}" x ${Math.floor(Math.random() * 15 + 8)}" x ${Math.floor(Math.random() * 5 + 2)}"`,
          'Color': ['Black', 'White', 'Silver', 'Blue', 'Red'][Math.floor(Math.random() * 5)]
        }
      };
      
      setProduct(simulatedProduct);
    } catch (error) {
      console.error('Error fetching product:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50">
        <div className="flex items-center justify-center h-96">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
        </div>
      </div>
    );
  }

  if (!product) {
    return (
      <div className="min-h-screen bg-gray-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="text-center py-12">
            <h1 className="text-2xl font-bold text-gray-900 mb-4">Product Not Found</h1>
            <Link to="/products" className="text-blue-600 hover:text-blue-700">
              ← Back to Products
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Breadcrumb */}
        <div className="mb-6">
          <Link 
            to="/products" 
            className="flex items-center text-blue-600 hover:text-blue-700 font-medium"
          >
            <ArrowLeft size={20} className="mr-2" />
            Back to Products
          </Link>
        </div>

        <div className="bg-white rounded-lg shadow-sm overflow-hidden">
          <div className="grid lg:grid-cols-2 gap-8 p-8">
            {/* Product Images */}
            <div className="space-y-4">
              <div className="aspect-square bg-gray-200 rounded-lg overflow-hidden">
                <img
                  src={product.images[selectedImage]}
                  alt={product.product_name}
                  className="w-full h-full object-cover"
                  onError={(e) => {
                    e.target.src = `https://via.placeholder.com/600x600/f3f4f6/9ca3af?text=Product+${product.id}`;
                  }}
                />
              </div>
              <div className="grid grid-cols-4 gap-2">
                {product.images.map((image, index) => (
                  <button
                    key={index}
                    onClick={() => setSelectedImage(index)}
                    className={`aspect-square bg-gray-200 rounded-lg overflow-hidden border-2 ${
                      selectedImage === index ? 'border-blue-600' : 'border-transparent'
                    }`}
                  >
                    <img
                      src={image}
                      alt={`${product.product_name} ${index + 1}`}
                      className="w-full h-full object-cover"
                      onError={(e) => {
                        e.target.src = `https://via.placeholder.com/150x150/f3f4f6/9ca3af?text=${index + 1}`;
                      }}
                    />
                  </button>
                ))}
              </div>
            </div>

            {/* Product Info */}
            <div className="space-y-6">
              <div>
                <div className="flex items-center space-x-2 mb-2">
                  <span className="bg-blue-100 text-blue-800 text-sm font-medium px-3 py-1 rounded-full">
                    {product.category}
                  </span>
                  <span className={`text-sm font-medium px-3 py-1 rounded-full ${
                    product.inStock 
                      ? 'bg-green-100 text-green-800' 
                      : 'bg-red-100 text-red-800'
                  }`}>
                    {product.inStock ? 'In Stock' : 'Out of Stock'}
                  </span>
                </div>
                
                <h1 className="text-3xl font-bold text-gray-900 mb-4">
                  {product.product_name}
                </h1>

                <div className="flex items-center space-x-4 mb-4">
                  <div className="flex items-center">
                    {[...Array(5)].map((_, i) => (
                      <Star
                        key={i}
                        size={20}
                        className={`${
                          i < Math.floor(product.rating) 
                            ? 'text-yellow-400 fill-current' 
                            : 'text-gray-300'
                        }`}
                      />
                    ))}
                    <span className="ml-2 text-gray-600">
                      {product.rating} ({product.reviews} reviews)
                    </span>
                  </div>
                </div>

                <div className="text-4xl font-bold text-blue-600 mb-6">
                  ${product.price}
                </div>
              </div>

              <div>
                <h3 className="text-lg font-semibold text-gray-900 mb-3">Description</h3>
                <p className="text-gray-600 leading-relaxed">
                  {product.description}
                </p>
              </div>

              <div>
                <h3 className="text-lg font-semibold text-gray-900 mb-3">Key Features</h3>
                <ul className="space-y-2">
                  {product.features.map((feature, index) => (
                    <li key={index} className="flex items-start">
                      <span className="w-2 h-2 bg-blue-600 rounded-full mt-2 mr-3 flex-shrink-0"></span>
                      <span className="text-gray-600">{feature}</span>
                    </li>
                  ))}
                </ul>
              </div>

              <div className="flex space-x-4">
                <button
                  disabled={!product.inStock}
                  className="flex-1 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white font-medium py-3 px-6 rounded-lg transition-colors flex items-center justify-center space-x-2"
                >
                  <ShoppingCart size={20} />
                  <span>{product.inStock ? 'Add to Cart' : 'Out of Stock'}</span>
                </button>
                
                <button className="bg-gray-100 hover:bg-gray-200 text-gray-700 p-3 rounded-lg transition-colors">
                  <Heart size={20} />
                </button>
                
                <button className="bg-gray-100 hover:bg-gray-200 text-gray-700 p-3 rounded-lg transition-colors">
                  <Share2 size={20} />
                </button>
              </div>
            </div>
          </div>

          {/* Specifications */}
          <div className="border-t px-8 py-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Specifications</h3>
            <div className="grid md:grid-cols-2 gap-4">
              {Object.entries(product.specifications).map(([key, value]) => (
                <div key={key} className="flex justify-between py-2 border-b border-gray-100">
                  <span className="font-medium text-gray-700">{key}:</span>
                  <span className="text-gray-600">{value}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ProductDetailPage;
