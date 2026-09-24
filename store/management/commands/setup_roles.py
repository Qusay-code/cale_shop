from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

from store.models import Product, Order


class Command(BaseCommand):
    """
    Create and configure the default administration roles.

    The command is safe to run multiple times because get_or_create()
    prevents duplicate groups from being created.

    Roles:
        Super Admin:
            Receives all Django permissions.

        Product Manager:
            Can view, add, change, and delete products.

        Order Manager:
            Can view and change customer orders.

        Customer Manager:
            Can view the administration dashboard and customer list.
    """

    help = "Create and configure CALE Shop administration roles."

    def handle(self, *args, **options):
        # ---------------------------------------------------------
        # 1. Create administration groups.
        # ---------------------------------------------------------
        super_admin_group, _ = Group.objects.get_or_create(
            name="Super Admin",
        )

        product_manager_group, _ = Group.objects.get_or_create(
            name="Product Manager",
        )

        order_manager_group, _ = Group.objects.get_or_create(
            name="Order Manager",
        )

        customer_manager_group, _ = Group.objects.get_or_create(
            name="Customer Manager",
        )

        # ---------------------------------------------------------
        # 2. Get Product permissions.
        # ---------------------------------------------------------
        product_content_type = ContentType.objects.get_for_model(
            Product,
        )

        product_permissions = Permission.objects.filter(
            content_type=product_content_type,
            codename__in=[
                "add_product",
                "change_product",
                "delete_product",
                "view_product",
            ],
        )

        # ---------------------------------------------------------
        # 3. Get Order permissions.
        # ---------------------------------------------------------
        order_content_type = ContentType.objects.get_for_model(
            Order,
        )

        order_permissions = Permission.objects.filter(
            content_type=order_content_type,
            codename__in=[
                "change_order",
                "view_order",
            ],
        )

        # ---------------------------------------------------------
        # 4. Get custom administration permissions.
        #
        # These permissions were added to the Product model
        # through Product.Meta.permissions.
        # ---------------------------------------------------------
        dashboard_permission = Permission.objects.get(
            content_type=product_content_type,
            codename="view_dashboard",
        )

        customer_permission = Permission.objects.get(
            content_type=product_content_type,
            codename="view_customer",
        )

        # ---------------------------------------------------------
        # 5. Assign Product Manager permissions.
        # ---------------------------------------------------------
        product_manager_group.permissions.set(
            product_permissions,
        )

        # ---------------------------------------------------------
        # 6. Assign Order Manager permissions.
        # ---------------------------------------------------------
        order_manager_group.permissions.set(
            order_permissions,
        )

        # ---------------------------------------------------------
        # 7. Assign Customer Manager permissions.
        # ---------------------------------------------------------
        customer_manager_group.permissions.set(
            [
                dashboard_permission,
                customer_permission,
            ],
        )

        # ---------------------------------------------------------
        # 8. Super Admin receives all permissions.
        # ---------------------------------------------------------
        all_permissions = Permission.objects.all()

        super_admin_group.permissions.set(
            all_permissions,
        )

        # ---------------------------------------------------------
        # 9. Display the configuration result.
        # ---------------------------------------------------------
        self.stdout.write(
            self.style.SUCCESS(
                "تم إعداد أدوار الإدارة والصلاحيات بنجاح."
            )
        )

        self.stdout.write(
            "Super Admin: جميع الصلاحيات"
        )

        self.stdout.write(
            "Product Manager: إدارة المنتجات"
        )

        self.stdout.write(
            "Order Manager: عرض وتعديل الطلبات"
        )

        self.stdout.write(
            "Customer Manager: Dashboard والعملاء"
        )