from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, close_old_connections, transaction
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.products.cache import get_catalog_cache_version
from apps.products.models import (
    FragranceNote,
    Product,
    ProductFragranceNote,
    ProductImage,
)
from apps.products.services import create_product_image_service, update_product_service
from apps.products.tests.factories import (
    FragranceNoteFactory,
    ProductFactory,
    ProductImageFactory,
)
from apps.users.models import CustomUser
from apps.users.services.signup_service import SignupIdentityConflict, create_user_service
from apps.users.services.user_auth_service import UserAuthService


pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True),
]


def test_postgresql_reports_named_product_constraints():
    invalid_product = ProductFactory.build(
        price=Decimal("100.00"),
        discount_price=Decimal("100.00"),
    )

    with pytest.raises(IntegrityError) as discount_error:
        with transaction.atomic():
            invalid_product.save(force_insert=True)

    assert (
        discount_error.value.__cause__.diag.constraint_name
        == "product_discount_lower_than_price"
    )

    invalid_volume = ProductFactory.build(volume_ml=0)
    with pytest.raises(IntegrityError) as volume_error:
        with transaction.atomic():
            invalid_volume.save(force_insert=True)

    assert (
        volume_error.value.__cause__.diag.constraint_name
        == "product_positive_volume_ml"
    )

    invalid_year = ProductFactory.build(introduction_year=1699)
    with pytest.raises(IntegrityError) as year_error:
        with transaction.atomic():
            invalid_year.save(force_insert=True)

    assert (
        year_error.value.__cause__.diag.constraint_name
        == "product_introduction_year_not_before_1700"
    )

    product = ProductFactory()
    ProductImageFactory(product=product, is_primary=True)
    with pytest.raises(IntegrityError) as primary_error:
        with transaction.atomic():
            ProductImageFactory(product=product, is_primary=True)

    assert (
        primary_error.value.__cause__.diag.constraint_name
        == "one_primary_image_per_product"
    )

    first_note = FragranceNoteFactory(name="Bergamot", slug="bergamot")
    second_note = FragranceNoteFactory(name="Lemon", slug="lemon")
    ProductFragranceNote.objects.create(
        product=product,
        fragrance_note=first_note,
        layer=ProductFragranceNote.Layer.TOP,
        position=1,
    )
    with pytest.raises(IntegrityError) as note_error:
        with transaction.atomic():
            ProductFragranceNote.objects.create(
                product=product,
                fragrance_note=first_note,
                layer=ProductFragranceNote.Layer.TOP,
                position=2,
            )
    assert (
        note_error.value.__cause__.diag.constraint_name
        == "unique_product_note_per_layer"
    )

    with pytest.raises(IntegrityError) as position_error:
        with transaction.atomic():
            ProductFragranceNote.objects.create(
                product=product,
                fragrance_note=second_note,
                layer=ProductFragranceNote.Layer.TOP,
                position=1,
            )
    assert (
        position_error.value.__cause__.diag.constraint_name
        == "unique_product_note_position"
    )


def test_postgresql_rollback_discards_rows_and_on_commit_cache_invalidation():
    initial_version = get_catalog_cache_version()
    sku = "ROLLBACK-PG-001"

    with pytest.raises(RuntimeError, match="force rollback"):
        with transaction.atomic():
            ProductFactory(sku=sku)
            raise RuntimeError("force rollback")

    assert not Product.objects.filter(sku=sku).exists()
    assert get_catalog_cache_version() == initial_version


def test_primary_image_updates_are_serialized_by_real_row_lock(mocker):
    product = ProductFactory()
    ready = Barrier(2)
    mocker.patch(
        "apps.products.services.generate_product_image_thumbnail.delay"
    )

    def create_primary(name):
        close_old_connections()
        try:
            thread_product = Product.objects.get(pk=product.pk)
            ready.wait(timeout=10)
            return create_product_image_service(
                product=thread_product,
                image_file=SimpleUploadedFile(
                    name,
                    b"threaded-image-content",
                    content_type="image/jpeg",
                ),
                is_primary=True,
                display_order=0,
            ).pk
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(create_primary, "first.jpg"),
            executor.submit(create_primary, "second.jpg"),
        ]
        created_ids = [future.result(timeout=20) for future in futures]

    assert len(set(created_ids)) == 2
    assert ProductImage.objects.filter(product=product).count() == 2
    assert ProductImage.objects.filter(
        product=product,
        is_primary=True,
    ).count() == 1


def test_fragrance_note_layer_updates_are_serialized_by_real_row_lock():
    product = ProductFactory()
    notes = [
        FragranceNoteFactory(name=name, slug=name.lower())
        for name in ("Amber", "Bergamot", "Cedar", "Davana")
    ]
    ready = Barrier(2)

    def replace_top_layer(note_pair):
        close_old_connections()
        try:
            thread_product = Product.objects.get(pk=product.pk)
            thread_notes = list(
                FragranceNote.objects.filter(pk__in=[note.pk for note in note_pair])
            )
            notes_by_id = {note.pk: note for note in thread_notes}
            ordered_notes = [notes_by_id[note.pk] for note in note_pair]
            ready.wait(timeout=10)
            update_product_service(
                product=thread_product,
                validated_data={"top_notes": ordered_notes},
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(replace_top_layer, notes[:2]),
            executor.submit(replace_top_layer, notes[2:]),
        ]
        for future in futures:
            future.result(timeout=20)

    persisted = list(
        ProductFragranceNote.objects.filter(
            product=product,
            layer=ProductFragranceNote.Layer.TOP,
        )
        .order_by("position")
        .values_list("fragrance_note__name", flat=True)
    )
    assert persisted in (["Amber", "Bergamot"], ["Cedar", "Davana"])


def test_postgresql_enforces_casefold_identity_constraints():
    CustomUser.objects.create(
        username="CaseFoldCustomer",
        email="CaseFold@example.com",
        password="!",
    )

    with pytest.raises(IntegrityError) as username_error:
        with transaction.atomic():
            CustomUser.objects.create(
                username="casefoldcustomer",
                email="other@example.com",
                password="!",
            )
    assert username_error.value.__cause__.diag.constraint_name == "users_unique_username_casefold"

    with pytest.raises(IntegrityError) as email_error:
        with transaction.atomic():
            CustomUser.objects.create(
                username="other_customer",
                email="casefold@example.com",
                password="!",
            )
    assert email_error.value.__cause__.diag.constraint_name == "users_unique_email_casefold"


def test_casefold_signup_race_allows_only_one_identity():
    ready = Barrier(2)

    def signup(username):
        close_old_connections()
        try:
            ready.wait(timeout=10)
            create_user_service(
                data={"username": username, "password": "StrongPassword123!"},
            )
            return "created"
        except SignupIdentityConflict:
            return "conflict"
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = [
            executor.submit(signup, username)
            for username in ("RacingUser", "racinguser")
        ]
        results = [outcome.result(timeout=20) for outcome in outcomes]

    assert sorted(results) == ["conflict", "created"]
    assert CustomUser.objects.filter(username__iexact="racinguser").count() == 1


def test_postgresql_password_change_blacklists_existing_refresh_tokens():
    user = CustomUser.objects.create_user(
        username="token_state_customer",
        password="OriginalPassword123!",
    )
    refresh = RefreshToken.for_user(user)

    UserAuthService.update_user_profile(
        user=user,
        validated_data={"password": "ReplacementPassword123!"},
    )

    assert BlacklistedToken.objects.filter(token__jti=refresh["jti"]).exists()
