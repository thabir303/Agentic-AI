from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.conf import settings
from .models import Issue, User
from .vector_service import vector_service
from .chatbot_service import chatbot_service
import logging

logger = logging.getLogger(__name__)

class ProductsView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get all products with optional filtering"""
        try:
            # Get query parameters
            search = request.GET.get('search', '')
            category = request.GET.get('category', '')
            limit = int(request.GET.get('limit', 500))
            
            if search:
                # Use vector search for search queries
                products = vector_service.search_products(search, k=limit, category_filter=category if category else None)
            elif category:
                # Get products by category
                products = vector_service.get_products_by_category(category, limit=limit)
            else:
                # Get all products
                products = vector_service.get_all_products(limit=limit)
            
            # Get categories for filtering
            categories = vector_service.get_categories()
            
            return Response({
                'products': products,
                'categories': categories,
                'total': len(products)
            })
            
        except Exception as e:
            logger.error(f"Error fetching products: {e}")
            return Response({
                'error': 'Failed to fetch products'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class ProductDetailView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request, product_id):
        """Get specific product details"""
        try:
            product = vector_service.get_product_by_id(product_id)
            
            if not product:
                return Response({
                    'error': 'Product not found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Get similar products
            similar_products = vector_service.search_products(
                product['text_content'], 
                k=5, 
                category_filter=product['category']
            )
            
            # Remove the current product from similar products
            similar_products = [p for p in similar_products if p['id'] != product_id][:4]
            
            return Response({
                'product': product,
                'similar_products': similar_products
            })
            
        except Exception as e:
            logger.error(f"Error fetching product {product_id}: {e}")
            return Response({
                'error': 'Failed to fetch product details'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class ChatbotView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        """Handle chatbot conversations"""
        try:
            message = request.data.get('message', '').strip()
            
            if not message:
                return Response({
                    'error': 'Message is required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            user = request.user
            
            # Process message with chatbot service
            result = chatbot_service.process_message(
                message=message,
                user_id=user.id,
                user_email=user.email,
                username=user.username
            )
            
            return Response(result)
            
        except Exception as e:
            logger.error(f"Error in chatbot: {e}")
            return Response({
                'response': 'I apologize, but I encountered an error. Please try again.',
                'intent': 'error'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class AdminIssuesView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get all issues (admin only)"""
        if request.user.role != 'admin':
            return Response({
                'error': 'Admin access required'
            }, status=status.HTTP_403_FORBIDDEN)
        
        try:
            issues = Issue.objects.all()
            issues_data = []
            
            for issue in issues:
                issues_data.append({
                    'id': issue.id,
                    'username': issue.username,
                    'email': issue.email,
                    'message': issue.message,
                    'status': issue.status,
                    'created_at': issue.created_at.isoformat(),
                    'updated_at': issue.updated_at.isoformat()
                })
            
            return Response({
                'issues': issues_data,
                'total': len(issues_data)
            })
            
        except Exception as e:
            logger.error(f"Error fetching issues: {e}")
            return Response({
                'error': 'Failed to fetch issues'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def patch(self, request, issue_id=None):
        """Update issue status (admin only)"""
        if request.user.role != 'admin':
            return Response({
                'error': 'Admin access required'
            }, status=status.HTTP_403_FORBIDDEN)
        
        try:
            issue = Issue.objects.get(id=issue_id)
            new_status = request.data.get('status')
            
            if new_status in ['pending', 'in_progress', 'resolved']:
                issue.status = new_status
                issue.save()
                
                return Response({
                    'message': 'Issue status updated successfully',
                    'issue': {
                        'id': issue.id,
                        'status': issue.status
                    }
                })
            else:
                return Response({
                    'error': 'Invalid status'
                }, status=status.HTTP_400_BAD_REQUEST)
                
        except Issue.DoesNotExist:
            return Response({
                'error': 'Issue not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error updating issue: {e}")
            return Response({
                'error': 'Failed to update issue'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def delete(self, request, issue_id=None):
        """Delete issue (admin only)"""
        if request.user.role != 'admin':
            return Response({
                'error': 'Admin access required'
            }, status=status.HTTP_403_FORBIDDEN)
        
        try:
            issue = Issue.objects.get(id=issue_id)
            issue.delete()
            
            return Response({
                'message': 'Issue deleted successfully'
            })
            
        except Issue.DoesNotExist:
            return Response({
                'error': 'Issue not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error deleting issue: {e}")
            return Response({
                'error': 'Failed to delete issue'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CategoriesView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get all product categories"""
        try:
            categories = vector_service.get_categories()
            return Response({
                'categories': categories
            })
        except Exception as e:
            logger.error(f"Error fetching categories: {e}")
            return Response({
                'error': 'Failed to fetch categories'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
