"""
Customer-facing views for the Cake Shop.

This module contains the views used by customers to:
- Browse active products.
- Create an account.
- Add, update, and remove cart items.
- Complete checkout.
- View the success page of their own orders.

Business rules such as cart validation and order creation are delegated
to the service layer so that important logic is not duplicated inside
the HTTP views.
"""

from django.contrib.auth.views import LoginView, PasswordResetView
from django.db import transaction
from django.contrib import messages
from django.contrib.auth import login ,logout
from django.urls import reverse, reverse_lazy
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from decimal import Decimal
from .forms import (
    AccountProfileForm,
    CheckoutForm,
    CustomerRegistrationForm,
)
from .models import CartItem, Order, Product, CustomerProfile
from .services.cart import add_to_cart
from .services.orders import create_order_from_cart
from django.contrib.auth import update_session_auth_hash
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.decorators import method_decorator
from django.contrib.auth.forms import PasswordChangeForm
from .forms import SecureAuthenticationForm, SecurePasswordResetForm
from .security import rate_limit
from .services.images import process_uploaded_image

@method_decorator(rate_limit(key_prefix="login", limit=10, period=900), name="post")
class RoleBasedLoginView(LoginView):
    """
    تسجيل دخول موحد لجميع المستخدمين مع توجيه كل مستخدم
    إلى الصفحة المناسبة حسب دوره.

    الأدوار:
    - Super Admin → لوحة التحكم
    - Product Manager → إدارة المنتجات
    - Order Manager → إدارة الطلبات
    - Customer Manager → إدارة العملاء
    - Customer → المتجر
    """

    template_name = "registration/login.html"
    authentication_form = SecureAuthenticationForm

    def get_success_url(self):
        """Return a safe explicit destination based on the user's role."""
        user = self.request.user

        # Never allow a supplied next URL to bypass the role-based landing page.
        if user.is_superuser:
            return reverse("store:admin_dashboard")

        if user.is_staff:
            roles = set(user.groups.values_list("name", flat=True))
            if "Super Admin" in roles:
                return reverse("store:admin_dashboard")
            if "Product Manager" in roles:
                return reverse("store:admin_product_list")
            if "Order Manager" in roles:
                return reverse("store:admin_order_list")
            if "Customer Manager" in roles:
                return reverse("store:admin_customer_list")
            return reverse("store:admin_dashboard")

        return reverse("store:home")

def home(request):
    """
    Display active products on the customer storefront.

    Only products with ``is_active=True`` are visible to customers.
    Products with zero stock remain visible so the customer can see
    that the product exists, while the template can indicate that
    it is currently unavailable.

    Args:
        request: The current HTTP request.

    Returns:
        HttpResponse: The rendered home page.
    """

    products = Product.objects.filter(is_active=True)

    return render(
        request,
        "store/shop/home.html",
        {
            "products": products,
        },
    )

def about(request):
    """
    Display the About Us page.

    This page provides general information about CALE Shop
    and the services offered by the store.
    """

    return render(
        request,
        "store/shop/about.html",
    )

@rate_limit(key_prefix="register", limit=5, period=3600)
def register(request):
    """
    Register a new customer account.

    The function creates both:
    - Django User
    - CustomerProfile

    The two records are created inside one database transaction
    to prevent creating an incomplete customer account.
    """

    if request.user.is_authenticated:
        return redirect("store:home")

    if request.method == "POST":
        form = CustomerRegistrationForm(request.POST)

        if form.is_valid():
            with transaction.atomic():
                user = form.save()

                CustomerProfile.objects.create(
                    user=user,
                    full_name=form.cleaned_data["full_name"],
                    phone=form.cleaned_data["phone"],
                    address=form.cleaned_data["address"],
                )

            login(request, user)

            messages.success(
                request,
                "تم إنشاء حسابك بنجاح.",
            )

            return redirect("store:home")

    else:
        form = CustomerRegistrationForm()

    return render(
        request,
        "registration/register.html",
        {"form": form},
    )

