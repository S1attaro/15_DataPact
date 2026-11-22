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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Stage 3F: say what to do instead of "---------". Still the blank
        # option (value ""), so leaving it is still "This field is required."
        self.fields["owner"].empty_label = "Choose an owner"
