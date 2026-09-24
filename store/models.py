"""Database models for CALE Shop."""
from django.core.validators import MinValueValidator
from django.db import models
from django.conf import settings
from django.contrib.auth.models import User

class Product(models.Model):
    """A cake/product offered by the store."""
    name = models.CharField(max_length=200, verbose_name="اسم المنتج")
    description = models.TextField(blank=True, verbose_name="الوصف")
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        verbose_name="السعر",
    )
    image = models.ImageField(
        upload_to="products/",
        blank=True,
        null=True,
        verbose_name="الصورة",
    )
    stock = models.PositiveIntegerField(
        default=0,
        verbose_name="المخزون",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="نشط",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="تاريخ الإضافة",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="آخر تحديث",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "منتج"
        verbose_name_plural = "المنتجات"

        permissions = [
            (
                "view_dashboard",
                "Can view administration dashboard",
            ),
            (
                "view_customer",
                "Can view customer list",
            ),
        ]

    def __str__(self):
        """Return the product name for admin/debugging."""
        return self.name

    
class CartItem(models.Model):
    """
    Represents one product inside a customer's shopping cart.

    Each cart item belongs to exactly one authenticated user and one
    product. The same product cannot appear more than once for the
    same user; its quantity should be updated instead.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="cart_items",
        verbose_name="العميل",
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="cart_items",
        verbose_name="المنتج",
    )

    quantity = models.PositiveIntegerField(
        default=1,
        verbose_name="الكمية",
    )

    class Meta:
        verbose_name = "عنصر في السلة"
        verbose_name_plural = "عناصر السلة"

        # Prevent duplicate products in the same user's cart.
        constraints = [
            models.UniqueConstraint(
                fields=["user", "product"],
                name="unique_cart_item_per_user_product",
            )
        ]

    def __str__(self):
        return f"{self.user} - {self.product} × {self.quantity}"

class Order(models.Model):
    """
    Represents a customer's order.

    The order stores the customer, delivery information,
    payment method, current status, and creation/update timestamps.

    The order status follows the store workflow:

        NEW
            ↓
        PROCESSING
            ↓
        DELIVERED

    An order can also be cancelled when appropriate.
    """

    class Status(models.TextChoices):
        """
        Available order statuses.

        TextChoices provides both a database value and a readable
        label that can be used safely in forms and templates.
        """

        NEW = "new", "جديد"
        PROCESSING = "processing", "قيد التجهيز"
        DELIVERED = "delivered", "تم التسليم"
        CANCELLED = "cancelled", "ملغي"

    class PaymentMethod(models.TextChoices):
        """
        Available payment methods.

        Cash on Delivery is the payment method currently supported
        by the store.
        """

        CASH_ON_DELIVERY = "cash_on_delivery", "الدفع عند الاستلام"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="orders",
        verbose_name="العميل",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NEW,
        verbose_name="حالة الطلب",
    )

    full_name = models.CharField(
        max_length=200,
        verbose_name="الاسم الكامل",
    )

    phone = models.CharField(
        max_length=30,
        verbose_name="رقم الهاتف",
    )

    address = models.TextField(
        verbose_name="العنوان",
    )

    notes = models.TextField(
        blank=True,
        verbose_name="ملاحظات",
    )

    payment_method = models.CharField(
        max_length=30,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH_ON_DELIVERY,
        verbose_name="طريقة الدفع",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="تاريخ إنشاء الطلب",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="آخر تحديث",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "طلب"
        verbose_name_plural = "الطلبات"

    def __str__(self):
        return f"طلب #{self.pk} - {self.full_name}"


class OrderItem(models.Model):
    """
    Represents one product line inside an order.

    Product is nullable because an order must remain historically
    valid even if the original product is deleted later.

    The product name and unit price are stored as snapshots so that
    historical orders are not affected by future product changes.
    """

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="الطلب",
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_items",
        verbose_name="المنتج",
    )

    product_name = models.CharField(
        max_length=200,
        verbose_name="اسم المنتج وقت الطلب",
    )

    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        verbose_name="سعر الوحدة وقت الطلب",
    )

    quantity = models.PositiveIntegerField(
        verbose_name="الكمية",
    )

    class Meta:
        ordering = ["id"]
        verbose_name = "عنصر طلب"
        verbose_name_plural = "عناصر الطلب"

    def __str__(self):
        return f"{self.product_name} × {self.quantity}"
    


class CustomerProfile(models.Model):
    """
    Store additional information for a customer.

    Each Django user can have one customer profile containing
    the customer's full name, phone number, and address.
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="customer_profile",
        verbose_name="المستخدم",
    )

    full_name = models.CharField(
        max_length=150,
        verbose_name="الاسم الثلاثي",
    )

    phone = models.CharField(
        max_length=30,
        verbose_name="رقم الهاتف",
    )

    address = models.TextField(
        verbose_name="العنوان",
    )
    profile_image = models.ImageField(
        upload_to="profiles/",
        blank=True,
        null=True,
        verbose_name="الصورة الشخصية",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="تاريخ الإنشاء",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="آخر تحديث",
    )

    class Meta:
        verbose_name = "بيانات العميل"
        verbose_name_plural = "بيانات العملاء"

    def __str__(self):
        return f"{self.user.username} - {self.full_name}"


class AdminAuditLog(models.Model):
    """Immutable record of sensitive changes made from the CALE admin panel."""

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cale_admin_audit_events",
    )
    action = models.CharField(max_length=40)
    target_username = models.CharField(max_length=150)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "سجل إجراء إداري"
        verbose_name_plural = "سجل الإجراءات الإدارية"
