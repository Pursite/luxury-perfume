from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.users.models import OTPChallenge


class Command(BaseCommand):
    help = "Remove expired OTP redemption state. Does not access cached OTP values."

    def handle(self, *args, **options):
        count, _ = OTPChallenge.objects.filter(expires_at__lte=timezone.now()).delete()
        self.stdout.write(f"Removed {count} expired OTP challenges.")
