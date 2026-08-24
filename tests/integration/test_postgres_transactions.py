from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from queue import Queue
from threading import (
    Barrier,
    BrokenBarrierError,
    Event,
    current_thread,
    main_thread,
)
from time import monotonic
from uuid import UUID

import pytest
from django.contrib import admin
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.files.storage import FileSystemStorage
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.db.models.query import QuerySet
from django.test import RequestFactory
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.products.cache import get_catalog_cache_version
from apps.products.models import (
    FragranceNote,
    Product,
    ProductFragranceNote,
    ProductImage,
)
from apps.products.services import (
    create_product_image_service,
    delete_product_image_service,
    update_product_service,
)
from apps.products.selectors import get_product_detail, get_product_image_by_id
from apps.products.tasks import generate_product_image_thumbnail
from apps.products.tests.factories import (
    FragranceNoteFactory,
    ProductFactory,
    ProductImageFactory,
)
from apps.users.models import CustomUser
from apps.users.services.signup_service import SignupIdentityConflict, create_user_service
from apps.users.services.user_auth_service import UserAuthService
from apps.users.tests.factories import AddressFactory, UserFactory


pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True),
]


def _wait_until_postgres_backend_is_blocked_on_lock(*, backend_pid: int) -> None:
    deadline = monotonic() + 10
    with connection.cursor() as cursor:
        while monotonic() < deadline:
            cursor.execute(
                "SELECT wait_event_type FROM pg_stat_activity WHERE pid = %s",
                [backend_pid],
            )
            row = cursor.fetchone()
            if row and row[0] == "Lock":
                return

    raise AssertionError(
        f"PostgreSQL backend {backend_pid} did not block on a row lock"
    )


def _wait_for_backend_to_finish_or_block(
    *,
    backend_pid: int,
    finished: Event,
) -> str:
    deadline = monotonic() + 10
    with connection.cursor() as cursor:
        while monotonic() < deadline:
            if finished.is_set():
                return "finished"
            cursor.execute(
                "SELECT wait_event_type FROM pg_stat_activity WHERE pid = %s",
                [backend_pid],
            )
            row = cursor.fetchone()
            if row and row[0] == "Lock":
                return "blocked"

    raise AssertionError(
        f"PostgreSQL backend {backend_pid} neither finished nor blocked"
    )


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


def test_address_admin_superuser_save_locks_owners_before_address():
    intended_owner = UserFactory(id=UUID(int=1))
    current_owner = UserFactory(id=UUID(int=2))
    address = AddressFactory(user=current_owner)
    superuser = UserFactory(is_staff=True, is_superuser=True)
    ordinary_staff = UserFactory(is_staff=True, is_superuser=False)
    owner_locked = Event()
    release_owner = Event()
    ordinary_finished = Event()
    superuser_backend_pid = Queue()
    ordinary_backend_pid = Queue()

    def block_intended_owner():
        close_old_connections()
        try:
            with transaction.atomic():
                CustomUser.objects.select_for_update().get(pk=intended_owner.pk)
                owner_locked.set()
                if not release_owner.wait(timeout=10):
                    raise TimeoutError("owner lock was not released")
            return None
        except Exception as exc:
            return exc
        finally:
            close_old_connections()

    def reassign_as_superuser():
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                superuser_backend_pid.put(cursor.fetchone()[0])
            request = RequestFactory().post("/admin/users/address/")
            request.user = CustomUser.objects.get(pk=superuser.pk)
            thread_address = address.__class__.objects.get(pk=address.pk)
            thread_address.user_id = intended_owner.pk
            admin.site._registry[address.__class__].save_model(
                request,
                thread_address,
                form=None,
                change=True,
            )
            return None
        except Exception as exc:
            return exc
        finally:
            close_old_connections()

    def update_as_ordinary_staff():
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                ordinary_backend_pid.put(cursor.fetchone()[0])
            request = RequestFactory().post("/admin/users/address/")
            request.user = CustomUser.objects.get(pk=ordinary_staff.pk)
            thread_address = address.__class__.objects.get(pk=address.pk)
            thread_address.title = "Concurrent customer update"
            admin.site._registry[address.__class__].save_model(
                request,
                thread_address,
                form=None,
                change=True,
            )
            return None
        except Exception as exc:
            return exc
        finally:
            ordinary_finished.set()
            close_old_connections()

    with ThreadPoolExecutor(max_workers=3) as executor:
        blocker_future = executor.submit(block_intended_owner)
        assert owner_locked.wait(timeout=10)
        superuser_future = executor.submit(reassign_as_superuser)
        backend_pid = superuser_backend_pid.get(timeout=10)
        _wait_until_postgres_backend_is_blocked_on_lock(backend_pid=backend_pid)
        ordinary_future = executor.submit(update_as_ordinary_staff)
        ordinary_pid = ordinary_backend_pid.get(timeout=10)
        ordinary_outcome = _wait_for_backend_to_finish_or_block(
            backend_pid=ordinary_pid,
            finished=ordinary_finished,
        )
        release_owner.set()
        blocker_error = blocker_future.result(timeout=20)
        superuser_error = superuser_future.result(timeout=20)
        ordinary_error = ordinary_future.result(timeout=20)

    assert ordinary_outcome == "finished"
    assert blocker_error is None
    assert superuser_error is None
    assert ordinary_error is None


