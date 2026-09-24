"""
Business logic related to the customer's shopping cart.

Cart rules are kept in this service layer instead of the views so that
the same validation can be reused from different parts of the application.

This service is responsible for:
- Validating requested quantities.
- Ensuring the product exists and is active.
- Checking available stock.
- Preventing duplicate cart rows for the same user and product.
- Increasing an existing cart item's quantity safely.
"""

from django.core.exceptions import ValidationError

from ..models import CartItem, Product


def add_to_cart(user, product_id, quantity=1):
    """
    Add a product to the authenticated customer's cart.

    Rules:
        - Quantity must be greater than zero.
        - The product must exist.
        - The product must be active.
        - The product must have available stock.
        - The requested quantity cannot exceed available stock.
        - A user cannot have duplicate CartItem records for the same
          product.
        - If the product already exists in the cart, the requested
          quantity is added to the existing quantity.
        - The resulting cart quantity must not exceed current stock.

    Important:
        Stock validation is performed before ``get_or_create()``.
        This prevents a newly created CartItem from being initialized
        with a quantity greater than the available stock.

    Args:
        user:
            The authenticated customer who owns the cart.

        product_id:
            Primary key of the product being added.

        quantity:
            Number of units to add. Defaults to 1.

    Returns:
        CartItem:
            The newly created or updated cart item.

    Raises:
        ValidationError:
            If the quantity is invalid, the product is unavailable,
            or the requested quantity exceeds available stock.
    """

    # Quantity must always be a positive integer.
    if quantity <= 0:
        raise ValidationError(
            "الكمية يجب أن تكون أكبر من صفر."
        )

    # Only active products can be added to a customer's cart.
    try:
        product = Product.objects.get(
            pk=product_id,
            is_active=True,
        )
    except Product.DoesNotExist:
        raise ValidationError(
            "المنتج غير موجود أو غير متاح."
        )

    # A product with zero stock cannot be added.
    if product.stock <= 0:
        raise ValidationError(
            "هذا المنتج غير متوفر حاليًا."
        )

    # This validation is required even when creating the cart item
    # for the first time.
    if quantity > product.stock:
        raise ValidationError(
            f"الكمية المطلوبة تتجاوز المخزون المتاح "
            f"({product.stock})."
        )

    # The database constraint on CartItem also prevents duplicate
    # user/product combinations.
    cart_item, created = CartItem.objects.get_or_create(
        user=user,
        product=product,
        defaults={
            "quantity": quantity,
        },
    )

    # If the product is already in the cart, increase its quantity.
    if not created:
        new_quantity = cart_item.quantity + quantity

        # The total requested quantity must still respect stock.
        if new_quantity > product.stock:
            raise ValidationError(
                f"الكمية المطلوبة تتجاوز المخزون المتاح "
                f"({product.stock})."
            )

        cart_item.quantity = new_quantity
        cart_item.save(
            update_fields=["quantity"],
        )

    return cart_item