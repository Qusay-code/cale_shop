"""
Business logic for changing customer order status.

This module keeps order-status transitions and inventory restoration
outside the administration views.

Centralizing these rules in a service layer makes the workflow:
- Easier to test.
- Easier to maintain.
- Safer when used from different parts of the application.
"""

from django.core.exceptions import ValidationError
from django.db import transaction

from ..models import Order, Product


@transaction.atomic
def change_order_status(order_id, new_status):
    """
    Safely change the status of a customer order.

    Allowed workflow:

        NEW -> PROCESSING -> DELIVERED
          \
           -> CANCELLED

    Rules:
        - The order row is locked during the operation.
        - The requested status must be valid.
        - Orders cannot move backwards in the workflow.
        - DELIVERED orders are final.
        - CANCELLED orders are final.
        - Stock is restored when a NEW or PROCESSING order is cancelled.
        - Cancelling an already cancelled order cannot restore stock
          a second time.

    The complete operation runs inside a database transaction.
    If stock restoration fails, the status change is also rolled back.

    Args:
        order_id:
            Primary key of the order.

        new_status:
            The new status requested by the administrator.

    Returns:
        Order:
            The updated order.

    Raises:
        Order.DoesNotExist:
            If the requested order does not exist.

        ValidationError:
            If the requested status is invalid or the transition
            is not allowed.
    """

    # Lock the order row so two administrators cannot modify
    # the same order at the same time.
    order = (
        Order.objects
        .select_for_update()
        .get(pk=order_id)
    )

    # Build the set of valid status values from the model itself.
    valid_statuses = {
        value
        for value, label in Order.Status.choices
    }

    if new_status not in valid_statuses:
        raise ValidationError(
            "حالة الطلب غير صالحة."
        )

    old_status = order.status

    # If the requested status is already the current status,
    # no database change is necessary.
    if old_status == new_status:
        return order

    # Define the complete and explicit order workflow.
    #
    # NEW:
    #     PROCESSING or CANCELLED
    #
    # PROCESSING:
    #     DELIVERED or CANCELLED
    #
    # DELIVERED:
    #     Final state
    #
    # CANCELLED:
    #     Final state
    allowed_transitions = {
        Order.Status.NEW: {
            Order.Status.PROCESSING,
            Order.Status.CANCELLED,
        },
        Order.Status.PROCESSING: {
            Order.Status.DELIVERED,
            Order.Status.CANCELLED,
        },
        Order.Status.DELIVERED: set(),
        Order.Status.CANCELLED: set(),
    }

    # Reject every transition that is not explicitly allowed.
    if new_status not in allowed_transitions.get(old_status, set()):
        status_labels = dict(Order.Status.choices)

        raise ValidationError(
            f"لا يمكن تغيير حالة الطلب من "
            f"«{status_labels.get(old_status, old_status)}» إلى "
            f"«{status_labels.get(new_status, new_status)}»."
        )

    # Restore inventory when a NEW or PROCESSING order is cancelled.
    #
    # Because this condition can only be true once for an order,
    # the same order cannot restore its stock multiple times.
    if (
        old_status in {Order.Status.NEW, Order.Status.PROCESSING}
        and new_status == Order.Status.CANCELLED
    ):
        items = (
            order.items
            .select_related("product")
            .all()
        )

        for item in items:

            # OrderItem.product uses SET_NULL. If the original product
            # has been deleted, there is no product row to restore.
            if item.product_id is None:
                continue

            # Lock the product row before modifying its stock.
            product = (
                Product.objects
                .select_for_update()
                .get(pk=item.product_id)
            )

            # Return the ordered quantity to available inventory.
            product.stock += item.quantity

            product.save(
                update_fields=[
                    "stock",
                    "updated_at",
                ]
            )

    # Save the new status only after all required operations
    # have completed successfully.
    order.status = new_status

    order.save(
        update_fields=[
            "status",
            "updated_at",
        ]
    )

    return order
