from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import SignupView, SigninView, UserProfileView
from .agentic_views import ChatbotView, AdminIssuesView, ProductsView, ProductDetailView, CategoriesView

urlpatterns = [
    path('signup/', SignupView.as_view(), name='signup'),
    path('signin/', SigninView.as_view(), name='signin'),
    path('user/', UserProfileView.as_view(), name='user-profile'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('chatbot/', ChatbotView.as_view(), name='chatbot'),
    path('admin/issues/', AdminIssuesView.as_view(), name='admin-issues'),
    path('admin/issues/<int:issue_id>/', AdminIssuesView.as_view(), name='admin-issues-detail'),
    path('products/', ProductsView.as_view(), name='products'),
    path('products/<int:product_id>/', ProductDetailView.as_view(), name='product-detail'),
    path('categories/', CategoriesView.as_view(), name='categories'),
]
