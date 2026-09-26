"""Forms for DataPact - Section 5, Hriday Agarwal."""

from django import forms

from .models import Dataset


class DatasetForm(forms.ModelForm):
    class Meta:
        model = Dataset
        fields = ["name", "owner", "source_team", "description"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }
