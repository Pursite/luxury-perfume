from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework import status

from apps.cart.models import Cart, CartItem
from apps.cart.tests.factories import CartFactory, CartItemFactory
from apps.products.models import ProductImage
from apps.products.tests.factories import ProductFactory
from apps.users.tests.factories import UserFactory


pytestmark = pytest.mark.django_db


def _cart_url():
    return reverse("apps.cart:cart-detail")


def _item_list_url():
    return reverse("apps.cart:cart-item-list")


def _item_detail_url(product):
    return reverse(
        "apps.cart:cart-item-detail",
        kwargs={"product_slug": product.slug},
    )


@pytest.mark.parametrize(
    ("method", "url_factory", "body"),
    [
        ("get", _cart_url, None),
        ("delete", _cart_url, None),
        (
            "post",
            _item_list_url,
            {"product_slug": "missing-product", "quantity": 1},
        ),
    ],
)
def test_cart_endpoints_require_authentication(api_client, method, url_factory, body):
    response = getattr(api_client, method)(url_factory(), body, format="json")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_item_detail_endpoints_require_authentication(api_client):
    product = ProductFactory()
    url = _item_detail_url(product)

    assert api_client.patch(url, {"quantity": 1}, format="json").status_code == 401
    assert api_client.delete(url).status_code == 401


def test_get_empty_cart_does_not_create_cart(api_client):
    user = UserFactory()
    api_client.force_authenticate(user=user)

    response = api_client.get(_cart_url())

    assert response.status_code == status.HTTP_200_OK
    assert response.data == {
        "items": [],
        "total_quantity": 0,
        "total_price": "0.00",
        "has_unavailable_items": False,
    }
    assert Cart.objects.filter(user=user).exists() is False
    assert user.is_profile_complete is False


