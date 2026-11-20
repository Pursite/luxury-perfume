from datetime import date, timedelta

from django import forms
from django.utils import timezone


class DashboardDateForm(forms.Form):
    start = forms.DateField(
        label="From",
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
    )
    end = forms.DateField(
        label="Through",
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
    )

    def __init__(self, data=None, *, today=None):
        self.today = today or timezone.localdate(timezone=timezone.get_default_timezone())
        super().__init__(
            data=data,
            initial={"start": self.today - timedelta(days=29), "end": self.today},
        )

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start"), cleaned.get("end")
        if start and start < date(1900, 1, 1):
            self.add_error("start", "Choose a start date on or after January 1, 1900.")
        if end and end > self.today:
            self.add_error("end", "Choose an end date no later than today.")
        if start and end:
            if start > end:
                raise forms.ValidationError("The start date must be on or before the end date.")
            if (end - start).days >= 90:
                raise forms.ValidationError("Choose a date range of 90 days or less.")
        return cleaned


class InventoryFilterForm(forms.Form):
    threshold = forms.IntegerField(
        label="Low-stock threshold",
        min_value=0,
        max_value=2_147_483_647,
        initial=5,
    )
