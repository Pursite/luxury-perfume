from django.db.models import Index
from django.test import SimpleTestCase

from apps.notifications.models import SmsDelivery


class SmsDeliveryMetadataTests(SimpleTestCase):
    def test_custom_index_names_fit_djangos_maximum(self):
        assert all(len(index.name) <= Index.max_name_length for index in SmsDelivery._meta.indexes)
