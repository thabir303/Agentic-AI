from django.contrib import admin
from .models import User
from .issue_models import Issue

admin.site.register(User)
admin.site.register(Issue)