@login_required(login_url="login")
def account(request):
    """
    Display and update the authenticated customer's profile.

    Profile images are validated, resized, and converted to WebP
    through the dedicated image service. When a new image replaces
    an old one, the old stored file is deleted after the database
    update succeeds.
    """
    try:
        profile = request.user.customer_profile
    except CustomerProfile.DoesNotExist:
        messages.error(
            request,
            "بيانات حسابك غير مكتملة. يرجى التواصل مع الإدارة.",
        )
        return redirect("store:home")

    if request.method == "POST":
        # Keep the old file name before applying form changes.
        old_image_name = profile.profile_image.name

        form = AccountProfileForm(
            request.POST,
            request.FILES,
            instance=profile,
        )

        if form.is_valid():
            profile = form.save(commit=False)
            uploaded_image = form.cleaned_data.get("profile_image")

            if uploaded_image:
                try:
                    filename, processed_image = process_uploaded_image(
                        uploaded_image,
                        max_dimension=1200,
                        quality=88,
                    )

                    profile.profile_image.save(
                        filename,
                        processed_image,
                        save=False,
                    )

                except ValidationError as error:
                    form.add_error(
                        "profile_image",
                        error.message,
                    )
                else:
                    profile.save()

                    # Delete the previous image only after the new
                    # profile data has been saved successfully.
                    if (
                        old_image_name
                        and old_image_name != profile.profile_image.name
                    ):
                        profile.profile_image.storage.delete(
                            old_image_name
                        )

                    messages.success(
                        request,
                        "تم تحديث بيانات حسابك بنجاح.",
                    )
                    return redirect("store:account")

            else:
                profile.save()

                # Handles the case where the user clears
                # the existing profile image.
                if (
                    old_image_name
                    and old_image_name != profile.profile_image.name
                ):
                    profile.profile_image.storage.delete(
                        old_image_name
                    )

                messages.success(
                    request,
                    "تم تحديث بيانات حسابك بنجاح.",
                )
                return redirect("store:account")

    else:
        form = AccountProfileForm(instance=profile)

    return render(
        request,
        "store/shop/account.html",
        {
            "form": form,
            "profile": profile,
        },
    )

@login_required(login_url="login")
def account_username(request):
    """
    Update the authenticated customer's username.

    The username is validated through AccountUsernameForm.
    After a successful update, the customer remains authenticated.
    """

    from .forms import AccountUsernameForm

    if request.method == "POST":
        form = AccountUsernameForm(
            request.POST,
            instance=request.user,
        )

        if form.is_valid():
            form.save()

            messages.success(
                request,
                "تم تحديث اسم المستخدم بنجاح.",
            )

            return redirect("store:account")

    else:
        form = AccountUsernameForm(instance=request.user)

    return render(
        request,
        "store/shop/account_username.html",
        {
            "form": form,
        },
    )

@login_required(login_url="login")
def account_password(request):
    """
    Allow the authenticated customer to change their password.

    The password is changed using Django's built-in PasswordChangeForm,
    which validates the current password and the new password securely.

    The user's session is preserved after a successful password change.
    """

    if request.method == "POST":
        form = PasswordChangeForm(
            user=request.user,
            data=request.POST,
        )

        if form.is_valid():
            user = form.save()

            # Keep the user logged in after changing the password.
            update_session_auth_hash(request, user)

            messages.success(
                request,
                "تم تغيير كلمة المرور بنجاح.",
            )

            return redirect("store:account")

    else:
        form = PasswordChangeForm(user=request.user)

    return render(
        request,
        "store/shop/account_password.html",
        {
            "form": form,
        },
    )

@login_required(login_url="login")
def add_cart_item(request, product_id):
    """
    Add a product to the authenticated customer's cart.

    The operation is restricted to POST requests. The actual business
    rules, including product availability and stock validation, are
    handled by the cart service.

    Args:
        request: The current HTTP request.
        product_id: Primary key of the product to add.

    Returns:
        HttpResponseRedirect: Redirects back to the storefront.
    """

    if request.method != "POST":
        return redirect("store:home")

    try:
        # Convert the submitted quantity into an integer.
        quantity = int(request.POST.get("quantity", 1))

        # Delegate cart business logic to the service layer.
        add_to_cart(
            user=request.user,
            product_id=product_id,
            quantity=quantity,
        )

        messages.success(
            request,
            "تمت إضافة المنتج إلى السلة بنجاح.",
        )

    except ValueError:
        messages.error(
            request,
            "الكمية غير صحيحة.",
        )

    except ValidationError as error:
        messages.error(
            request,
            error.message,
        )

    referer = request.META.get("HTTP_REFERER")

    if referer and url_has_allowed_host_and_scheme(
    url=referer,
    allowed_hosts={request.get_host()},
    require_https=request.is_secure(),
):
         return redirect(referer)

    return redirect("store:home")


