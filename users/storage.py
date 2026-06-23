import os
from pathlib import PurePosixPath
from uuid import uuid4

from django.conf import settings
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible


@deconstructible
class CloudinaryMediaStorage(Storage):
    """Django storage backend for user-uploaded media stored in Cloudinary.

    It is intentionally small and only implements the operations this project
    needs for profile avatars: save, url and delete. The backend is enabled via
    settings only when Cloudinary credentials are present.
    """

    def __init__(self, folder=None):
        self.folder = folder or getattr(settings, "CLOUDINARY_MEDIA_FOLDER", "gol_master")
        self._configure_cloudinary()

    def _configure_cloudinary(self):
        import cloudinary

        cloudinary_url = getattr(settings, "CLOUDINARY_URL", "")
        if cloudinary_url:
            os.environ["CLOUDINARY_URL"] = cloudinary_url
            cloudinary.config(secure=True)
            return

        cloudinary.config(
            cloud_name=getattr(settings, "CLOUDINARY_CLOUD_NAME", ""),
            api_key=getattr(settings, "CLOUDINARY_API_KEY", ""),
            api_secret=getattr(settings, "CLOUDINARY_API_SECRET", ""),
            secure=True,
        )

    def _normalize_name(self, name):
        return str(PurePosixPath(name.replace("\\", "/")))

    def _strip_extension(self, name):
        path = PurePosixPath(self._normalize_name(name))
        if path.suffix:
            return str(path.with_suffix(""))
        return str(path)

    def _cloudinary_public_id(self, name):
        base_public_id = self._strip_extension(name)
        if self.folder:
            return f"{self.folder}/{base_public_id}"
        return base_public_id

    def get_available_name(self, name, max_length=None):
        path = PurePosixPath(self._normalize_name(name))
        unique_name = f"{path.stem}-{uuid4().hex[:12]}{path.suffix}"
        candidate = str(path.with_name(unique_name))
        if max_length and len(candidate) > max_length:
            candidate = candidate[-max_length:]
        return candidate

    def _save(self, name, content):
        import cloudinary.uploader

        normalized_name = self._normalize_name(name)
        public_id = self._cloudinary_public_id(normalized_name)
        content.seek(0)
        cloudinary.uploader.upload(
            content,
            public_id=public_id,
            resource_type="image",
            overwrite=True,
            invalidate=True,
        )
        return normalized_name

    def url(self, name):
        import cloudinary.utils

        public_id = self._cloudinary_public_id(name)
        url, _ = cloudinary.utils.cloudinary_url(
            public_id,
            resource_type="image",
            secure=True,
        )
        return url

    def delete(self, name):
        import cloudinary.uploader

        if name:
            cloudinary.uploader.destroy(
                self._cloudinary_public_id(name),
                resource_type="image",
                invalidate=True,
            )

    def exists(self, name):
        return False

    def size(self, name):
        return 0

