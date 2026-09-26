"""
Order-related business logic.

This module contains the business logic responsible for converting
a customer's shopping cart into a confirmed order.

Keeping this logic outside the HTTP views makes the application:
- Easier to test.
- Easier to maintain.
- Safer against partial database updates.
- Reusable from other parts of the application.

The checkout operation is protected by a database transaction and
row-level locking to prevent stock inconsistencies during concurrent
orders.
"""

from django.core.exceptions import ValidationError
from django.db import transaction

from ..models import CartItem, Order, OrderItem, OrderStatusHistory, Product


@transaction.atomic
def create_order_from_cart(
    user,
    full_name,
    phone,
    address,
    notes="",
    payment_method=Order.PaymentMethod.CASH_ON_DELIVERY,
):
    """
    Convert the authenticated customer's cart into a new order.

    The complete operation runs inside one database transaction.

    Processing steps:
        1. Lock the customer's cart items.
        2. Verify that the cart is not empty.
        3. Create the Order record.
        4. Lock every related product row.
        5. Verify that each product is still active.
        6. Verify that sufficient stock is available.
        7. Create an OrderItem snapshot for each cart item.
        8. Deduct the purchased quantity from product stock.
        9. Clear the customer's cart.

    Transaction safety:
        If any validation fails during the process, Django rolls back
        the entire transaction. This means that a partially created
        order, partial stock deduction, or partial cart deletion
        cannot remain in the database.

    Important:
        OrderItem stores the product name and price as snapshots.
        Therefore, changing a product's name or price later does not
        change historical order information.

    Args:
        user:
            The authenticated customer placing the order.

        full_name:
            Customer's full name used for delivery.

        phone:
            Customer's phone number.

        address:
            Customer's delivery address.

        notes:
            Optional customer notes.

        payment_method:
            Payment method selected by the customer.

    Returns:
        Order:
            The newly created order.

    Raises:
        ValidationError:
            If the cart is empty, a product is no longer available,
            or there is insufficient stock.
    """

    # Lock all cart rows belonging to this customer.
    #
    # select_for_update() prevents another transaction from modifying
    # these cart rows while the current checkout is being processed.
    cart_items = list(
        CartItem.objects
        .select_for_update()
        .select_related("product")
        .filter(user=user)
    )

    # An empty cart cannot produce an order.
    if not cart_items:
        raise ValidationError(
            "السلة فارغة. أضف منتجًا قبل إتمام الطلب."
        )

    # Create the order inside the same transaction.
    #
    # If anything fails later, this record will also be rolled back.
    order = Order.objects.create(
        user=user,
        full_name=full_name,
        phone=phone,
        address=address,
        notes=notes,
        payment_method=payment_method,
        status=Order.Status.NEW,
    )
    OrderStatusHistory.objects.create(
        order=order,
        status=Order.Status.NEW,
    )

    # Process every item currently in the customer's cart.
    for cart_item in cart_items:

        # Lock the actual product row before checking or changing stock.
        #
        # This is important when two customers try to purchase the
        # same product at nearly the same time.
        product = (
            Product.objects
            .select_for_update()
            .get(pk=cart_item.product_id)
        )

        # A product may have been disabled after it was added to the
        # customer's cart. It must be active at checkout time.
        if not product.is_active:
            raise ValidationError(
                f"المنتج «{product.name}» لم يعد متاحًا."
            )

        # Re-check the stock at checkout time.
        #
        # The stock may have changed after the product was added
        # to the cart, so the cart quantity cannot be trusted alone.
        if cart_item.quantity > product.stock:
            raise ValidationError(
                f"المنتج «{product.name}» لا يتوفر منه "
                f"سوى {product.stock} قطعة."
            )

        # Create an immutable snapshot of the product information
        # relevant to this order.
        #
        # Even if the product is renamed or its price changes later,
        # this OrderItem will retain the original values.
        OrderItem.objects.create(
            order=order,
            product=product,
            product_name=product.name,
            unit_price=product.price,
            quantity=cart_item.quantity,
        )

        # Deduct the purchased quantity from the current stock.
        product.stock -= cart_item.quantity

        product.save(
            update_fields=[
                "stock",
                "updated_at",
            ]
        )

    # The complete order was created successfully.
    # Clear the customer's cart only after all items were processed.
    CartItem.objects.filter(
        user=user,
    ).delete()

    return order
