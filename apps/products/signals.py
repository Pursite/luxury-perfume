from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.products.cache import invalidate_product_api_cache
from apps.products.models import (
    Brand,
    Category,
    FragranceNote,
    Product,
    ProductFragranceNote,
    ProductImage,
)


@receiver(post_save, sender=Product, dispatch_uid="products.invalidate_product_save")
@receiver(post_delete, sender=Product, dispatch_uid="products.invalidate_product_delete")
@receiver(post_save, sender=ProductImage, dispatch_uid="products.invalidate_image_save")
@receiver(post_delete, sender=ProductImage, dispatch_uid="products.invalidate_image_delete")
@receiver(post_save, sender=Category, dispatch_uid="products.invalidate_category_save")
@receiver(post_delete, sender=Category, dispatch_uid="products.invalidate_category_delete")
@receiver(post_save, sender=Brand, dispatch_uid="products.invalidate_brand_save")
@receiver(post_delete, sender=Brand, dispatch_uid="products.invalidate_brand_delete")
@receiver(
    post_save,
    sender=FragranceNote,
    dispatch_uid="products.invalidate_fragrance_note_save",
)
@receiver(
    post_delete,
    sender=FragranceNote,
    dispatch_uid="products.invalidate_fragrance_note_delete",
)
@receiver(
    post_save,
    sender=ProductFragranceNote,
    dispatch_uid="products.invalidate_product_fragrance_note_save",
)
@receiver(
    post_delete,
    sender=ProductFragranceNote,
    dispatch_uid="products.invalidate_product_fragrance_note_delete",
)
def invalidate_cached_product_responses(**kwargs) -> None:
    """Invalidate public catalog data only after the database transaction commits."""
    if kwargs.get("raw"):
        return
    transaction.on_commit(invalidate_product_api_cache)
