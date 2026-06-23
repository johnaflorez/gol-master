import shutil
import tempfile
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from users.models import UserProfile
from users.storage import CloudinaryMediaStorage


def make_image_file(name="avatar.png", image_format="PNG", content_type="image/png"):
	image = Image.new("RGB", (20, 20), color="red")
	buffer = BytesIO()
	image.save(buffer, format=image_format)
	return SimpleUploadedFile(name, buffer.getvalue(), content_type=content_type)


class UserProfileUpdateViewTests(TestCase):

	def setUp(self):
		self.temp_media_root = tempfile.mkdtemp()
		self.user = User.objects.create_user(username="profile-user", password="secret123")
		self.client.login(username="profile-user", password="secret123")

	def tearDown(self):
		shutil.rmtree(self.temp_media_root, ignore_errors=True)

	def test_profile_update_saves_valid_avatar(self):
		with override_settings(MEDIA_ROOT=self.temp_media_root):
			response = self.client.post(
				reverse("profile_edit"),
				{
					"bio": "Mi bio",
					"avatar": make_image_file(),
				},
			)

		profile = UserProfile.objects.get(user=self.user)
		self.assertRedirects(response, reverse("dashboard"))
		self.assertEqual(profile.bio, "Mi bio")
		self.assertTrue(profile.avatar.name.startswith("avatars/"))

	def test_profile_update_accepts_valid_image_with_non_standard_content_type(self):
		with override_settings(MEDIA_ROOT=self.temp_media_root):
			response = self.client.post(
				reverse("profile_edit"),
				{
					"bio": "Foto valida",
					"avatar": make_image_file("avatar.jpg", image_format="JPEG", content_type="image/jpg"),
				},
			)

		profile = UserProfile.objects.get(user=self.user)
		self.assertRedirects(response, reverse("dashboard"))
		self.assertEqual(profile.bio, "Foto valida")
		self.assertTrue(profile.avatar.name.startswith("avatars/"))

	def test_profile_update_creates_missing_media_root(self):
		missing_media_root = tempfile.mkdtemp()
		shutil.rmtree(missing_media_root)

		with override_settings(MEDIA_ROOT=missing_media_root):
			response = self.client.post(
				reverse("profile_edit"),
				{
					"bio": "Media root nuevo",
					"avatar": make_image_file(),
				},
			)

		profile = UserProfile.objects.get(user=self.user)
		self.assertRedirects(response, reverse("dashboard"))
		self.assertTrue(profile.avatar.name.startswith("avatars/"))
		shutil.rmtree(missing_media_root, ignore_errors=True)

	def test_profile_update_rejects_invalid_avatar_type(self):
		invalid_file = SimpleUploadedFile("avatar.txt", b"not an image", content_type="text/plain")

		with override_settings(MEDIA_ROOT=self.temp_media_root):
			response = self.client.post(
				reverse("profile_edit"),
				{
					"bio": "Mi bio",
					"avatar": invalid_file,
				},
			)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Adjunte una imagen válida")

	@patch("django.core.files.storage.filesystem.FileSystemStorage._save", side_effect=OSError("no write"))
	def test_profile_update_storage_error_returns_form_error(self, storage_save):
		with override_settings(MEDIA_ROOT=self.temp_media_root):
			response = self.client.post(
				reverse("profile_edit"),
				{
					"bio": "Mi bio",
					"avatar": make_image_file(),
				},
			)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "No se pudo guardar la imagen")

	@patch("django.core.files.storage.filesystem.FileSystemStorage._save", side_effect=RuntimeError("unexpected storage error"))
	def test_profile_update_unexpected_storage_error_returns_form_error(self, storage_save):
		with override_settings(MEDIA_ROOT=self.temp_media_root):
			response = self.client.post(
				reverse("profile_edit"),
				{
					"bio": "Mi bio",
					"avatar": make_image_file(),
				},
			)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "No se pudo guardar la imagen")

	def test_media_diagnostics_requires_staff(self):
		response = self.client.get(reverse("media_diagnostics"))

		self.assertEqual(response.status_code, 403)

	def test_media_diagnostics_reports_writable_media_root_for_staff(self):
		self.user.is_staff = True
		self.user.save()

		with override_settings(MEDIA_ROOT=self.temp_media_root):
			response = self.client.get(reverse("media_diagnostics"))

		self.assertEqual(response.status_code, 200)
		payload = response.json()
		self.assertEqual(payload["media_root"], self.temp_media_root)
		self.assertTrue(payload["exists"])
		self.assertTrue(payload["is_dir"])
		self.assertTrue(payload["writable"])


class CloudinaryMediaStorageTests(TestCase):

	@patch("cloudinary.config")
	@patch("cloudinary.uploader.upload")
	def test_storage_uploads_file_and_returns_normalized_name(self, upload, config):
		storage = CloudinaryMediaStorage(folder="test_folder")
		file = make_image_file()

		saved_name = storage._save("avatars/avatar.png", file)

		self.assertEqual(saved_name, "avatars/avatar.png")
		upload.assert_called_once()
		self.assertEqual(upload.call_args.kwargs["public_id"], "test_folder/avatars/avatar")
		self.assertEqual(upload.call_args.kwargs["resource_type"], "image")

	@patch("cloudinary.config")
	@patch("cloudinary.utils.cloudinary_url", return_value=("https://res.cloudinary.com/demo/image/upload/test_folder/avatars/avatar", {}))
	def test_storage_builds_cloudinary_url(self, cloudinary_url, config):
		storage = CloudinaryMediaStorage(folder="test_folder")

		url = storage.url("avatars/avatar.png")

		self.assertEqual(url, "https://res.cloudinary.com/demo/image/upload/test_folder/avatars/avatar")
		cloudinary_url.assert_called_once_with(
			"test_folder/avatars/avatar",
			resource_type="image",
			secure=True,
		)

	@patch("cloudinary.config")
	@patch("cloudinary.uploader.destroy")
	def test_storage_deletes_cloudinary_resource(self, destroy, config):
		storage = CloudinaryMediaStorage(folder="test_folder")

		storage.delete("avatars/avatar.png")

		destroy.assert_called_once_with(
			"test_folder/avatars/avatar",
			resource_type="image",
			invalidate=True,
		)


