from django import forms
from users.models import UserProfile


class UserProfileForm(forms.ModelForm):
    
    class Meta:
        model = UserProfile
        fields = ("bio", "avatar")
        labels = {
            "bio": "Sobre ti",
            "avatar": "Foto de perfil",
        }
        widgets = {
            "bio": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "Cuéntanos sobre ti...",
                }
            ),
            "avatar": forms.FileInput(
                attrs={
                    "class": "form-control",
                    "accept": "image/*",
                }
            ),
        }

