"""
Custom administration-panel views for CALE Shop.

This module provides the custom admin interface used by staff users
to manage products and customer orders.

Important:
    These views are separate from Django's built-in admin interface.
    Django's built-in admin remains available as a fallback.

Security:
    Every view in this module is protected by ``staff_required``.
    Therefore, only authenticated users with ``is_staff=True`` can
    access the custom administration panel.
"""
from django.db import models, transaction
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.models import Group, User
from django.core.paginator import Paginator
from .forms import AccountUpdateForm, ProductForm, StaffAccountCreationForm
from .models import AdminAuditLog, Order, Product
from .services.order_status import change_order_status
from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from .models import Order, OrderItem, Product
from decimal import Decimal
from .services.images import process_uploaded_image
from .security import rate_limit
from functools import wraps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import permission_required

def staff_required(view_func):
    """
    Restrict a view to authenticated staff users.

    Unauthenticated users are redirected to the login page.
    Authenticated non-staff users receive HTTP 403 Forbidden.
    """

    @wraps(view_func)
    def wrapped_view(request, *args, **kwargs):

        if not request.user.is_authenticated:
            return login_required(
                login_url="login"
            )(view_func)(request, *args, **kwargs)

        if not request.user.is_staff:
            raise PermissionDenied(
                "ليس لديك صلاحية للوصول إلى هذه الصفحة."
            )

        return view_func(request, *args, **kwargs)

    return wrapped_view


def is_cale_super_admin(user):
    return user.is_superuser or user.groups.filter(name="Super Admin").exists()

@staff_required
@permission_required("store.view_dashboard", raise_exception=True)
def dashboard(request):
    """
    Display the main custom administration dashboard.

    The dashboard statistics are calculated directly from the database
    so the displayed numbers always reflect the current store data.
    """

    can_view_orders = request.user.has_perm("store.view_order")
    can_view_products = request.user.has_perm("store.view_product")
    can_view_customers = request.user.has_perm("store.view_customer")
    total_products = Product.objects.count() if can_view_products else 0
    total_customers = User.objects.filter(is_staff=False).count() if can_view_customers else 0
    total_orders = Order.objects.count() if can_view_orders else 0
    new_orders = Order.objects.filter(status=Order.Status.NEW).count() if can_view_orders else 0

    total_sales = (
    OrderItem.objects
    .filter(
        order__status__in=[
            Order.Status.NEW,
            Order.Status.PROCESSING,
            Order.Status.DELIVERED,
        ]
    )
    .aggregate(
        total=Sum(
            ExpressionWrapper(
                F("unit_price") * F("quantity"),
                output_field=DecimalField(
                    max_digits=12,
                    decimal_places=2,
                ),
            )
        )
    )["total"]
    or 0
    ) if can_view_orders else 0
    recent_orders = (
        Order.objects.select_related("user").order_by("-created_at")[:6]
        if can_view_orders
        else []
    )
    low_stock_products = (
        Product.objects.filter(is_active=True, stock__lte=5)
        .order_by("stock", "name")[:5]
        if can_view_products
        else []
    )

    context = {
        "page_title": "Dashboard",
        "total_products": total_products,
        "total_customers": total_customers,
        "total_orders": total_orders,
        "new_orders": new_orders,
        "total_sales": total_sales,
        "recent_orders": recent_orders,
        "low_stock_products": low_stock_products,
        "can_view_orders": can_view_orders,
        "can_view_products": can_view_products,
        "can_add_products": request.user.has_perm("store.add_product"),
        "can_view_customers": can_view_customers,
        "can_manage_users": request.user.has_perm("auth.view_user")
        and request.user.has_perm("auth.add_user"),
    }

    return render(
        request,
        "store/admin/dashboard.html",
        context,
    )

