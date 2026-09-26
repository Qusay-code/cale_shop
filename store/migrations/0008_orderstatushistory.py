from django.db import migrations, models
import django.db.models.deletion


def backfill_current_status(apps, schema_editor):
    Order = apps.get_model("store", "Order")
    OrderStatusHistory = apps.get_model("store", "OrderStatusHistory")
    database = schema_editor.connection.alias

    for order in Order.objects.using(database).only("pk", "status", "updated_at").iterator():
        history = OrderStatusHistory.objects.using(database).create(
            order_id=order.pk,
            status=order.status,
        )
        OrderStatusHistory.objects.using(database).filter(pk=history.pk).update(
            created_at=order.updated_at,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("store", "0007_adminauditlog"),
    ]

    operations = [
        migrations.CreateModel(
            name="OrderStatusHistory",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("new", "جديد"),
                            ("processing", "قيد التجهيز"),
                            ("delivered", "تم التسليم"),
                            ("cancelled", "ملغي"),
                        ],
                        max_length=20,
                        verbose_name="حالة الطلب",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        verbose_name="تاريخ ووقت التحديث",
                    ),
                ),
                (
                    "order",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="status_history",
                        to="store.order",
                        verbose_name="الطلب",
                    ),
                ),
            ],
            options={
                "verbose_name": "تحديث حالة طلب",
                "verbose_name_plural": "تحديثات حالات الطلبات",
                "ordering": ["created_at", "pk"],
            },
        ),
        migrations.RunPython(backfill_current_status, migrations.RunPython.noop),
    ]