def test_thumbnail_redeliveries_are_serialized_by_real_row_lock(mocker):
    product_image = ProductImageFactory()
    reads_ready = Barrier(2)
    original_get = QuerySet.get

    def synchronize_product_image_reads(queryset, *args, **kwargs):
        result = original_get(queryset, *args, **kwargs)
        if (
            current_thread() is not main_thread()
            and queryset.model is ProductImage
            and kwargs.get("pk") == product_image.pk
        ):
            try:
                reads_ready.wait(timeout=1)
            except BrokenBarrierError:
                pass
        return result

    mocker.patch.object(QuerySet, "get", synchronize_product_image_reads)
    thumbnail_storage = product_image.thumbnail.storage
    storage_save = mocker.spy(thumbnail_storage, "save")

    def generate_thumbnail():
        close_old_connections()
        try:
            generate_product_image_thumbnail.run.__wrapped__(product_image.pk)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(generate_thumbnail) for _ in range(2)]
        for future in futures:
            future.result(timeout=20)

    product_image.refresh_from_db()
    _, thumbnail_files = thumbnail_storage.listdir(
        f"products/thumbnails/by-image-id/{product_image.pk}"
    )
    assert storage_save.call_count == 1
    assert thumbnail_files == ["thumbnail.webp"]


def test_thumbnail_generation_and_image_delete_share_the_same_row_lock(mocker):
    stale_product_image = ProductImageFactory()
    storage = stale_product_image.image.storage
    original_name = stale_product_image.image.name
    task_reached_storage = Event()
    allow_storage_save = Event()
    delete_lock_query_started = Event()
    delete_lock_query_returned = Event()
    delete_backend_pid = Queue()
    delete_thread = {}
    storage_save = storage.save
    original_get = QuerySet.get

    def observe_delete_lock_query(queryset, *args, **kwargs):
        is_target_delete_lock = (
            current_thread() is delete_thread.get("value")
            and queryset.model is ProductImage
            and queryset.query.select_for_update
            and kwargs.get("pk") == stale_product_image.pk
        )
        if not is_target_delete_lock:
            return original_get(queryset, *args, **kwargs)

        delete_lock_query_started.set()
        try:
            return original_get(queryset, *args, **kwargs)
        finally:
            delete_lock_query_returned.set()

    def block_thumbnail_save(name, content, max_length=None):
        task_reached_storage.set()
        if not allow_storage_save.wait(timeout=10):
            raise TimeoutError("thumbnail save was not released")
        return storage_save(name, content, max_length=max_length)

    mocker.patch.object(storage, "save", side_effect=block_thumbnail_save)
    mocker.patch.object(QuerySet, "get", observe_delete_lock_query)

    def generate_thumbnail():
        close_old_connections()
        try:
            generate_product_image_thumbnail.run.__wrapped__(stale_product_image.pk)
        finally:
            close_old_connections()

    def delete_image():
        close_old_connections()
        try:
            delete_thread["value"] = current_thread()
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                delete_backend_pid.put(cursor.fetchone()[0])
            delete_product_image_service(product_image=stale_product_image)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        thumbnail_future = executor.submit(generate_thumbnail)
        assert task_reached_storage.wait(timeout=10)
        delete_future = executor.submit(delete_image)
        try:
            backend_pid = delete_backend_pid.get(timeout=10)
            assert delete_lock_query_started.wait(timeout=10)
            _wait_until_postgres_backend_is_blocked_on_lock(
                backend_pid=backend_pid
            )
            assert delete_lock_query_returned.is_set() is False
        finally:
            allow_storage_save.set()
        thumbnail_future.result(timeout=20)
        delete_future.result(timeout=20)

    assert not ProductImage.objects.filter(pk=stale_product_image.pk).exists()
    assert storage.exists(original_name) is False
    assert storage.exists(
        "products/thumbnails/by-image-id/"
        f"{stale_product_image.pk}/thumbnail.webp"
    ) is False