@staff_required
@permission_required("auth.view_user", raise_exception=True)
def staff_user_list(request):
    """List staff accounts and their assigned CALE administration roles."""
    users = User.objects.filter(is_staff=True).prefetch_related("groups")
    search_query = request.GET.get("q", "").strip()[:100]
    role_filter = request.GET.get("role", "").strip()
    sort = request.GET.get("sort", "newest")
    if search_query:
        users = users.filter(username__icontains=search_query)
    available_roles = Group.objects.filter(
        name__in=("Super Admin", "Product Manager", "Order Manager", "Customer Manager")
    ).order_by("name")
    valid_roles = set(available_roles.values_list("name", flat=True))
    if role_filter in valid_roles:
        users = users.filter(groups__name=role_filter).distinct()
    elif role_filter:
        role_filter = ""
    ordering = {
        "newest": "-date_joined",
        "oldest": "date_joined",
        "username": "username",
        "username_desc": "-username",
    }
    users = users.order_by("-is_superuser", ordering.get(sort, "-date_joined"))
    page_obj = Paginator(users, 25).get_page(request.GET.get("page"))
    return render(
        request,
        "store/admin/users/list.html",
        {
            "page_title": "إدارة حسابات الموظفين",
            "staff_users": page_obj.object_list,
            "page_obj": page_obj,
            "search_query": search_query,
            "role_filter": role_filter,
            "available_roles": available_roles,
            "sort": sort if sort in ordering else "newest",
            "can_manage_accounts": is_cale_super_admin(request.user),
        },
    )


@staff_required
@permission_required("auth.add_user", raise_exception=True)
@rate_limit(key_prefix="admin-create-staff", limit=20, period=3600)
def staff_user_create(request):
    """Create a staff account and assign approved role groups."""
    if request.method == "POST":
        form = StaffAccountCreationForm(request.POST)
        if form.is_valid():
            if form.cleaned_data["groups"].exists() and request.POST.get("confirm_roles") != "yes":
                form.add_error("groups", "أكد الأدوار المحددة قبل إنشاء الحساب.")
                return render(request, "store/admin/users/form.html", {
                    "page_title": "إنشاء حساب موظف",
                    "form": form,
                    "roles_available": form.fields["groups"].queryset.exists(),
                })
            with transaction.atomic():
                user = form.save()
                AdminAuditLog.objects.create(
                    actor=request.user,
                    action="staff_created",
                    target_username=user.username,
                    details={"roles": sorted(user.groups.values_list("name", flat=True))},
                )
            messages.success(
                request,
                f"تم إنشاء حساب الموظف {user.username} وإسناد الصلاحيات المحددة.",
            )
            return redirect("store:admin_user_list")
    else:
        form = StaffAccountCreationForm()

    return render(
        request,
        "store/admin/users/form.html",
        {
            "page_title": "إنشاء حساب موظف",
            "form": form,
            "roles_available": form.fields["groups"].queryset.exists(),
        },
    )


