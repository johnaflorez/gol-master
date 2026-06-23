import json
from pathlib import Path

from django.conf import settings
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Muestra diagnóstico del storage activo para media/avatars."

    def handle(self, *args, **options):
        media_root = Path(settings.MEDIA_ROOT)
        payload = {
            "storage_backend": f"{default_storage.__class__.__module__}.{default_storage.__class__.__name__}",
            "media_root": str(media_root),
            "cloudinary_configured": getattr(settings, "CLOUDINARY_CONFIGURED", False),
            "cloudinary_enabled": getattr(settings, "CLOUDINARY_STORAGE_ENABLED", False),
            "cloudinary_url_present": bool(getattr(settings, "CLOUDINARY_URL", "")),
            "cloudinary_cloud_name_present": bool(getattr(settings, "CLOUDINARY_CLOUD_NAME", "")),
            "cloudinary_api_key_present": bool(getattr(settings, "CLOUDINARY_API_KEY", "")),
            "cloudinary_api_secret_present": bool(getattr(settings, "CLOUDINARY_API_SECRET", "")),
            "local_exists": media_root.exists(),
            "local_is_dir": media_root.is_dir(),
            "local_writable": False,
            "local_error": "",
        }

        try:
            media_root.mkdir(parents=True, exist_ok=True)
            probe = media_root / ".check-media-storage"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            payload["local_exists"] = media_root.exists()
            payload["local_is_dir"] = media_root.is_dir()
            payload["local_writable"] = True
        except Exception as exc:
            payload["local_error"] = str(exc)

        self.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False))

