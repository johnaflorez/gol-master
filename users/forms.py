import re

from django import forms
from django.utils import timezone

from users.models import UserProfile


class UserProfileForm(forms.ModelForm):
    MAX_AVATAR_SIZE = 5 * 1024 * 1024
    E164_PATTERN = re.compile(r"^\+[1-9]\d{7,14}$")

    def clean_avatar(self):
        avatar = self.cleaned_data.get("avatar")
        if not avatar:
            return avatar

        if avatar.size > self.MAX_AVATAR_SIZE:
            raise forms.ValidationError("La imagen no puede superar 5MB.")

        return avatar

    def clean_whatsapp_phone_number(self):
        phone_number = (self.cleaned_data.get("whatsapp_phone_number") or "").strip().replace(" ", "")
        if phone_number and not self.E164_PATTERN.match(phone_number):
            raise forms.ValidationError("Ingresa el número en formato internacional, por ejemplo +573001234567.")
        return phone_number

    def clean(self):
        cleaned_data = super().clean()
        notifications_enabled = cleaned_data.get("whatsapp_notifications_enabled")
        phone_number = cleaned_data.get("whatsapp_phone_number")

        if notifications_enabled and not phone_number:
            self.add_error("whatsapp_phone_number", "Ingresa tu número de WhatsApp para activar los recordatorios.")

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        if instance.whatsapp_notifications_enabled:
            if not instance.whatsapp_opt_in_at:
                instance.whatsapp_opt_in_at = timezone.now()
        else:
            instance.whatsapp_opt_in_at = None

        if commit:
            instance.save()
            self.save_m2m()

        return instance
    
    class Meta:
        model = UserProfile
        fields = ("bio", "avatar", "whatsapp_phone_number", "whatsapp_notifications_enabled")
        labels = {
            "bio": "Sobre ti",
            "avatar": "Foto de perfil",
            "whatsapp_phone_number": "Número de WhatsApp",
            "whatsapp_notifications_enabled": "Recibir recordatorios por WhatsApp",
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
            "whatsapp_phone_number": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "+573001234567",
                    "inputmode": "tel",
                    "autocomplete": "tel",
                }
            ),
            "whatsapp_notifications_enabled": forms.CheckboxInput(
                attrs={
                    "class": "form-check-input",
                }
            ),
        }

