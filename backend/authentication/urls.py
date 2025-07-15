from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import SignupView, SigninView, ProfileView
from .agentic_views import ChatbotView, AdminIssuesView, ProductsView, ProductDetailView, CategoriesView

urlpatterns = [
    # Authentication endpoints
    path('signup/', SignupView.as_view(), name='signup'),
    path('signin/', SigninView.as_view(), name='signin'),
    path('user/', ProfileView.as_view(), name='user-profile'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),

    # Product endpoints
    path('products/', ProductsView.as_view(), name='products'),
    path('products/<int:product_id>/', ProductDetailView.as_view(), name='product-detail'),
    path('categories/', CategoriesView.as_view(), name='categories'),

    # Chatbot endpoint
    path('chatbot/', ChatbotView.as_view(), name='chatbot'),

    # Admin endpoints
    path('admin/issues/', AdminIssuesView.as_view(), name='admin-issues'),
    path('admin/issues/<int:issue_id>/', AdminIssuesView.as_view(), name='admin-issue-detail'),
    path('profile/', ProfileView.as_view(), name='profile'),
]