def test_add_returns_created_full_cart(api_client):
    user = UserFactory()
    product = ProductFactory(
        price=Decimal("100.00"),
        discount_price=Decimal("80.00"),
        stock=5,
    )
    api_client.force_authenticate(user=user)

    response = api_client.post(
        _item_list_url(),
        {"product_slug": product.slug, "quantity": 2},
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["total_quantity"] == 2
    assert response.data["total_price"] == "160.00"
    assert response.data["has_unavailable_items"] is False
    assert response.data["items"] == [
        {
            "product": {
                "uuid": str(product.uuid),
                "slug": product.slug,
                "name": product.name,
                "primary_image": None,
            },
            "quantity": 2,
            "unit_price": "80.00",
            "line_total": "160.00",
            "available_stock": 5,
            "available": True,
        }
    ]


def test_repeated_post_increments_and_returns_ok(api_client):
    item = CartItemFactory(quantity=2, product__stock=10)
    api_client.force_authenticate(user=item.cart.user)

    response = api_client.post(
        _item_list_url(),
        {"product_slug": item.product.slug, "quantity": 3},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["items"][0]["quantity"] == 5


def test_patch_sets_absolute_quantity(api_client):
    item = CartItemFactory(quantity=2, product__stock=10)
    api_client.force_authenticate(user=item.cart.user)

    response = api_client.patch(
        _item_detail_url(item.product),
        {"quantity": 4},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["items"][0]["quantity"] == 4
    assert CartItem.objects.get(pk=item.pk).quantity == 4


def test_item_delete_returns_no_content_and_retains_cart(api_client):
    item = CartItemFactory()
    api_client.force_authenticate(user=item.cart.user)

    response = api_client.delete(_item_detail_url(item.product))

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert response.data is None
    assert Cart.objects.filter(pk=item.cart_id).exists() is True
    assert CartItem.objects.filter(pk=item.pk).exists() is False


def test_clear_returns_no_content_and_retains_existing_cart(api_client):
    cart = CartFactory()
    CartItemFactory(cart=cart)
    CartItemFactory(cart=cart)
    api_client.force_authenticate(user=cart.user)

    response = api_client.delete(_cart_url())

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert response.data is None
    assert Cart.objects.filter(pk=cart.pk).exists() is True
    assert cart.items.exists() is False


def test_clear_missing_cart_returns_no_content_without_creating_one(api_client):
    user = UserFactory()
    api_client.force_authenticate(user=user)

    response = api_client.delete(_cart_url())

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert Cart.objects.filter(user=user).exists() is False


def test_get_and_item_mutations_are_isolated_by_owner(api_client):
    product = ProductFactory(stock=10)
    owned = CartItemFactory(product=product, quantity=2)
    other_user = UserFactory()
    api_client.force_authenticate(user=other_user)

    get_response = api_client.get(_cart_url())
    patch_response = api_client.patch(
        _item_detail_url(product),
        {"quantity": 1},
        format="json",
    )
    delete_response = api_client.delete(_item_detail_url(product))

    assert get_response.data["items"] == []
    assert patch_response.status_code == status.HTTP_404_NOT_FOUND
    assert delete_response.status_code == status.HTTP_404_NOT_FOUND
    assert CartItem.objects.get(pk=owned.pk).quantity == 2


@pytest.mark.parametrize("quantity", [0, -1])
def test_add_and_patch_reject_nonpositive_quantity(api_client, quantity):
    item = CartItemFactory(product__stock=10)
    api_client.force_authenticate(user=item.cart.user)

    add_response = api_client.post(
        _item_list_url(),
        {"product_slug": item.product.slug, "quantity": quantity},
        format="json",
    )
    patch_response = api_client.patch(
        _item_detail_url(item.product),
        {"quantity": quantity},
        format="json",
    )

    assert add_response.status_code == status.HTTP_400_BAD_REQUEST
    assert patch_response.status_code == status.HTTP_400_BAD_REQUEST
    assert "quantity" in add_response.data
    assert "quantity" in patch_response.data


def test_add_treats_missing_and_inactive_products_as_not_found(api_client):
    user = UserFactory()
    inactive = ProductFactory(is_active=False)
    api_client.force_authenticate(user=user)

    missing_response = api_client.post(
        _item_list_url(),
        {"product_slug": "missing-product", "quantity": 1},
        format="json",
    )
    inactive_response = api_client.post(
        _item_list_url(),
        {"product_slug": inactive.slug, "quantity": 1},
        format="json",
    )

    assert missing_response.status_code == status.HTTP_404_NOT_FOUND
    assert inactive_response.status_code == status.HTTP_404_NOT_FOUND
    assert Cart.objects.filter(user=user).exists() is False


@pytest.mark.parametrize(
    ("method", "existing_quantity", "submitted_quantity", "stock"),
    [("post", 2, 2, 3), ("patch", 2, 4, 3)],
)
def test_mutations_reject_current_stock_excess_without_partial_write(
    api_client,
    method,
    existing_quantity,
    submitted_quantity,
    stock,
):
    item = CartItemFactory(quantity=existing_quantity, product__stock=stock)
    api_client.force_authenticate(user=item.cart.user)
    url = _item_list_url() if method == "post" else _item_detail_url(item.product)
    payload = {"quantity": submitted_quantity}
    if method == "post":
        payload["product_slug"] = item.product.slug

    response = getattr(api_client, method)(url, payload, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert str(response.data["quantity"][0]) == (
        "Requested quantity exceeds available stock."
    )
    assert CartItem.objects.get(pk=item.pk).quantity == existing_quantity


def test_get_reflects_live_price_discount_stock_and_activity(api_client):
    item = CartItemFactory(
        quantity=2,
        product__price=Decimal("100.00"),
        product__discount_price=Decimal("80.00"),
        product__stock=5,
        product__is_active=True,
    )
    api_client.force_authenticate(user=item.cart.user)

    initial = api_client.get(_cart_url())
    assert initial.data["items"][0]["unit_price"] == "80.00"
    assert initial.data["items"][0]["available"] is True

    product = item.product
    product.discount_price = None
    product.price = Decimal("120.00")
    product.stock = 1
    product.save(update_fields=("discount_price", "price", "stock", "updated_at"))

    reduced = api_client.get(_cart_url())
    assert reduced.data["items"][0]["quantity"] == 2
    assert reduced.data["items"][0]["unit_price"] == "120.00"
    assert reduced.data["items"][0]["line_total"] == "240.00"
    assert reduced.data["items"][0]["available_stock"] == 1
    assert reduced.data["items"][0]["available"] is False

    product.stock = 0
    product.is_active = False
    product.discount_price = Decimal("90.00")
    product.save(
        update_fields=("stock", "is_active", "discount_price", "updated_at")
    )

    unavailable = api_client.get(_cart_url())
    assert unavailable.data["items"][0]["quantity"] == 2
    assert unavailable.data["items"][0]["unit_price"] == "90.00"
    assert unavailable.data["items"][0]["available_stock"] == 0
    assert unavailable.data["items"][0]["available"] is False


def test_totals_include_unavailable_items_at_current_prices(api_client):
    cart = CartFactory()
    CartItemFactory(
        cart=cart,
        quantity=2,
        product__price=Decimal("10.00"),
        product__discount_price=None,
        product__stock=2,
    )
    CartItemFactory(
        cart=cart,
        quantity=3,
        product__price=Decimal("5.00"),
        product__discount_price=None,
        product__stock=0,
    )
    api_client.force_authenticate(user=cart.user)

    response = api_client.get(_cart_url())

    assert response.data["total_quantity"] == 5
    assert response.data["total_price"] == "35.00"
    assert response.data["has_unavailable_items"] is True


def test_primary_image_prefers_marked_image_over_display_order(api_client):
    item = CartItemFactory()
    ProductImage.objects.create(
        product=item.product,
        image="products/first.jpg",
        display_order=0,
        is_primary=False,
    )
    primary = ProductImage.objects.create(
        product=item.product,
        image="products/primary.jpg",
        display_order=2,
        is_primary=True,
    )
    api_client.force_authenticate(user=item.cart.user)

    response = api_client.get(_cart_url())

    image_data = response.data["items"][0]["product"]["primary_image"]
    assert image_data["id"] == primary.pk
    assert image_data["image"].endswith("/media/products/primary.jpg")


def test_get_multiple_items_and_images_uses_two_queries(
    api_client,
    django_assert_num_queries,
):
    cart = CartFactory()
    for index in range(3):
        product = ProductFactory()
        CartItemFactory(cart=cart, product=product)
        ProductImage.objects.create(
            product=product,
            image=f"products/query-{index}.jpg",
        )
    api_client.force_authenticate(user=cart.user)

    with django_assert_num_queries(2):
        response = api_client.get(_cart_url())

    assert response.status_code == status.HTTP_200_OK
    assert len(response.data["items"]) == 3


def test_item_routes_use_exact_product_slug_not_uuid_or_numeric_id(api_client):
    item = CartItemFactory(product__stock=5)
    api_client.force_authenticate(user=item.cart.user)

    assert api_client.patch(
        _item_detail_url(item.product), {"quantity": 2}, format="json"
    ).status_code == status.HTTP_200_OK
    assert api_client.patch(
        f"/api/v1/cart/items/{item.product.uuid}/",
        {"quantity": 2},
        format="json",
    ).status_code == status.HTTP_404_NOT_FOUND
    assert api_client.patch(
        f"/api/v1/cart/items/{item.product.pk}/",
        {"quantity": 2},
        format="json",
    ).status_code == status.HTTP_404_NOT_FOUND
    assert api_client.patch(
        f"/api/v1/cart/items/{item.product.slug.upper()}/",
        {"quantity": 2},
        format="json",
    ).status_code == status.HTTP_404_NOT_FOUND
