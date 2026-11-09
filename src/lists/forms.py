from django import forms
from django.utils.translation import gettext as _
from django_select2 import forms as s2forms

from lists.models import CustomList


class CollaboratorsWidget(s2forms.ModelSelect2MultipleWidget):
    """Custom widget for selecting multiple users."""

    search_fields = ["username__icontains"]


class CustomListForm(forms.ModelForm):
    """Form for creating new custom lists."""

    class Meta:
        """Bind form to model."""

        model = CustomList
        fields = ["name", "description", "collaborators"]
        widgets = {
            "collaborators": CollaboratorsWidget(
                attrs={
                    "data-minimum-input-length": 1,
                    "data-allow-clear": "false",
                },
            ),
        }

    def __init__(self, *args, **kwargs):
        """Use the active language for labels and the collaborator search."""
        super().__init__(*args, **kwargs)
        self.fields["name"].label = _("Name")
        self.fields["description"].label = _("Description")
        self.fields["collaborators"].label = _("Collaborators")
        self.fields["collaborators"].widget.attrs["data-placeholder"] = _(
            "Search users to add...",
        )
