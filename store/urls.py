"""
URL configuration for the store application.

This module defines:
- Customer storefront routes.
- Registration and shopping-cart routes.
- Checkout and order-success routes.
- Custom administration-panel routes.

The application namespace is ``store`` so URLs can be referenced
through names such as ``store:home`` and ``store:cart``.
"""

from django.urls import path
from store.views import RoleBasedLoginView
from . import admin_views, views


app_name = "store"


urlpatterns = [
    # ------------------------------------------------------------------
    # Customer storefront
    # ------------------------------------------------------------------

    # Storefront home page.
    path(
        "",
        views.home,
        name="home",
    ),
    path("shop/", views.shop, name="shop"),
    path("about/", views.about, name="about"),

    # Customer registration.
    path(
        "register/",
        views.register,
        name="register",
    ),
    # Customer logout.
    path(
    "logout/",
    views.user_logout,
    name="logout",
    ),

    path("account/",
          views.account, 
          name="account"
    ),

    path(
    "account/username/",
    views.account_username,
    name="account_username",
    ),
    path(
    "account/password/",
    views.account_password,
    name="account_password",
),

    # ------------------------------------------------------------------
    # Shopping cart
    # ------------------------------------------------------------------

    # Display the authenticated customer's shopping cart.
    path(
        "cart/",
        views.cart,
        name="cart",
    ),

    # Add a product to the authenticated customer's cart.
    path(
        "cart/add/<int:product_id>/",
        views.add_cart_item,
        name="add_cart_item",
    ),

    # Update the quantity of an existing cart item.
    path(
        "cart/update/<int:item_id>/",
        views.update_cart_item,
        name="update_cart_item",
    ),

    # Remove an item from the authenticated customer's cart.
    path(
        "cart/remove/<int:item_id>/",
        views.remove_cart_item,
        name="remove_cart_item",
    ),

    # ------------------------------------------------------------------
    # Checkout and orders
    # ------------------------------------------------------------------

    # Customer checkout page.
    path(
        "checkout/",
        views.checkout,
        name="checkout",
    ),

    # Order success page.
    #
    # The view itself verifies that the order belongs to the
    # authenticated customer.
    path(
        "order/success/<int:order_id>/",
        views.order_success,
        name="order_success",
    ),
    path(
    "orders/",
    views.customer_orders,
    name="customer_orders",
    ),

    # ------------------------------------------------------------------
    # Custom administration panel
    # ------------------------------------------------------------------

    # Main administration dashboard.
    path(
        "admin-panel/",
        admin_views.dashboard,
        name="admin_dashboard",
    ),
    path(
        "admin-panel/users/",
        admin_views.staff_user_list,
        name="admin_user_list",
    ),
    path(
        "admin-panel/users/create/",
        admin_views.staff_user_create,
        name="admin_user_create",
    ),
    path(
        "admin-panel/accounts/<int:pk>/edit/",
        admin_views.account_update,
        name="admin_account_update",
    ),
    path(
        "admin-panel/audit-log/",
        admin_views.admin_audit_log,
        name="admin_audit_log",
    ),
    path(
    "admin-panel/customers/",
    admin_views.customer_list,
    name="admin_customer_list",
    ),

    # ------------------------------------------------------------------
    # Order management
    # ------------------------------------------------------------------

    # List customer orders.
    path(
        "admin-panel/orders/",
        admin_views.order_list,
        name="admin_order_list",
    ),

    # Display the details of one order.
    path(
        "admin-panel/orders/<int:pk>/",
        admin_views.order_detail,
        name="admin_order_detail",
    ),

    # Change an order's status.
    path(
        "admin-panel/orders/<int:pk>/status/",
        admin_views.order_change_status,
        name="admin_order_change_status",
    ),

    # ------------------------------------------------------------------
    # Product management
    # ------------------------------------------------------------------

    # List products.
    path(
        "admin-panel/products/",
        admin_views.product_list,
        name="admin_product_list",
    ),

    # Create a new product.
    path(
        "admin-panel/products/create/",
        admin_views.product_create,
        name="admin_product_create",
    ),

    # Edit an existing product.
    path(
        "admin-panel/products/<int:pk>/edit/",
        admin_views.product_update,
        name="admin_product_update",
    ),

    # Delete a product.
    path(
        "admin-panel/products/<int:pk>/delete/",
        admin_views.product_delete,
        name="admin_product_delete",
    ),

    # Activate or deactivate a product.
    path(
        "admin-panel/products/<int:pk>/toggle/",
        admin_views.product_toggle_status,
        name="admin_product_toggle_status",
    ),
]