@login_required(login_url="login")
def cart(request):
    """
    Display the authenticated customer's shopping cart.

    Only items belonging to the current user are retrieved.

    The total cart value is calculated from the current product prices.
    The price actually charged during checkout is stored separately
    in OrderItem.unit_price.

    Args:
        request: The current HTTP request.

    Returns:
        HttpResponse: The rendered shopping cart page.
    """

    cart_items = (
        CartItem.objects
        .select_related("product")
        .filter(user=request.user)
    )

    # Calculate the current total value of all cart items.
    total = sum(
        item.product.price * item.quantity
        for item in cart_items
    )

    return render(
        request,
        "store/shop/cart.html",
        {
            "cart_items": cart_items,
            "total": total,
        },
    )


@login_required(login_url="login")
def update_cart_item(request, item_id):
    """
    Update the quantity of one item in the customer's cart.

    Security:
        The CartItem is retrieved using both its primary key and
        the authenticated user. Therefore, a customer cannot modify
        another customer's cart item.

    Validation:
        - Quantity must be a positive integer.
        - Quantity cannot exceed the product's current stock.

    Args:
        request: The current HTTP request.
        item_id: Primary key of the CartItem.

    Returns:
        HttpResponseRedirect: Redirects back to the cart page.
    """

    if request.method != "POST":
        return redirect("store:cart")

    try:
        quantity = int(request.POST.get("quantity", 1))

        if quantity <= 0:
            messages.error(
                request,
                "الكمية يجب أن تكون أكبر من صفر.",
            )
            return redirect("store:cart")

        # Retrieve only an item belonging to the current customer.
        cart_item = (
            CartItem.objects
            .select_related("product")
            .get(
                pk=item_id,
                user=request.user,
            )
        )

        # Do not allow the requested quantity to exceed stock.
        if quantity > cart_item.product.stock:
            messages.error(
                request,
                f"الكمية المطلوبة تتجاوز المخزون المتاح "
                f"({cart_item.product.stock}).",
            )
            return redirect("store:cart")

        cart_item.quantity = quantity
        cart_item.save(update_fields=["quantity"])

        messages.success(
            request,
            "تم تحديث الكمية بنجاح.",
        )

    except ValueError:
        messages.error(
            request,
            "الكمية غير صحيحة.",
        )

    except CartItem.DoesNotExist:
        messages.error(
            request,
            "عنصر السلة غير موجود.",
        )

    return redirect("store:cart")


@login_required(login_url="login")
def remove_cart_item(request, item_id):
    """
    Remove one item from the authenticated customer's cart.

    The operation is restricted to POST requests.

    Security:
        The CartItem lookup includes the authenticated user, preventing
        one customer from deleting another customer's cart item.

    Args:
        request: The current HTTP request.
        item_id: Primary key of the CartItem.

    Returns:
        HttpResponseRedirect: Redirects back to the cart page.
    """

    if request.method != "POST":
        return redirect("store:cart")

    try:
        # Retrieve only an item belonging to the current customer.
        cart_item = CartItem.objects.get(
            pk=item_id,
            user=request.user,
        )

        cart_item.delete()

        messages.success(
            request,
            "تم حذف المنتج من السلة بنجاح.",
        )

    except CartItem.DoesNotExist:
        messages.error(
            request,
            "عنصر السلة غير موجود.",
        )

    return redirect("store:cart")


