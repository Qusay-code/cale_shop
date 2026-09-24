"""Validated forms used by the CALE Shop application.

All user-controlled text is normalized and treated as plain text. Django's
normal template auto-escaping remains the final XSS protection layer; this
module additionally rejects/strips HTML from fields that are intended to be
plain text only.
"""

from __future__ import annotations

import re
import unicodedata

from django import forms
from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm, UserCreationForm
from django.contrib.auth.models import Group, User
from django.contrib.auth.password_validation import password_validators_help_text_html, validate_password
from django.core.exceptions import ValidationError
from django.utils.html import strip_tags
from django.utils.safestring import mark_safe

from .models import CustomerProfile, Order, Product
from .security import turnstile_enabled, validate_turnstile


CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
PHONE_RE = re.compile(r"^[0-9٠-٩+()\-\s]{7,30}$")
ADMIN_ROLE_NAMES = (
    "Super Admin",
    "Product Manager",
    "Order Manager",
    "Customer Manager",
)


def clean_plain_text(value: str, *, max_length: int | None = None) -> str:
    """Normalize user text and remove HTML/control characters."""

    value = unicodedata.normalize("NFKC", value or "")
    value = strip_tags(value)
    value = CONTROL_CHARS_RE.sub("", value)
    value = " ".join(value.split())

    if max_length and len(value) > max_length:
        raise ValidationError("النص المدخل أطول من الحد المسموح.")

    return value


class TurnstileWidget(forms.Widget):
    """Render a Cloudflare Turnstile widget when configured."""

    def value_from_datadict(self, data, files, name):
        # Turnstile posts its response under this fixed field name.
        return data.get("cf-turnstile-response") or data.get(name)

    def render(self, name, value, attrs=None, renderer=None):
        if not turnstile_enabled():
            return ""

        site_key = forms.utils.flatatt({
            "data-sitekey": settings.TURNSTILE_SITE_KEY,
            "data-action": "submit",
        })
        return mark_safe(
            f'<div class="cf-turnstile"{site_key}></div>'
            '<script src="https://challenges.cloudflare.com/turnstile/v0/api.js" defer></script>'
        )


