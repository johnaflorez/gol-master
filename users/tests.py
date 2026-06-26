import shutil
import tempfile
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from users.forms import UserProfileForm
from users.models import UserProfile
from users.services.rich_text import MAX_PROFILE_BIO_LENGTH, sanitize_profile_bio
from users.templatetags.user_extras import rich_profile_bio, user_bio_or_username


def make_image_file(name="avatar.png", image_format="PNG", content_type="image/png"):
	image = Image.new("RGB", (20, 20), color="red")
	buffer = BytesIO()
	image.save(buffer, format=image_format)
	return SimpleUploadedFile(name, buffer.getvalue(), content_type=content_type)


class RichTextProfileBioTests(TestCase):

	def test_sanitizer_preserves_allowed_formatting_and_emojis(self):
		html = '<p><strong>Gol</strong> <span style="color:#ff0000;font-size:1.5rem;text-align:center">⚽</span></p>'

		cleaned = sanitize_profile_bio(html)

		self.assertIn("<strong>Gol</strong>", cleaned)
		self.assertIn('style="color:#ff0000;font-size:1.5rem;text-align:center;"', cleaned)
		self.assertIn("⚽", cleaned)

	def test_sanitizer_removes_scripts_events_images_and_unsafe_css(self):
		html = '<span style="position:absolute;color:red;background-color:url(javascript:alert(1));font-size:999px" onclick="alert(1)">X</span><script>alert(2)</script><img src=x onerror=alert(3)>'

		cleaned = sanitize_profile_bio(html)

		self.assertEqual(cleaned, '<span style="color:red;">X</span>')
		self.assertNotIn("onclick", cleaned)
		self.assertNotIn("script", cleaned.lower())
		self.assertNotIn("alert", cleaned)
		self.assertNotIn("img", cleaned.lower())
		self.assertNotIn("position", cleaned.lower())
		self.assertNotIn("javascript", cleaned.lower())
		self.assertNotIn("url", cleaned.lower())
		self.assertNotIn("999px", cleaned.lower())

	def test_sanitizer_removes_css_expression_values(self):
		cleaned = sanitize_profile_bio('<span style="color:expression(alert(1));font-size:1.25rem">Seguro</span>')

		self.assertEqual(cleaned, '<span style="font-size:1.25rem;">Seguro</span>')
		self.assertNotIn("expression", cleaned.lower())
		self.assertNotIn("alert", cleaned.lower())

	def test_sanitizer_removes_empty_style_attributes(self):
		cleaned = sanitize_profile_bio('<span style="color:expression(alert(1));font-size:999px">Seguro</span>')

		self.assertEqual(cleaned, "<span>Seguro</span>")
		self.assertNotIn("style=", cleaned.lower())

	def test_sanitizer_allows_safe_links_and_removes_unsafe_protocols(self):
		html = '<a href="javascript:alert(1)" title="bad">bad</a><a href="https://example.com" title="ok">ok</a>'

		cleaned = sanitize_profile_bio(html)

		self.assertIn('<a title="bad">bad</a>', cleaned)
		self.assertIn('<a href="https://example.com" title="ok">ok</a>', cleaned)
		self.assertNotIn("javascript", cleaned.lower())
		self.assertNotIn("alert", cleaned)

	def test_profile_form_sanitizes_bio_before_saving(self):
		form = UserProfileForm(data={"bio": '<b>Hola</b><iframe src="https://example.com"></iframe>'})

		self.assertTrue(form.is_valid())
		self.assertEqual(form.cleaned_data["bio"], "<b>Hola</b>")

	def test_profile_form_rejects_bio_longer_than_limit(self):
		form = UserProfileForm(data={"bio": "x" * (MAX_PROFILE_BIO_LENGTH + 1)})

		self.assertFalse(form.is_valid())
		self.assertIn("bio", form.errors)

	def test_rich_profile_bio_filter_returns_safe_sanitized_html(self):
		rendered = str(rich_profile_bio('<u>Subrayado</u><script>alert(1)</script>'))

		self.assertEqual(rendered, "<u>Subrayado</u>")
		self.assertNotIn("script", rendered.lower())
		self.assertNotIn("alert", rendered)


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

	def test_profile_update_saves_sanitized_rich_bio(self):
		with override_settings(MEDIA_ROOT=self.temp_media_root):
			response = self.client.post(
				reverse("profile_edit"),
				{
					"bio": '<p><span style="color:#ff0000;font-size:1.5rem;position:absolute">Grande ⚽</span><script>alert(1)</script><img src=x onerror=alert(1)></p>',
				}
			)

		profile = UserProfile.objects.get(user=self.user)
		self.assertRedirects(response, reverse("dashboard"))
		self.assertIn('style="color:#ff0000;font-size:1.5rem;"', profile.bio)
		self.assertIn("Grande ⚽", profile.bio)
		self.assertNotIn("script", profile.bio.lower())
		self.assertNotIn("alert(1)", profile.bio)
		self.assertNotIn("onerror", profile.bio.lower())
		self.assertNotIn("position", profile.bio.lower())

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

	def test_pages_include_global_avatar_preview_modal(self):
		response = self.client.get(reverse("profile_edit"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "avatarPreviewModal")
		self.assertContains(response, "avatarPreviewModalImage")

	def test_profile_edit_includes_rich_bio_editor(self):
		response = self.client.get(reverse("profile_edit"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "profile-rich-bio-editor")
		self.assertContains(response, "data-rich-command=\"bold\"")
		self.assertContains(response, "data-rich-color")
		self.assertContains(response, "data-rich-emoji-toggle")
		self.assertContains(response, "data-rich-emoji-panel")
		self.assertContains(response, "data-rich-emoji-search")
		self.assertContains(response, "data-rich-emoji-tabs")
		self.assertContains(response, "data-rich-emoji-grid")
		self.assertContains(response, "EMOJI_CATEGORIES")
		self.assertContains(response, "pulgar")
		self.assertContains(response, "Caritas")
		self.assertContains(response, "Fútbol")
		self.assertContains(response, "event.stopPropagation")
		self.assertContains(response, "event.composedPath")
		self.assertContains(response, "clickedInsidePicker")

	def test_user_bio_or_username_renders_sanitized_html(self):
		profile = UserProfile.objects.create(
			user=self.user,
			bio='<span style="color:blue" onclick="alert(1)">Azul 💙</span><script>alert(1)</script>',
		)

		rendered = str(user_bio_or_username(profile.user))

		self.assertIn('style="color:blue;"', rendered)
		self.assertIn("Azul 💙", rendered)
		self.assertNotIn("onclick", rendered)
		self.assertNotIn("script", rendered)
		self.assertNotIn("alert(1)", rendered)

	def test_pages_include_responsive_sidebar_navigation(self):
		response = self.client.get(reverse("profile_edit"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "app-sidebar")
		self.assertContains(response, "appSidebarOffcanvas")
		self.assertContains(response, reverse("match_list"))
		self.assertContains(response, reverse("group_standings"))
		self.assertContains(response, "fa-list-check")
		self.assertContains(response, reverse("profile_edit"))
		self.assertContains(response, reverse("logout"))

	def test_existing_avatar_is_clickable_to_open_preview(self):
		with override_settings(MEDIA_ROOT=self.temp_media_root):
			profile = UserProfile.objects.create(user=self.user)
			profile.avatar = make_image_file()
			profile.save()

			response = self.client.get(reverse("profile_edit"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "avatar-clickable")
		self.assertContains(response, "data-avatar-url=")
		self.assertContains(response, "data-avatar-title=")

	def test_missing_avatar_fallback_is_not_clickable(self):
		response = self.client.get(reverse("profile_edit"))

		self.assertEqual(response.status_code, 200)
		self.assertNotContains(response, "data-avatar-url=")



