"""Forms for the tracker web UI."""
from django import forms

from .models import TrackedApp


class AddAppForm(forms.Form):
    """Form for adding a new tracked app via the dashboard."""
    appid = forms.IntegerField(
        label="Steam App ID",
        min_value=1,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "e.g. 730, 570, 1245620",
        }),
    )
    alias = forms.CharField(
        max_length=200, required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Optional — auto-resolved from Steam if blank",
        }),
    )
    track_price = forms.BooleanField(required=False, initial=True,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))
    track_news = forms.BooleanField(required=False, initial=True,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))
    track_updates = forms.BooleanField(required=False, initial=True,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))


class ChangeFilterForm(forms.Form):
    """Filter form for the changelog page."""
    change_type = forms.ChoiceField(
        required=False, widget=forms.Select(attrs={"class": "form-select"}),
    )
    appid = forms.IntegerField(required=False,
        widget=forms.Select(attrs={"class": "form-select"}))
    days = forms.IntegerField(required=False, initial=7, min_value=1, max_value=365,
        widget=forms.NumberInput(attrs={"class": "form-control", "min": 1, "max": 365}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import Change, TrackedApp
        self.fields["change_type"].choices = (
            [("", "All types")] + list(Change.Type.choices)
        )
        self.fields["appid"].widget.choices = [("", "All apps")] + [
            (a.appid, str(a)) for a in TrackedApp.objects.all().order_by("cached_name", "appid")
        ]
