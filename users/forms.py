from django import forms

from users.models import UserProfile
from users.services.rich_text import MAX_PROFILE_BIO_LENGTH, sanitize_profile_bio


class UserProfileForm(forms.ModelForm):
    MAX_AVATAR_SIZE = 5 * 1024 * 1024

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.bio:
            self.initial["bio"] = sanitize_profile_bio(self.instance.bio)

    def clean_bio(self):
        bio = sanitize_profile_bio(self.cleaned_data.get("bio"))
        if len(bio) > MAX_PROFILE_BIO_LENGTH:
            raise forms.ValidationError(f"La bio no puede superar {MAX_PROFILE_BIO_LENGTH} caracteres.")
        return bio

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
                    "class": "form-control rich-bio-textarea",
                    "rows": 6,
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

