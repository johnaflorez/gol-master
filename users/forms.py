from django import forms

from users.models import UserProfile


class UserProfileForm(forms.ModelForm):
    MAX_AVATAR_SIZE = 5 * 1024 * 1024

    def clean_avatar(self):
        avatar = self.cleaned_data.get("avatar")
        if not avatar:
            return avatar

        if avatar.size > self.MAX_AVATAR_SIZE:
            raise forms.ValidationError("La imagen no puede superar 5MB.")

        return avatar
    
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

