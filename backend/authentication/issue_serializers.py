from rest_framework import serializers
from .issue_models import Issue

class IssueSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.username', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)
    
    class Meta:
        model = Issue
        fields = ['id', 'user_name', 'user_email', 'issue', 'product_id', 'created_at']