@staff_required
def account_update(request, pk):
    """Allow CALE Super Admins to edit staff data and assigned roles."""
    if not is_cale_super_admin(request.user):
        raise PermissionDenied("هذه الصفحة متاحة لدور Super Admin فقط.")

    account = get_object_or_404(User, pk=pk, is_staff=True)
    if request.method == "POST":
        form = AccountUpdateForm(request.POST, instance=account)
        if form.is_valid():
            old_username = account.username
            old_roles = set(account.groups.filter(name__in=("Super Admin", "Product Manager", "Order Manager", "Customer Manager")).values_list("name", flat=True))
            new_roles = set(form.cleaned_data["groups"].values_list("name", flat=True))
            roles_changed = old_roles != new_roles
            if roles_changed and request.POST.get("confirm_roles") != "yes":
                form.add_error(None, "أكد تغيير الأدوار من نافذة التأكيد قبل الحفظ.")
                return render(request, "store/admin/users/edit.html", {
                    "page_title": f"تعديل الحساب: {account.username}",
                    "account": account,
                    "form": form,
                    "initial_role_ids": list(account.groups.filter(name__in=("Super Admin", "Product Manager", "Order Manager", "Customer Manager")).values_list("pk", flat=True)),
                })
            password_changed = bool(form.cleaned_data.get("password"))
            with transaction.atomic():
                if "Super Admin" in old_roles and "Super Admin" not in new_roles:
                    super_admin_group = Group.objects.select_for_update().get(name="Super Admin")
                    has_another_active_super_admin = User.objects.filter(
                        is_staff=True,
                        is_active=True,
                        groups=super_admin_group,
                    ).exclude(pk=account.pk).exists()
                    if not has_another_active_super_admin:
                        form.add_error("groups", "لا يمكن إزالة صلاحية Super Admin من آخر حساب نشط يحمل هذا الدور.")
                        return render(request, "store/admin/users/edit.html", {
                            "page_title": f"تعديل الحساب: {account.username}",
                            "account": account,
                            "form": form,
                            "initial_role_ids": list(account.groups.filter(name__in=("Super Admin", "Product Manager", "Order Manager", "Customer Manager")).values_list("pk", flat=True)),
                        })
                form.save()
                changes = {
                    "username_changed": old_username != account.username,
                    "password_changed": password_changed,
                    "roles_before": sorted(old_roles),
                    "roles_after": sorted(new_roles),
                }
                AdminAuditLog.objects.create(
                    actor=request.user,
                    action="staff_updated",
                    target_username=account.username,
                    details=changes,
                )
            messages.success(request, f"تم تحديث بيانات الحساب {account.username}.")
            return redirect("store:admin_user_list")
    else:
        form = AccountUpdateForm(instance=account)

    return render(request, "store/admin/users/edit.html", {
        "page_title": f"تعديل الحساب: {account.username}",
        "account": account,
        "form": form,
        "is_staff_account": True,
        "initial_role_ids": list(account.groups.filter(name__in=("Super Admin", "Product Manager", "Order Manager", "Customer Manager")).values_list("pk", flat=True)),
    })


@staff_required
def admin_audit_log(request):
    """Show the recent administrative account and permission changes."""
    if not is_cale_super_admin(request.user):
        raise PermissionDenied("هذه الصفحة متاحة لدور Super Admin فقط.")
    entries = AdminAuditLog.objects.select_related("actor")
    search_query = request.GET.get("q", "").strip()[:100]
    if search_query:
        entries = entries.filter(
            Q(target_username__icontains=search_query)
            | Q(actor__username__icontains=search_query)
        )
    page_obj = Paginator(entries, 50).get_page(request.GET.get("page"))
    return render(request, "store/admin/users/audit_log.html", {
        "page_title": "سجل تغييرات الإدارة",
        "entries": page_obj.object_list,
        "page_obj": page_obj,
        "search_query": search_query,
    })


@staff_required
@permission_required(
    "store.view_customer",
    raise_exception=True,
)
def customer_list(request):
    """
    Display registered customers in the custom administration panel.

    Staff users can:
    - Search by username.
    - Search by email.
    - View the number of orders for each customer.

    Staff accounts are excluded from the customer list because
    this section is intended for store customers.
    """

    search_query = request.GET.get("q", "").strip()[:100]

    customers = (
        User.objects
        .filter(is_staff=False)
        .annotate(order_count=models.Count("orders"))
        .order_by("-date_joined")
    )

    if search_query:
        customers = customers.filter(
            Q(username__icontains=search_query)
            | Q(email__icontains=search_query)
        )

    return render(
        request,
        "store/admin/customers/list.html",
        {
            "page_title": "العملاء",
            "customers": customers,
            "search_query": search_query,
        },
    )

