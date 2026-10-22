"""Forms for the tracker web UI."""
import yaml
from django import forms
from django.core.exceptions import ValidationError

from .models import TrackedApp


MAX_APPS_CONFIG_SIZE = 1_048_576
MAX_APPS_PER_CONFIG = 1000
APP_CONFIG_KEYS = {"appid", "alias", "news", "updates", "price"}


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


class AppsImportForm(forms.Form):
    """Validate an apps.yaml file before it changes the tracked app list."""
    file = forms.FileField(
        label="YAML file",
        widget=forms.ClearableFileInput(attrs={
            "class": "form-control",
            "accept": ".yaml,.yml,application/yaml,text/yaml",
        }),
    )

    def clean_file(self):
        uploaded_file = self.cleaned_data["file"]
        if uploaded_file.size > MAX_APPS_CONFIG_SIZE:
            raise ValidationError("The YAML file must be 1 MB or smaller.")

        try:
            content = uploaded_file.read().decode("utf-8-sig")
            data = yaml.safe_load(content)
        except UnicodeDecodeError as exc:
            raise ValidationError("The YAML file must use UTF-8 encoding.") from exc
        except yaml.YAMLError as exc:
            raise ValidationError(f"Invalid YAML: {exc}") from exc

        if not isinstance(data, dict) or set(data) != {"apps"}:
            raise ValidationError("The YAML document must contain only an 'apps' list.")

        apps = data["apps"]
        if not isinstance(apps, list):
            raise ValidationError("'apps' must be a list.")
        if len(apps) > MAX_APPS_PER_CONFIG:
            raise ValidationError(
                f"The YAML file cannot contain more than {MAX_APPS_PER_CONFIG} apps."
            )

        cleaned_apps = []
        appids = set()
        for index, app in enumerate(apps, start=1):
            if not isinstance(app, dict):
                raise ValidationError(f"App entry {index} must be a mapping.")
            if set(app) - APP_CONFIG_KEYS:
                raise ValidationError(
                    f"App entry {index} contains unsupported settings."
                )

            appid = app.get("appid")
            if type(appid) is not int or not 1 <= appid <= 4_294_967_295:
                raise ValidationError(
                    f"App entry {index} must have a positive integer appid."
                )
            if appid in appids:
                raise ValidationError(f"AppID {appid} appears more than once.")
            appids.add(appid)

            alias = app.get("alias", "")
            if not isinstance(alias, str) or len(alias) > 200:
                raise ValidationError(
                    f"App entry {index} alias must be a string of at most 200 characters."
                )

            settings = {}
            for key in ("news", "updates", "price"):
                value = app.get(key, True)
                if type(value) is not bool:
                    raise ValidationError(
                        f"App entry {index} setting '{key}' must be true or false."
                    )
                settings[key] = value

            cleaned_apps.append({
                "appid": appid,
                "alias": alias,
                **settings,
            })

        self.cleaned_data["apps"] = cleaned_apps
        return uploaded_file


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