class TurnstileField(forms.CharField):
    """Server-validated Turnstile response field."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault("widget", TurnstileWidget())
        super().__init__(*args, **kwargs)

    def clean(self, value):
        value = super().clean(value)
        validate_turnstile(value)
        return value


class SecurePasswordResetForm(PasswordResetForm):
    """Password-reset form protected by the same CAPTCHA policy."""

    turnstile = TurnstileField(label="CAPTCHA")


class SecureAuthenticationForm(AuthenticationForm):
    """Authentication form with CAPTCHA verification."""

    turnstile = TurnstileField(label="CAPTCHA")


class ProductForm(forms.ModelForm):
    """Validated product-management form for staff users."""

    class Meta:
        model = Product
        fields = ["name", "description", "price", "image", "stock", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "اسم المنتج"}),
            "description": forms.Textarea(attrs={"class": "form-control", "placeholder": "وصف المنتج", "rows": 6}),
            "price": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "image": forms.ClearableFileInput(attrs={"class": "form-control", "accept": "image/jpeg,image/png,image/webp"}),
            "stock": forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-checkbox"}),
        }
        labels = {
            "name": "اسم المنتج",
            "description": "الوصف",
            "price": "السعر",
            "image": "صورة المنتج",
            "stock": "المخزون",
            "is_active": "المنتج نشط",
        }

    def clean_name(self):
        value = clean_plain_text(self.cleaned_data["name"], max_length=200)
        if len(value) < 2:
            raise ValidationError("اسم المنتج قصير جدًا.")
        return value

    def clean_description(self):
        return clean_plain_text(self.cleaned_data.get("description", ""), max_length=5000)


class CustomerRegistrationForm(UserCreationForm):
    """Secure customer registration form with a required unique email address."""

    email = forms.EmailField(
        max_length=254,
        required=True,
        label="البريد الإلكتروني",
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "أدخل البريد الإلكتروني",
                "autocomplete": "email",
                "inputmode": "email",
            }
        ),
    )
    full_name = forms.CharField(max_length=150, label="الاسم الثلاثي", widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "أدخل الاسم الثلاثي"}))
    phone = forms.CharField(max_length=30, label="رقم الهاتف", widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "أدخل رقم الهاتف"}))
    address = forms.CharField(label="العنوان", widget=forms.Textarea(attrs={"class": "form-control", "placeholder": "أدخل العنوان بالتفصيل", "rows": 3}))
    turnstile = TurnstileField(label="CAPTCHA")

    class Meta:
        model = User
        fields = ("username", "email", "full_name", "phone", "address", "password1", "password2")
        labels = {"username": "اسم المستخدم"}
        widgets = {"username": forms.TextInput(attrs={"class": "form-control", "placeholder": "أدخل اسم المستخدم", "autocomplete": "username"})}

    def clean_email(self):
        value = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise ValidationError("هذا البريد الإلكتروني مستخدم بالفعل.")
        return value

    def clean_full_name(self):
        value = clean_plain_text(self.cleaned_data["full_name"], max_length=150)
        if len(value.split()) < 2:
            raise ValidationError("يرجى إدخال الاسم بشكل صحيح.")
        return value

    def clean_phone(self):
        value = clean_plain_text(self.cleaned_data["phone"], max_length=30)
        if not PHONE_RE.fullmatch(value):
            raise ValidationError("رقم الهاتف يحتوي على أحرف أو رموز غير مسموحة.")
        return value

    def clean_address(self):
        value = clean_plain_text(self.cleaned_data["address"], max_length=1000)
        if len(value) < 5:
            raise ValidationError("يرجى إدخال عنوان صحيح.")
        return value


class StaffAccountCreationForm(forms.ModelForm):
    """Create a staff account and assign one or more approved store roles."""

    password = forms.CharField(
        label="كلمة المرور",
        strip=False,
        help_text=password_validators_help_text_html(),
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "autocomplete": "new-password"},
            render_value=False,
        ),
    )
    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.filter(name__in=ADMIN_ROLE_NAMES).order_by("name"),
        required=True,
        label="الصلاحيات",
        help_text="يمكن اختيار أكثر من دور. دور Super Admin يمنح صلاحيات لوحة CALE كاملة.",
        widget=forms.CheckboxSelectMultiple(attrs={"class": "role-options"}),
    )

    class Meta:
        model = User
        fields = ("username",)
        widgets = {
            "username": forms.TextInput(attrs={"class": "form-control", "autocomplete": "username"}),
        }
        labels = {"username": "اسم المستخدم"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.order_fields(["username", "password", "groups"])

    def clean_password(self):
        password = self.cleaned_data["password"]
        validate_password(password, User(username=self.cleaned_data.get("username", "")))
        return password

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        user.is_staff = True
        user.is_active = True
        if commit:
            user.save()
            user.groups.add(*self.cleaned_data["groups"])
        return user


class AccountUpdateForm(forms.ModelForm):
    """Edit a staff account's username, roles, and optionally its password."""

    password = forms.CharField(
        label="كلمة مرور جديدة (اختياري)",
        required=False,
        strip=False,
        help_text="اترك الحقل فارغاً للإبقاء على كلمة المرور الحالية.",
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "autocomplete": "new-password"},
            render_value=False,
        ),
    )
    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.filter(name__in=ADMIN_ROLE_NAMES).order_by("name"),
        required=True,
        label="الصلاحيات",
        help_text="اختر الأدوار التي تحدد صلاحيات هذا الموظف في لوحة CALE.",
        widget=forms.CheckboxSelectMultiple(attrs={"class": "role-options"}),
    )

    class Meta:
        model = User
        fields = ("username",)
        widgets = {
            "username": forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["groups"].initial = self.instance.groups.all()

    def clean_password(self):
        password = self.cleaned_data.get("password")
        if password:
            validate_password(password, self.instance)
        return password

    def clean_groups(self):
        groups = self.cleaned_data["groups"]
        if (
            self.instance.groups.filter(name="Super Admin").exists()
            and not groups.filter(name="Super Admin").exists()
            and not User.objects.filter(
                is_staff=True,
                is_active=True,
                groups__name="Super Admin",
            ).exclude(pk=self.instance.pk).exists()
        ):
            raise ValidationError("لا يمكن إزالة صلاحية Super Admin من آخر حساب نشط يحمل هذا الدور.")
        return groups

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get("password")
        if password:
            user.set_password(password)
        if commit:
            user.save()
            managed_roles = Group.objects.filter(name__in=ADMIN_ROLE_NAMES)
            user.groups.remove(*managed_roles)
            user.groups.add(*self.cleaned_data["groups"])
        return user

class CheckoutForm(forms.ModelForm):
    """Validated checkout form."""

    class Meta:
        model = Order
        fields = ("full_name", "phone", "address", "notes", "payment_method")
        widgets = {
            "full_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "الاسم الكامل", "readonly": True}),
            "phone": forms.TextInput(attrs={"class": "form-control", "placeholder": "رقم الهاتف"}),
            "address": forms.Textarea(attrs={"class": "form-control", "placeholder": "عنوان التوصيل", "rows": 4}),
            "notes": forms.Textarea(attrs={"class": "form-control", "placeholder": "ملاحظات إضافية (اختياري)", "rows": 3}),
            "payment_method": forms.Select(attrs={"class": "form-control"}),
        }

    def clean_full_name(self):
        value = clean_plain_text(self.cleaned_data["full_name"], max_length=200)
        if not value:
            raise ValidationError("الاسم مطلوب.")
        return value

    def clean_phone(self):
        value = clean_plain_text(self.cleaned_data["phone"], max_length=30)
        if not PHONE_RE.fullmatch(value):
            raise ValidationError("رقم الهاتف غير صالح.")
        return value

    def clean_address(self):
        value = clean_plain_text(self.cleaned_data["address"], max_length=1000)
        if len(value) < 5:
            raise ValidationError("العنوان غير صالح.")
        return value

    def clean_notes(self):
        return clean_plain_text(self.cleaned_data.get("notes", ""), max_length=2000)

    def clean_payment_method(self):
        value = self.cleaned_data["payment_method"]
        valid = {choice for choice, _ in Order.PaymentMethod.choices}
        if value not in valid:
            raise ValidationError("طريقة الدفع غير صالحة.")
        return value


class AccountProfileForm(forms.ModelForm):
    """Validated customer profile form."""

    class Meta:
        model = CustomerProfile
        fields = ("full_name", "phone", "address", "profile_image")
        widgets = {
            "full_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "أدخل الاسم الثلاثي"}),
            "phone": forms.TextInput(attrs={"class": "form-control", "placeholder": "أدخل رقم الهاتف"}),
            "address": forms.Textarea(attrs={"class": "form-control", "placeholder": "أدخل العنوان", "rows": 4}),
            "profile_image": forms.ClearableFileInput(attrs={"class": "form-control", "accept": "image/jpeg,image/png,image/webp"}),
        }
        labels = {"full_name": "الاسم الثلاثي", "phone": "رقم الهاتف", "address": "العنوان", "profile_image": "الصورة الشخصية"}

    def clean_full_name(self):
        value = clean_plain_text(self.cleaned_data["full_name"], max_length=150)
        if len(value.split()) < 2:
            raise ValidationError("يرجى إدخال الاسم بشكل صحيح.")
        return value

    def clean_phone(self):
        value = clean_plain_text(self.cleaned_data["phone"], max_length=30)
        if not PHONE_RE.fullmatch(value):
            raise ValidationError("رقم الهاتف غير صالح.")
        return value

    def clean_address(self):
        value = clean_plain_text(self.cleaned_data["address"], max_length=1000)
        if len(value) < 5:
            raise ValidationError("العنوان غير صالح.")
        return value


class AccountUsernameForm(forms.ModelForm):
    """Secure username-change form."""

    class Meta:
        model = User
        fields = ("username",)
        widgets = {"username": forms.TextInput(attrs={"class": "form-control", "placeholder": "أدخل اسم المستخدم", "autocomplete": "username"})}
        labels = {"username": "اسم المستخدم"}