@staff_required
@permission_required(
    "store.view_order",
    raise_exception=True,
)
def order_list(request):
    """
    Display customer orders in the custom administration panel.

    Supported filters:
        - Order status.
        - Order number.
        - Customer username.
        - Customer full name.
        - Customer phone number.

    Search and status values are received through the URL query string.

    Args:
        request: The current HTTP request.

    Returns:
        HttpResponse: The rendered order list page.
    """

    # Read search and status filters from the URL query string.
    search_query = request.GET.get("q", "").strip()[:100]
    selected_status = request.GET.get("status", "").strip()

    # Retrieve all orders with their related customer in the same query.
    orders = (
        Order.objects
        .select_related("user")
        .all()
    )

    # Build a set containing the valid database status values.
    valid_statuses = {
        value
        for value, label in Order.Status.choices
    }

    # Apply the status filter only when a valid status was supplied.
    if selected_status in valid_statuses:
        orders = orders.filter(status=selected_status)
    else:
        selected_status = ""

    # Apply text search when the administrator entered a search term.
    if search_query:
        search_filter = (
            Q(full_name__icontains=search_query)
            | Q(phone__icontains=search_query)
            | Q(user__username__icontains=search_query)
        )

        # Numeric searches can also match the order primary key.
        if search_query.isdigit():
            search_filter |= Q(pk=int(search_query))

        orders = orders.filter(search_filter)

    return render(
        request,
        "store/admin/orders/list.html",
        {
            "page_title": "الطلبات",
            "orders": orders,
            "selected_status": selected_status,
            "status_choices": Order.Status.choices,
            "search_query": search_query,
        },
    )


@staff_required
@permission_required(
    "store.view_order",
    raise_exception=True,
)
def order_detail(request, pk):
    """
    Display the complete details of one customer order.

    The customer and order items are loaded efficiently using
    ``select_related`` so the template can access their information
    without unnecessary database queries.

    The status choices displayed in the template are restricted to
    transitions allowed by the order workflow.

    Args:
        request: The current HTTP request.
        pk: Primary key of the order.

    Returns:
        HttpResponse: The rendered order detail page.

    Raises:
        Http404: If the requested order does not exist.
    """

    order = get_object_or_404(
        Order.objects.select_related("user"),
        pk=pk,
    )

    # Load each order item together with its related product.
    items = (
        order.items
        .select_related("product")
        .all()
    )

    # Calculate the total value of all items in this order.
    total = sum(
        (item.unit_price * item.quantity for item in items),
        Decimal("0.00"),
    )

    # Define the status workflow used by the order-status service.
    allowed_transitions = {
        Order.Status.NEW: {
            Order.Status.PROCESSING,
            Order.Status.CANCELLED,
        },
        Order.Status.PROCESSING: {
            Order.Status.DELIVERED,
        },
        Order.Status.DELIVERED: set(),
        Order.Status.CANCELLED: set(),
    }

    status_labels = dict(Order.Status.choices)

    # Keep the current status visible, then add only valid next statuses.
    available_statuses = [
        (order.status, status_labels[order.status]),
        *[
            (status, status_labels[status])
            for status in allowed_transitions.get(order.status, set())
        ],
    ]

    return render(
        request,
        "store/admin/orders/detail.html",
        {
            "page_title": f"تفاصيل الطلب #{order.id}",
            "order": order,
            "items": items,
            "total": total,
            "available_statuses": available_statuses,
        },
    )

