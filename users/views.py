import logging
from pathlib import Path

from django import forms
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.files.storage import default_storage
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import UpdateView

from users.models import UserProfile
from users.forms import UserProfileForm


logger = logging.getLogger(__name__)


class UserProfileUpdateView(LoginRequiredMixin, UpdateView):
    model = UserProfile
    form_class = UserProfileForm
    template_name = "users/profile_edit.html"
    success_url = reverse_lazy("dashboard")

    def get_object(self, queryset=None):
        profile, created = UserProfile.objects.get_or_create(user=self.request.user)
        return profile

    def form_valid(self, form):
        try:
            if not getattr(settings, "CLOUDINARY_STORAGE_ENABLED", False):
                Path(settings.MEDIA_ROOT).mkdir(parents=True, exist_ok=True)
            return super().form_valid(form)
        except Exception as exc:
            logger.exception(
                "Profile avatar save failed for user_id=%s MEDIA_ROOT=%s error=%s",
                self.request.user.id,
                settings.MEDIA_ROOT,
                exc,
            )
            form.add_error(
                None,
                forms.ValidationError(
                    "No se pudo guardar la imagen en este momento. Intenta con otra imagen o vuelve a intentarlo más tarde."
                ),
            )
            return self.form_invalid(form)


class MediaDiagnosticsView(LoginRequiredMixin, UserPassesTestMixin, View):

    def test_func(self):
        return self.request.user.is_staff

    def get(self, request, *args, **kwargs):
        media_root = Path(settings.MEDIA_ROOT)
        payload = {
            "media_root": str(media_root),
            "exists": media_root.exists(),
            "is_dir": media_root.is_dir(),
            "writable": False,
            "error": "",
            "storage_backend": f"{default_storage.__class__.__module__}.{default_storage.__class__.__name__}",
            "cloudinary_configured": getattr(settings, "CLOUDINARY_CONFIGURED", False),
            "cloudinary_enabled": getattr(settings, "CLOUDINARY_STORAGE_ENABLED", False),
            "cloudinary_cloud_name_present": bool(getattr(settings, "CLOUDINARY_CLOUD_NAME", "")),
            "cloudinary_api_key_present": bool(getattr(settings, "CLOUDINARY_API_KEY", "")),
            "cloudinary_api_secret_present": bool(getattr(settings, "CLOUDINARY_API_SECRET", "")),
            "cloudinary_url_present": bool(getattr(settings, "CLOUDINARY_URL", "")),
        }

        try:
            media_root.mkdir(parents=True, exist_ok=True)
            probe = media_root / ".diagnostic-write-test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            payload.update(
                {
                    "exists": media_root.exists(),
                    "is_dir": media_root.is_dir(),
                    "writable": True,
                }
            )
        except Exception as exc:
            payload["error"] = str(exc)

        return JsonResponse(payload)


