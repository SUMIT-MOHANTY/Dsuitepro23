"""
Django Admin configuration for Core app
"""

from django.contrib import admin

# Core app provides abstract models only, no concrete models to register
# Domain apps will register their models that inherit from core base classes
