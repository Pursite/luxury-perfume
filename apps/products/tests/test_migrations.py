from decimal import Decimal

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_ordered_note_migration_preserves_membership_and_observable_order():
    old_target = [
        (
            "products",
            "0003_fragrancenote_remove_product_abv_remove_product_ibu_and_more",
        )
    ]
    new_target = [("products", "0004_ordered_fragrance_notes")]
    executor = MigrationExecutor(connection)
    executor.migrate(old_target)
    old_apps = executor.loader.project_state(old_target).apps
    LegacyCategory = old_apps.get_model("products", "Category")
    LegacyFragranceNote = old_apps.get_model("products", "FragranceNote")
    LegacyProduct = old_apps.get_model("products", "Product")
    category = LegacyCategory.objects.create(name="Perfume", slug="perfume")
    product = LegacyProduct.objects.create(
        category=category,
        name="Migration fragrance",
        slug="migration-fragrance",
        sku="MIGRATION-001",
        description="Migration fixture",
        price=Decimal("100.00"),
        volume_ml=100,
        concentration="body_splash",
    )
    zesty = LegacyFragranceNote.objects.create(name="Zesty Lemon", slug="zesty-lemon")
    amber = LegacyFragranceNote.objects.create(name="Amber", slug="amber")
    product.top_notes.add(zesty, amber)
    product.middle_notes.add(zesty)

    try:
        executor = MigrationExecutor(connection)
        executor.migrate(new_target)
        new_apps = executor.loader.project_state(new_target).apps
        MigratedProduct = new_apps.get_model("products", "Product")
        ProductFragranceNote = new_apps.get_model(
            "products",
            "ProductFragranceNote",
        )

        assert list(
            ProductFragranceNote.objects.filter(product_id=product.pk, layer="top")
            .order_by("position")
            .values_list("position", "fragrance_note__name")
        ) == [(1, "Amber"), (2, "Zesty Lemon")]
        assert list(
            ProductFragranceNote.objects.filter(product_id=product.pk, layer="middle")
            .values_list("position", "fragrance_note_id")
        ) == [(1, zesty.pk)]
        assert (
            MigratedProduct.objects.get(pk=product.pk).concentration == "unspecified"
        )

        executor = MigrationExecutor(connection)
        executor.migrate(old_target)
        restored_apps = executor.loader.project_state(old_target).apps
        RestoredProduct = restored_apps.get_model("products", "Product")
        restored = RestoredProduct.objects.get(pk=product.pk)
        assert list(restored.top_notes.order_by("name").values_list("name", flat=True)) == [
            "Amber",
            "Zesty Lemon",
        ]
        assert list(restored.middle_notes.values_list("id", flat=True)) == [zesty.pk]
    finally:
        MigrationExecutor(connection).migrate(new_target)
