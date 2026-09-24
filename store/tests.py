"""Security and integration tests for CALE Shop."""

from django.contrib.auth.hashers import identify_hasher
from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .forms import CustomerRegistrationForm, ProductForm, SecurePasswordResetForm
from .models import AdminAuditLog, CustomerProfile, Order, Product
from .services.orders import create_order_from_cart


@override_settings(
    DEBUG=True,
    SECURE_SSL_REDIRECT=False,
    TURNSTILE_SITE_KEY="",
    TURNSTILE_SECRET_KEY="",
)
class SecurityConfigurationTests(TestCase):
    """Verify the core security controls configured by the project."""

    def setUp(self):
        cache.clear()

    def test_argon2_is_the_primary_password_hasher(self):
        user = User.objects.create_user(
            username="hash-test",
            password="StrongPassword!123",
        )
        self.assertEqual(identify_hasher(user.password).algorithm, "argon2")
        self.assertNotEqual(user.password, "StrongPassword!123")

    def test_registration_strips_html_from_plain_text_fields(self):
        form = CustomerRegistrationForm(
            data={
                "username": "safe-user",
                "email": "safe@example.com",
                "full_name": "<b>علي محمد</b>",
                "phone": "+218 91 1234567",
                "address": "<script>alert(1)</script>طرابلس",
                "password1": "StrongPassword!123",
                "password2": "StrongPassword!123",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["full_name"], "علي محمد")
        self.assertNotIn("<script>", form.cleaned_data["address"])

    def test_registration_requires_unique_email(self):
        User.objects.create_user(
            username="existing-email",
            email="Existing@Example.com",
            password="StrongPassword!123",
        )
        form = CustomerRegistrationForm(
            data={
                "username": "new-user",
                "email": "existing@example.com",
                "full_name": "علي محمد",
                "phone": "+218 91 1234567",
                "address": "طرابلس",
                "password1": "StrongPassword!123",
                "password2": "StrongPassword!123",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("هذا البريد الإلكتروني مستخدم بالفعل.", str(form.errors["email"]))

    def test_product_form_rejects_html_as_markup(self):
        form = ProductForm(
            data={
                "name": "<img src=x onerror=alert(1)>كيكة",
                "description": "<script>alert(1)</script>وصف",
                "price": "25.00",
                "stock": "10",
                "is_active": "on",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertNotIn("<img", form.cleaned_data["name"])
        self.assertNotIn("<script", form.cleaned_data["description"])

    def test_security_headers_are_present(self):
        response = self.client.get(reverse("store:home"))
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response["Referrer-Policy"], "strict-origin-when-cross-origin")
        self.assertIn("frame-ancestors 'none'", response["Content-Security-Policy"])

    def test_login_is_rate_limited(self):
        User.objects.create_user(
            username="rate-user",
            password="StrongPassword!123",
        )

        for _ in range(10):
            response = self.client.post(
                reverse("login"),
                {
                    "username": "rate-user",
                    "password": "wrong-password",
                },
            )
            self.assertNotEqual(response.status_code, 429)

        response = self.client.post(
            reverse("login"),
            {
                "username": "rate-user",
                "password": "wrong-password",
            },
        )
        self.assertEqual(response.status_code, 429)

    def test_customer_cannot_view_another_customers_order(self):
        first = User.objects.create_user(
            username="first",
            password="StrongPassword!123",
        )
        second = User.objects.create_user(
            username="second",
            password="StrongPassword!123",
        )
        order = Order.objects.create(
            user=first,
            full_name="First Customer",
            phone="+218911234567",
            address="Tripoli",
            payment_method=Order.PaymentMethod.CASH_ON_DELIVERY,
        )

        self.client.force_login(second)
        response = self.client.get(
            reverse("store:order_success", kwargs={"order_id": order.id})
        )
        self.assertRedirects(response, reverse("store:home"))

    def test_password_reset_route_exists(self):
        response = self.client.get(reverse("password_reset"))
        self.assertEqual(response.status_code, 200)

    @override_settings(DEBUG=False, TURNSTILE_SITE_KEY="", TURNSTILE_SECRET_KEY="")
    def test_captcha_fails_closed_in_production_when_not_configured(self):
        form = SecurePasswordResetForm(data={"email": "customer@example.com"})
        self.assertFalse(form.is_valid())
        self.assertIn("CAPTCHA", str(form.errors))

    def test_customer_cannot_access_staff_product_management(self):
        user = User.objects.create_user(
            username="customer",
            password="StrongPassword!123",
        )
        self.client.force_login(user)
        response = self.client.get(reverse("store:admin_product_list"))
        self.assertEqual(response.status_code, 403)

    def test_checkout_service_keeps_user_data_isolated(self):
        first = User.objects.create_user(
            username="first-cart",
            password="StrongPassword!123",
        )
        second = User.objects.create_user(
            username="second-cart",
            password="StrongPassword!123",
        )
        product = Product.objects.create(
            name="Cake",
            price="50.00",
            stock=10,
            is_active=True,
        )
        from .models import CartItem
        CartItem.objects.create(user=first, product=product, quantity=2)
        CartItem.objects.create(user=second, product=product, quantity=1)

        order = create_order_from_cart(
            user=first,
            full_name="First Customer",
            phone="+218911234567",
            address="Tripoli",
        )

        self.assertEqual(order.user, first)
        self.assertEqual(product.__class__.objects.get(pk=product.pk).stock, 8)
        self.assertTrue(CartItem.objects.filter(user=second, product=product).exists())


@override_settings(DEBUG=True, SECURE_SSL_REDIRECT=False)
class AdminRoleAccessTests(TestCase):
    """Verify that staff roles stay within their assigned CALE permissions."""

    def setUp(self):
        cache.clear()
        call_command("setup_roles", verbosity=0)
        self.roles = {
            role.name: role
            for role in Group.objects.filter(
                name__in=("Super Admin", "Product Manager", "Order Manager", "Customer Manager")
            )
        }

    def make_staff(self, username, role):
        user = User.objects.create_user(
            username=username,
            password="Secure-Test-Password-27!",
            is_staff=True,
        )
        user.groups.add(self.roles[role])
        return user

    def test_product_manager_is_confined_to_product_management(self):
        self.make_staff("product-manager", "Product Manager")
        self.client.force_login(User.objects.get(username="product-manager"))
        self.assertEqual(self.client.get(reverse("store:admin_product_list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("store:admin_order_list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("store:admin_customer_list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("store:admin_dashboard")).status_code, 403)

    def test_order_manager_is_confined_to_orders(self):
        self.make_staff("order-manager", "Order Manager")
        self.client.force_login(User.objects.get(username="order-manager"))
        self.assertEqual(self.client.get(reverse("store:admin_order_list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("store:admin_product_list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("store:admin_customer_list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("store:admin_dashboard")).status_code, 403)

    def test_customer_manager_does_not_receive_order_or_product_stats(self):
        customer_manager = self.make_staff("customer-manager", "Customer Manager")
        Product.objects.create(name="Private product", price="25.00", stock=4)
        customer = User.objects.create_user(username="store-customer", password="Secure-Test-Password-27!")
        Order.objects.create(
            user=customer,
            full_name="Store Customer",
            phone="0911234567",
            address="Tripoli",
            payment_method=Order.PaymentMethod.CASH_ON_DELIVERY,
        )
        self.client.force_login(customer_manager)
        dashboard = self.client.get(reverse("store:admin_dashboard"))
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(dashboard.context["total_products"], 0)
        self.assertEqual(dashboard.context["total_orders"], 0)
        self.assertEqual(dashboard.context["total_sales"], 0)
        self.assertEqual(self.client.get(reverse("store:admin_customer_list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("store:admin_product_list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("store:admin_order_list")).status_code, 403)

    def test_only_super_admin_can_edit_staff_and_customer_accounts_remain_closed(self):
        manager = self.make_staff("product-manager", "Product Manager")
        target = self.make_staff("target-staff", "Product Manager")
        customer = User.objects.create_user(username="ordinary-customer", password="Secure-Test-Password-27!")
        self.client.force_login(manager)
        self.assertEqual(
            self.client.get(reverse("store:admin_account_update", args=[target.pk])).status_code,
            403,
        )

        super_admin = self.make_staff("store-super-admin", "Super Admin")
        self.client.force_login(super_admin)
        self.assertEqual(
            self.client.get(reverse("store:admin_account_update", args=[customer.pk])).status_code,
            404,
        )
        self.assertEqual(self.client.get(reverse("store:admin_audit_log")).status_code, 200)

    def test_staff_role_changes_require_confirmation_and_are_audited(self):
        super_admin = self.make_staff("store-super-admin", "Super Admin")
        target = self.make_staff("target-staff", "Product Manager")
        self.client.force_login(super_admin)
        url = reverse("store:admin_account_update", args=[target.pk])
        payload = {
            "username": "updated-staff",
            "password": "Zebra-Lantern-72!",
            "groups": [str(self.roles["Order Manager"].pk)],
        }
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 200)
        target.refresh_from_db()
        self.assertEqual(target.username, "target-staff")

        response = self.client.post(url, {**payload, "confirm_roles": "yes"})
        self.assertRedirects(response, reverse("store:admin_user_list"))
        target.refresh_from_db()
        self.assertEqual(target.username, "updated-staff")
        self.assertTrue(target.check_password("Zebra-Lantern-72!"))
        self.assertEqual(list(target.groups.values_list("name", flat=True)), ["Order Manager"])
        event = AdminAuditLog.objects.get(action="staff_updated", target_username="updated-staff")
        self.assertTrue(event.details["password_changed"])
        self.assertNotIn("password", event.details)

    def test_last_active_super_admin_cannot_be_removed(self):
        super_admin = self.make_staff("only-super-admin", "Super Admin")
        self.client.force_login(super_admin)
        response = self.client.post(
            reverse("store:admin_account_update", args=[super_admin.pk]),
            {
                "username": super_admin.username,
                "groups": [str(self.roles["Order Manager"].pk)],
                "confirm_roles": "yes",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(super_admin.groups.filter(name="Super Admin").exists())
