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