def test_failed_thumbnail_cleanup_keeps_row_lock_during_waiting_redelivery(
    mocker,
):
    product_image = ProductImageFactory()
    storage = product_image.thumbnail.storage
    original_delete = storage.delete
    original_get = QuerySet.get
    original_save = ProductImage.save
    cleanup_started = Event()
    allow_cleanup = Event()
    redelivery_lock_query_started = Event()
    redelivery_backend_pid = Queue()
    task_threads = {}

    def fail_first_thumbnail_database_save(instance, *args, **kwargs):
        if (
            current_thread() is task_threads.get("failing")
            and kwargs.get("update_fields") == ["thumbnail", "updated_at"]
        ):
            raise RuntimeError("simulated database failure")
        return original_save(instance, *args, **kwargs)

    def block_failed_thumbnail_cleanup(name):
        if current_thread() is task_threads.get("failing"):
            cleanup_started.set()
            if not allow_cleanup.wait(timeout=20):
                raise TimeoutError("failed thumbnail cleanup was not released")
        return original_delete(name)

    def observe_redelivery_lock_query(queryset, *args, **kwargs):
        if (
            current_thread() is task_threads.get("redelivery")
            and queryset.model is ProductImage
            and queryset.query.select_for_update
            and kwargs.get("pk") == product_image.pk
        ):
            redelivery_lock_query_started.set()
        return original_get(queryset, *args, **kwargs)

    mocker.patch.object(ProductImage, "save", fail_first_thumbnail_database_save)
    mocker.patch.object(storage, "delete", side_effect=block_failed_thumbnail_cleanup)
    mocker.patch.object(QuerySet, "get", observe_redelivery_lock_query)

    def fail_thumbnail_generation():
        close_old_connections()
        try:
            task_threads["failing"] = current_thread()
            generate_product_image_thumbnail.run.__wrapped__(product_image.pk)
        finally:
            close_old_connections()

    def redeliver_thumbnail_generation():
        close_old_connections()
        try:
            task_threads["redelivery"] = current_thread()
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                redelivery_backend_pid.put(cursor.fetchone()[0])
            generate_product_image_thumbnail.run.__wrapped__(product_image.pk)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        failed_future = executor.submit(fail_thumbnail_generation)
        assert cleanup_started.wait(timeout=10)
        redelivery_future = executor.submit(redeliver_thumbnail_generation)
        try:
            backend_pid = redelivery_backend_pid.get(timeout=10)
            assert redelivery_lock_query_started.wait(timeout=10)
            _wait_until_postgres_backend_is_blocked_on_lock(
                backend_pid=backend_pid
            )
        finally:
            allow_cleanup.set()

        with pytest.raises(RuntimeError, match="database failure"):
            failed_future.result(timeout=20)
        redelivery_future.result(timeout=20)

    product_image.refresh_from_db()
    assert storage.exists(product_image.thumbnail.name)


