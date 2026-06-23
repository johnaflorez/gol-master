from django import forms
from users.models import UserProfile


class UserProfileForm(forms.ModelForm):
    MAX_AVATAR_SIZE = 5 * 1024 * 1024
    ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}

    def clean_avatar(self):
        avatar = self.cleaned_data.get("avatar")
        if not avatar:
            return avatar

        if avatar.size > self.MAX_AVATAR_SIZE:
            raise forms.ValidationError("La imagen no puede superar 5MB.")

        content_type = getattr(avatar, "content_type", "")
        if content_type and content_type not in self.ALLOWED_IMAGE_TYPES:
            raise forms.ValidationError("Formato no permitido. Usa JPG, PNG o WEBP.")

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

