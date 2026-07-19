import factory
from apps.users.models import CustomUser, Address


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CustomUser

    phone_number = factory.Sequence(lambda n: f"0912{n:07d}")

    username = factory.Sequence(lambda n: f"user_{n:05d}")
    email = factory.Faker('email')

    first_name = factory.Faker('first_name')
    last_name = factory.Faker('last_name')
    is_active = True
    is_staff = False


class AddressFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Address

    user = factory.SubFactory(UserFactory)
    title = factory.Iterator(['خانه', 'شرکت', 'مغازه'])
    full_address = factory.Faker('address')
    postal_code = factory.Sequence(lambda n: f"12345{n:05d}")