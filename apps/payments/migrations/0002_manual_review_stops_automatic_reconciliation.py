from django.db import migrations, models
from django.db.models import Q


def clear_manual_review_automatic_work(apps, schema_editor):
    payment_model = apps.get_model("payments", "Payment")
    payment_model.objects.filter(status="manual_review").update(
        next_reconciliation_at=None,
        operation_token=None,
        operation_started_at=None,
    )


class Migration(migrations.Migration):
    dependencies = [("payments", "0001_initial")]

    operations = [
        migrations.RunPython(
            clear_manual_review_automatic_work,
            migrations.RunPython.noop,
        ),
        migrations.RemoveIndex(
            model_name="payment",
            name="payments_reconcile_due_idx",
        ),
        migrations.AddIndex(
            model_name="payment",
            index=models.Index(
                condition=Q(status__in=("pending", "redirect_ready", "verifying")),
                fields=("next_reconciliation_at", "id"),
                name="payments_reconcile_due_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="payment",
            constraint=models.CheckConstraint(
                condition=(
                    ~Q(status="manual_review")
                    | Q(
                        next_reconciliation_at__isnull=True,
                        operation_token__isnull=True,
                        operation_started_at__isnull=True,
                    )
                ),
                name="payments_review_has_no_automatic_work",
            ),
        ),
    ]