@login_required(login_url="login")
@rate_limit(key_prefix="checkout", limit=10, period=600)
def checkout(request):
    """
    Display the checkout form and create a new customer order.

    GET:
        Load the customer's saved profile information into the
        checkout form.

    POST:
        Validate the checkout information, update the customer's
        profile with the editable phone and address fields, then
        delegate order creation to the order service.

    Staff users are prevented from creating customer orders through
    the storefront.
    """

    # Staff users manage the store through the custom admin panel.
    if request.user.is_staff:
        messages.error(
            request,
            "حساب الإدارة مخصص لإدارة المتجر ولا يمكنه إنشاء طلبات.",
        )
        return redirect("store:admin_dashboard")

    # Retrieve only the current customer's cart items.
    cart_items = (
        CartItem.objects
        .select_related("product")
        .filter(user=request.user)
    )
    cart_total = sum(
    (
        item.product.price * item.quantity
        for item in cart_items
    ),
    Decimal("0.00"),
)

    # Checkout cannot proceed with an empty cart.
    if not cart_items.exists():
        messages.error(
            request,
            "السلة فارغة. أضف منتجًا قبل إتمام الطلب.",
        )
        return redirect("store:cart")

    # Get the customer's saved profile.
    try:
        profile = request.user.customer_profile
    except CustomerProfile.DoesNotExist:
        messages.error(
            request,
            "بيانات حسابك غير مكتملة. يرجى التواصل مع الإدارة.",
        )
        return redirect("store:home")

    if request.method == "POST":
        form = CheckoutForm(request.POST)

        if form.is_valid():
            try:
                # Update the customer's saved contact information.
                profile.phone = form.cleaned_data["phone"]
                profile.address = form.cleaned_data["address"]
                profile.save(update_fields=["phone", "address", "updated_at"])

                # Delegate order creation to the transaction-safe service.
                order = create_order_from_cart(
                    user=request.user,
                    full_name=profile.full_name,
                    phone=profile.phone,
                    address=profile.address,
                    notes=form.cleaned_data["notes"],
                    payment_method=form.cleaned_data["payment_method"],
                )

                messages.success(
                    request,
                    f"تم إنشاء طلبك بنجاح. رقم الطلب: #{order.id}",
                )

                return redirect(
                    "store:order_success",
                    order_id=order.id,
                )

            except ValidationError as error:
                messages.error(
                    request,
                    error.message,
                )

                # Reload the cart after a failed transaction.
                cart_items = (
                    CartItem.objects
                    .select_related("product")
                    .filter(user=request.user)
                )

    else:
        # GET request: preload saved customer information.
        form = CheckoutForm(
            initial={
                "full_name": profile.full_name,
                "phone": profile.phone,
                "address": profile.address,
            }
        )

    return render(
        request,
        "store/shop/checkout.html",
        {
            "form": form,
            "cart_items": cart_items,
            "cart_total": cart_total,
        },
    )


@login_required(login_url="login")
def order_success(request, order_id):
    """
    Display the success page for an order belonging to the customer.

    Security:
        The order lookup includes both the order ID and the current
        authenticated user. A customer therefore cannot access another
        customer's order success page by changing the URL.

    Args:
        request: The current HTTP request.
        order_id: Primary key of the order.

    Returns:
        HttpResponse: The order success page or a redirect if the
        order does not belong to the current customer.
    """

    # Retrieve only an order belonging to the authenticated customer.
    order = (
        Order.objects
        .filter(
            pk=order_id,
            user=request.user,
        )
        .prefetch_related("status_history")
        .first()
    )

    if order is None:
        messages.error(
            request,
            "الطلب غير موجود.",
        )
        return redirect("store:home")

    return render(
        request,
        "store/shop/order_success.html",
        {
            "order": order,
        },
    )

@login_required(login_url="login")
def customer_orders(request):
    """
    Display all orders belonging to the authenticated customer.

    Security:
        Only orders associated with the current authenticated user
        are returned. Customers cannot view other customers' orders.

    Args:
        request: The current HTTP request.

    Returns:
        HttpResponse: The customer's orders page.
    """

    # Retrieve only orders belonging to the authenticated customer.
    orders = (
        Order.objects
        .filter(user=request.user)
        .prefetch_related("items", "status_history")
        .order_by("-created_at")
    )

    return render(
        request,
        "store/shop/orders.html",
        {
            "orders": orders,
        },
    )

def shop(request):
    """
    Display the storefront product listing.

    Only active products are displayed.
    Products remain visible even when their stock reaches zero.
    """

    products = Product.objects.filter(
        is_active=True
    ).order_by("-created_at")

    return render(
        request,
        "store/shop/shop.html",
        {
            "products": products,
        },
    )

@method_decorator(rate_limit(key_prefix="password-reset", limit=5, period=900), name="post")
class SecurePasswordResetView(PasswordResetView):
    """Django's password-reset flow with CAPTCHA and throttling."""

    template_name = "registration/password_reset_form.html"
    email_template_name = "registration/password_reset_email.txt"
    subject_template_name = "registration/password_reset_subject.txt"
    form_class = SecurePasswordResetForm
    success_url = reverse_lazy("password_reset_done")


def user_logout(request):
    """
    Log the current user out of CALE Shop.

    The authentication session is terminated using Django's
    built-in authentication system, then the user is redirected
    to the storefront home page.
    """

    if request.method == "POST":
        logout(request)
        return redirect("store:home")

    # Logout is state-changing and therefore intentionally rejects GET.
    return redirect("store:home")
