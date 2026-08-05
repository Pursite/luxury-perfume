from django.db import migrations, models
from django.db.models import Count
from django.db.models.functions import Lower, Trim
import django.core.validators


def reject_case_insensitive_identity_conflicts(apps, schema_editor):
    """Refuse the schema change until operators resolve legacy conflicts."""
    CustomUser = apps.get_model("users", "CustomUser")
    conflicting_fields = []
    for field_name in ("username", "email"):
        has_conflict = (
            CustomUser.objects.exclude(**{f"{field_name}__isnull": True})
            .exclude(**{field_name: ""})
            .annotate(normalized_identity=Lower(Trim(field_name)))
            .values("normalized_identity")
            .annotate(identity_count=Count("pk"))
            .filter(identity_count__gt=1)
            .exists()
        )
        if has_conflict:
            conflicting_fields.append(field_name)

    if conflicting_fields:
        fields = ", ".join(conflicting_fields)
        raise RuntimeError(
            "Cannot add case-insensitive identity constraints because "
            f"case-insensitive identity conflicts exist for: {fields}. "
            "Resolve the conflicting records privately before retrying the migration."
        )


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0004_customuser_users_active_user_requires_identity"),
    ]

    operations = [
        migrations.RunPython(
            reject_case_insensitive_identity_conflicts,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="customuser",
            name="email",
            field=models.EmailField(blank=True, max_length=254, null=True),
        ),
        migrations.AlterField(
            model_name="customuser",
            name="phone_number",
            field=models.CharField(
                blank=True,
                max_length=11,
                null=True,
                unique=True,
                validators=[
                    django.core.validators.RegexValidator(
                        message="Phone number must be entered in the format: '0912345678'.",
                        regex=r"^09[0-9]{9}$",
                    ),
                ],
            ),
        ),
        migrations.AlterField(
            model_name="customuser",
            name="username",
            field=models.CharField(blank=True, max_length=150, null=True),
        ),
        migrations.AddConstraint(
            model_name="customuser",
            constraint=models.UniqueConstraint(
                Lower("username"),
                condition=models.Q(("username__isnull", False), models.Q(("username", ""), _negated=True)),
                name="users_unique_username_casefold",
            ),
        ),
        migrations.AddConstraint(
            model_name="customuser",
            constraint=models.UniqueConstraint(
                Lower("email"),
                condition=models.Q(("email__isnull", False), models.Q(("email", ""), _negated=True)),
                name="users_unique_email_casefold",
            ),
        ),
    ]