@staff_required
@permission_required(
    "store.change_order",
    raise_exception=True,
)
@rate_limit(key_prefix="admin-order-status", limit=30, period=600)
def order_change_status(request, pk):
    """
    Change an order's status from the custom admin panel.

    Only POST requests are accepted because changing an order status
    modifies database records and can also modify product stock.

    The actual order-status business rules are handled by
    ``change_order_status()`` in the service layer.

    This keeps the view responsible for HTTP handling while keeping
    inventory and order-transition rules outside the view.

    Args:
        request: The current HTTP request.
        pk: Primary key of the order.

    Returns:
        HttpResponseRedirect: Redirects to the order detail page or
        order list page after processing the request.
    """

    # Status changes must never be performed through GET requests.
    if request.method != "POST":
        messages.error(
            request,
            "طريقة الطلب غير مسموحة.",
        )
        return redirect(
            "store:admin_order_detail",
            pk=pk,
        )

    new_status = request.POST.get("status")

    if not new_status:
        messages.error(
            request,
            "يرجى اختيار حالة الطلب.",
        )
        return redirect(
            "store:admin_order_detail",
            pk=pk,
        )

    try:
        # Delegate all status-transition and stock logic to the service.
        order = change_order_status(
            order_id=pk,
            new_status=new_status,
        )

    except Order.DoesNotExist:
        messages.error(
            request,
            "الطلب غير موجود.",
        )
        return redirect("store:admin_order_list")

    except ValidationError as error:
        messages.error(
            request,
            error.message,
        )
        return redirect(
            "store:admin_order_detail",
            pk=pk,
        )

    messages.success(
        request,
        f"تم تغيير حالة الطلب #{order.id} "
        f"إلى {order.get_status_display()}.",
    )

    return redirect(
        "store:admin_order_detail",
        pk=pk,
    )


@staff_required
@permission_required(
    "store.view_product",
    raise_exception=True,
)
def product_list(request):
    """
    Display products in the custom administration panel.

    Supports:
        - Searching by product name.
        - Searching by product description.
        - Filtering active products.
        - Filtering inactive products.

    Args:
        request: The current HTTP request.

    Returns:
        HttpResponse: The rendered product list page.
    """

    products = Product.objects.all()

    search_query = request.GET.get("q", "").strip()[:100]
    status_filter = request.GET.get("status", "all")

    # Search by product name or description.
    if search_query:
        products = products.filter(
            Q(name__icontains=search_query)
            | Q(description__icontains=search_query)
        )

    # Apply the requested active/inactive filter.
    if status_filter == "active":
        products = products.filter(is_active=True)

    elif status_filter == "inactive":
        products = products.filter(is_active=False)

    return render(
        request,
        "store/admin/products/list.html",
        {
            "page_title": "المنتجات",
            "products": products,
            "search_query": search_query,
            "status_filter": status_filter,
        },
    )


@staff_required
@permission_required(
    "store.add_product",
    raise_exception=True,
)
def product_create(request):
    """
    Create a new product from the custom administration panel.

    Uploaded product images are processed through the image service
    before being stored. The original high-quality upload is therefore
    converted into an optimized WebP image.

    Args:
        request: The current HTTP request.

    Returns:
        HttpResponse: The product creation form or a redirect after
        successful creation.
    """

    if request.method == "POST":
        form = ProductForm(
            request.POST,
            request.FILES,
        )

        if form.is_valid():
            product = form.save(commit=False)

            uploaded_image = form.cleaned_data.get("image")

            if uploaded_image:
                try:
                    filename, processed_image = process_uploaded_image(
                        uploaded_image,
                    )

                    product.image.save(
                        filename,
                        processed_image,
                        save=False,
                    )

                except ValidationError as error:
                    form.add_error(
                        "image",
                        error.message,
                    )

                else:
                    product.save()

                    messages.success(
                        request,
                        f'تمت إضافة المنتج "{product.name}" بنجاح.',
                    )

                    return redirect(
                        "store:admin_product_list"
                    )

            else:
                product.save()

                messages.success(
                    request,
                    f'تمت إضافة المنتج "{product.name}" بنجاح.',
                )

                return redirect(
                    "store:admin_product_list"
                )

    else:
        form = ProductForm()

    return render(
        request,
        "store/admin/products/form.html",
        {
            "page_title": "إضافة منتج",
            "form": form,
            "form_title": "إضافة منتج جديد",
            "submit_label": "إضافة المنتج",
        },
    )


