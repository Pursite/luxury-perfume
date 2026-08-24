import factory
from factory.django import DjangoModelFactory

from apps.cart.models import Cart, CartItem
from apps.products.tests.factories import ProductFactory
from apps.users.tests.factories import UserFactory


class CartFactory(DjangoModelFactory):
    class Meta:
        model = Cart

    user = factory.SubFactory(UserFactory)


class CartItemFactory(DjangoModelFactory):
    class Meta:
        model = CartItem

    cart = factory.SubFactory(CartFactory)
    product = factory.SubFactory(ProductFactory)
    quantity = 1
