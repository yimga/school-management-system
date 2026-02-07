from django import forms


class SupportRequestForm(forms.Form):
    CATEGORY_CHOICES = [
        ("SUPPORT", "Support request"),
        ("FEEDBACK", "Product feedback"),
    ]

    category = forms.ChoiceField(choices=CATEGORY_CHOICES)
    subject = forms.CharField(max_length=200)
    message = forms.CharField(widget=forms.Textarea(attrs={"rows": 6}))