@staff_required
@permission_required(
    "store.change_product",
    raise_exception=True,
)
def product_update(request, pk):
    """
    Update an existing product.

    When a new image is uploaded, it is processed through the image
    service before being stored. After the new image is successfully
    saved, the previous image file is deleted from storage.

    If no new image is uploaded, the existing image remains unchanged.

    Args:
        request: The current HTTP request.
        pk: Primary key of the product.

    Returns:
        HttpResponse: The edit form or a redirect after successful
        modification.
    """

    product = get_object_or_404(
        Product,
        pk=pk,
    )

    if request.method == "POST":
        # Keep the old image path before modifying the product.
        old_image_name = product.image.name

        form = ProductForm(
            request.POST,
            request.FILES,
            instance=product,
        )

        if form.is_valid():
            product = form.save(commit=False)

            uploaded_image = form.cleaned_data.get("image")

            if uploaded_image:
                try:
                    filename, processed_image = process_uploaded_image(
                        uploaded_image,
                    )

                    product.image.save(
                        filename,
                        processed_image,
                        save=False,
                    )

                except ValidationError as error:
                    form.add_error(
                        "image",
                        error.message,
                    )

                else:
                    product.save()

                    # Delete the old image only after the new image
                    # has been successfully saved.
                    if (
                        old_image_name
                        and old_image_name != product.image.name
                    ):
                        product.image.storage.delete(
                            old_image_name
                        )

                    messages.success(
                        request,
                        f'تم تعديل المنتج "{product.name}" بنجاح.',
                    )

                    return redirect(
                        "store:admin_product_list"
                    )

            else:
                product.save()

                messages.success(
                    request,
                    f'تم تعديل المنتج "{product.name}" بنجاح.',
                )

                return redirect(
                    "store:admin_product_list"
                )

    else:
        form = ProductForm(
            instance=product,
        )

    return render(
        request,
        "store/admin/products/form.html",
        {
            "page_title": "تعديل المنتج",
            "form": form,
            "form_title": f"تعديل: {product.name}",
            "submit_label": "حفظ التعديلات",
            "product": product,
        },
    )

@staff_required
@permission_required(
    "store.delete_product",
    raise_exception=True,
)
def product_delete(request, pk):
    """
    Display the product deletion confirmation page and delete the
    product only after a POST request.

    GET:
        Display a confirmation page.

    POST:
        Delete the product and remove its stored image if it exists.

    Args:
        request: The current HTTP request.
        pk: Primary key of the product.

    Returns:
        HttpResponse: Confirmation page or redirect after deletion.
    """

    product = get_object_or_404(
        Product,
        pk=pk,
    )

    if request.method == "POST":
        product_name = product.name

        # Keep the image reference before deleting the database record.
        image_name = product.image.name
        image_storage = product.image.storage

        product.delete()

        # Remove the physical image file after the product has been
        # successfully deleted from the database.
        if image_name and image_storage.exists(image_name):
            image_storage.delete(image_name)

        messages.success(
            request,
            f'تم حذف المنتج "{product_name}" بنجاح.',
        )

        return redirect(
            "store:admin_product_list"
        )

    return render(
        request,
        "store/admin/products/delete.html",
        {
            "page_title": "حذف المنتج",
            "product": product,
        },
    )


@staff_required
@permission_required(
    "store.change_product",
    raise_exception=True,
)
def product_toggle_status(request, pk):
    """
    Toggle the active status of a product.

    Only POST requests are accepted because the operation modifies
    database data.

    Args:
        request: The current HTTP request.
        pk: Primary key of the product.

    Returns:
        HttpResponseRedirect: Redirects to the product list.
    """

    if request.method != "POST":
        return redirect("store:admin_product_list")

    product = get_object_or_404(
        Product,
        pk=pk,
    )

    # Switch the product between active and inactive states.
    product.is_active = not product.is_active

    product.save(
        update_fields=["is_active"],
    )

    if product.is_active:
        messages.success(
            request,
            f'تم تفعيل المنتج "{product.name}".',
        )
    else:
        messages.warning(
            request,
            f'تم إيقاف المنتج "{product.name}".',
        )

    return redirect("store:admin_product_list")
