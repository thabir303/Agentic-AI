from django.urls import path
from .views import SignupView, SigninView
from .agentic_views import ChatbotView, AdminIssuesView, ProductsView, ProductDetailView

urlpatterns = [
    path('signup/', SignupView.as_view(), name='signup'),
    path('signin/', SigninView.as_view(), name='signin'),
    path('chatbot/', ChatbotView.as_view(), name='chatbot'),
    path('admin/issues/', AdminIssuesView.as_view(), name='admin-issues'),
    path('products/', ProductsView.as_view(), name='products'),
    path('products/<int:product_id>/', ProductDetailView.as_view(), name='product-detail'),
]
