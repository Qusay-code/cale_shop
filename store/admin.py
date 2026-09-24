"""
Django built-in admin configuration for Product.

The custom admin panel is the primary administration interface.
Django's built-in admin remains available as a fallback.
"""

from django.contrib import admin

from .models import Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    """
    Configure Product display, search, filtering, and editing
    in Django's built-in administration interface.
    """

    # Columns displayed in the product list.
    list_display = (
        "name",
        "price",
        "stock",
        "is_active",
        "created_at",
        "updated_at",
    )

    # Filters displayed in the right-side filter panel.
    list_filter = (
        "is_active",
        "created_at",
    )

    # Fields searchable from the admin search box.
    search_fields = (
        "name",
        "description",
    )

    # Fields that staff can edit directly from the product list.
    list_editable = (
        "price",
        "stock",
        "is_active",
    )

    # Creation and update timestamps are managed automatically by Django.
    readonly_fields = (
        "created_at",
        "updated_at",
    )