def test_failed_original_cleanup_cannot_delete_concurrent_valid_upload(
    mocker,
    tmp_path,
):
    image_field = ProductImage._meta.get_field("image")
    overwrite_storage = FileSystemStorage(
        location=tmp_path / "overwrite-storage",
        allow_overwrite=True,
    )
    mocker.patch.object(image_field, "storage", overwrite_storage)
    mocker.patch("apps.products.services.generate_product_image_thumbnail.delay")
    original_save = ProductImage.save
    original_delete = overwrite_storage.delete
    uploads_started = Barrier(2)
    successful_row_uncommitted = Event()
    allow_successful_commit = Event()
    failed_cleanup_started = Event()
    allow_failed_cleanup = Event()
    upload_threads = {}

    def control_database_saves(instance, *args, **kwargs):
        result = original_save(instance, *args, **kwargs)
        if current_thread() is upload_threads.get("failing"):
            if not successful_row_uncommitted.wait(timeout=10):
                raise TimeoutError("successful upload never wrote its row")
            raise RuntimeError("simulated database failure")
        if current_thread() is upload_threads.get("successful"):
            successful_row_uncommitted.set()
            if not allow_successful_commit.wait(timeout=10):
                raise TimeoutError("successful upload commit was not released")
        return result

    def block_failed_cleanup(name):
        if current_thread() is upload_threads.get("failing"):
            failed_cleanup_started.set()
            if not allow_failed_cleanup.wait(timeout=10):
                raise TimeoutError("failed original cleanup was not released")
        return original_delete(name)

    mocker.patch.object(ProductImage, "save", control_database_saves)
    mocker.patch.object(
        overwrite_storage,
        "delete",
        side_effect=block_failed_cleanup,
    )

    failing_product = ProductFactory()
    successful_product = ProductFactory()

    def upload(*, role, product, content):
        close_old_connections()
        try:
            upload_threads[role] = current_thread()
            uploads_started.wait(timeout=10)
            return create_product_image_service(
                product=product,
                image_file=SimpleUploadedFile(
                    "shared-name.jpg",
                    content,
                    content_type="image/jpeg",
                ),
                is_primary=False,
                display_order=0,
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        failed_future = executor.submit(
            upload,
            role="failing",
            product=failing_product,
            content=b"failed upload",
        )
        successful_future = executor.submit(
            upload,
            role="successful",
            product=successful_product,
            content=b"successful upload",
        )
        assert failed_cleanup_started.wait(timeout=10)
        allow_successful_commit.set()
        successful_image = successful_future.result(timeout=20)
        allow_failed_cleanup.set()
        with pytest.raises(RuntimeError, match="database failure"):
            failed_future.result(timeout=20)

    successful_image.refresh_from_db()
    assert successful_image.image.storage.exists(successful_image.image.name)


def test_concurrent_product_deletes_preserve_204_then_404_contract(mocker):
    product_image = ProductImageFactory()
    product = product_image.product
    product_image.thumbnail.save(
        "concurrent-product-delete.webp",
        ContentFile(b"thumbnail"),
        save=True,
    )
    storage = product_image.image.storage
    image_names = [product_image.image.name, product_image.thumbnail.name]
    admin_user = UserFactory(is_staff=True, is_superuser=True)
    url = reverse(
        "apps.products:product-detail",
        kwargs={"product_slug": product.slug},
    )
    both_requests_resolved = Barrier(2)

    def synchronize_resolved_products(*, product_slug, include_inactive=False):
        resolved_product = get_product_detail(
            product_slug=product_slug,
            include_inactive=include_inactive,
        )
        both_requests_resolved.wait(timeout=10)
        return resolved_product

    mocker.patch(
        "apps.products.views.get_product_detail",
        side_effect=synchronize_resolved_products,
    )

    def delete_product():
        close_old_connections()
        try:
            client = APIClient()
            client.force_authenticate(user=admin_user)
            return client.delete(url).status_code
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(delete_product) for _ in range(2)]
        response_statuses = [future.result(timeout=20) for future in futures]

    assert sorted(response_statuses) == [
        status.HTTP_204_NO_CONTENT,
        status.HTTP_404_NOT_FOUND,
    ]
    assert Product.objects.filter(pk=product.pk).exists() is False
    assert all(storage.exists(name) is False for name in image_names)


def test_concurrent_product_image_deletes_preserve_204_then_404_contract(mocker):
    product_image = ProductImageFactory()
    product_image.thumbnail.save(
        "concurrent-image-delete.webp",
        ContentFile(b"thumbnail"),
        save=True,
    )
    storage = product_image.image.storage
    image_names = [product_image.image.name, product_image.thumbnail.name]
    admin_user = UserFactory(is_staff=True, is_superuser=True)
    url = reverse(
        "apps.products:product-image-delete",
        kwargs={"image_id": product_image.pk},
    )
    both_requests_resolved = Barrier(2)

    def synchronize_resolved_images(*, image_id):
        resolved_image = get_product_image_by_id(image_id=image_id)
        both_requests_resolved.wait(timeout=10)
        return resolved_image

    mocker.patch(
        "apps.products.views.get_product_image_by_id",
        side_effect=synchronize_resolved_images,
    )

    def delete_product_image():
        close_old_connections()
        try:
            client = APIClient()
            client.force_authenticate(user=admin_user)
            return client.delete(url).status_code
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(delete_product_image) for _ in range(2)]
        response_statuses = [future.result(timeout=20) for future in futures]

    assert sorted(response_statuses) == [
        status.HTTP_204_NO_CONTENT,
        status.HTTP_404_NOT_FOUND,
    ]
    assert ProductImage.objects.filter(pk=product_image.pk).exists() is False
    assert all(storage.exists(name) is False for name in image_names)


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
