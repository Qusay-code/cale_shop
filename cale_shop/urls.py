from django.contrib import admin
from django.contrib.auth.views import PasswordResetDoneView, PasswordResetConfirmView, PasswordResetCompleteView
from django.urls import include, path, reverse_lazy
from django.conf import settings
from django.conf.urls.static import static

from store.views import RoleBasedLoginView, SecurePasswordResetView


urlpatterns = [
    path("django-admin/", admin.site.urls),

    # Custom login
    path(
        "login/",
        RoleBasedLoginView.as_view(),
        name="login",
    ),


    path(
        "password-reset/",
        SecurePasswordResetView.as_view(),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        PasswordResetDoneView.as_view(
            template_name="registration/password_reset_done.html"
        ),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        PasswordResetConfirmView.as_view(
            template_name="registration/password_reset_confirm.html",
            success_url=reverse_lazy("password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        PasswordResetCompleteView.as_view(
            template_name="registration/password_reset_complete.html"
        ),
        name="password_reset_complete",
    ),

    # Store URLs MUST come before Django auth URLs.
    path(
        "",
        include("store.urls"),
    ),

]


if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT,
    )