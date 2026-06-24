import shutil
import tempfile
from io import BytesIO
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from matches.models import Match
from predictions.models import Prediction
from teams.models import Team
from users.models import UserProfile, WhatsAppReminderLog
from users.services.whatsapp_reminders import MorningWhatsAppReminderService


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

	def test_pages_include_global_avatar_preview_modal(self):
		response = self.client.get(reverse("profile_edit"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "avatarPreviewModal")
		self.assertContains(response, "avatarPreviewModalImage")

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

	def test_profile_update_saves_whatsapp_opt_in(self):
		response = self.client.post(
			reverse("profile_edit"),
			{
				"bio": "Quiero recordatorios",
				"whatsapp_phone_number": "+573001234567",
				"whatsapp_notifications_enabled": "on",
			},
		)

		profile = UserProfile.objects.get(user=self.user)
		self.assertRedirects(response, reverse("dashboard"))
		self.assertEqual(profile.whatsapp_phone_number, "+573001234567")
		self.assertTrue(profile.whatsapp_notifications_enabled)
		self.assertIsNotNone(profile.whatsapp_opt_in_at)

	def test_profile_update_requires_phone_when_whatsapp_enabled(self):
		response = self.client.post(
			reverse("profile_edit"),
			{
				"bio": "Sin telefono",
				"whatsapp_notifications_enabled": "on",
			},
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Ingresa tu número de WhatsApp")

	def test_profile_update_rejects_invalid_whatsapp_phone(self):
		response = self.client.post(
			reverse("profile_edit"),
			{
				"bio": "Telefono invalido",
				"whatsapp_phone_number": "3001234567",
				"whatsapp_notifications_enabled": "on",
			},
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "formato internacional")


class FakeWhatsAppClient:

	def __init__(self):
		self.calls = []

	def send_template(self, **kwargs):
		self.calls.append(kwargs)

		class Result:
			provider_message_id = "wamid.test"

		return Result()


class WhatsAppMorningReminderServiceTests(TestCase):

	def setUp(self):
		self.user = User.objects.create_user(username="whatsapp-user", first_name="Ana", password="secret123")
		self.other_user = User.objects.create_user(username="other-user", password="secret123")
		self.team_a = Team.objects.create(name="Colombia", code="COL")
		self.team_b = Team.objects.create(name="Brasil", code="BRA")
		UserProfile.objects.create(
			user=self.user,
			whatsapp_phone_number="+573001234567",
			whatsapp_notifications_enabled=True,
			whatsapp_opt_in_at=timezone.now(),
		)
		UserProfile.objects.create(
			user=self.other_user,
			whatsapp_phone_number="+573009999999",
			whatsapp_notifications_enabled=True,
			whatsapp_opt_in_at=timezone.now(),
		)

	def _match(self, *, hours_offset=3):
		kickoff_at = timezone.now() + timedelta(hours=hours_offset)
		return Match.objects.create(
			home_team=self.team_a,
			away_team=self.team_b,
			kickoff_at=kickoff_at,
			finished=False,
		), timezone.localdate(kickoff_at)

	def test_service_dry_run_logs_only_users_with_pending_predictions(self):
		match, reminder_date = self._match()
		Prediction.objects.create(
			user=self.other_user,
			match=match,
			predicted_home_score=1,
			predicted_away_score=0,
		)

		summary = MorningWhatsAppReminderService(client=FakeWhatsAppClient()).run(
			reminder_date=reminder_date,
			dry_run=True,
		)

		self.assertEqual(summary.users_checked, 2)
		self.assertEqual(summary.dry_run, 1)
		self.assertEqual(summary.skipped, 1)
		log = WhatsAppReminderLog.objects.get(user=self.user)
		self.assertEqual(log.status, WhatsAppReminderLog.STATUS_DRY_RUN)
		self.assertEqual(log.pending_match_count, 1)
		self.assertEqual(log.phone_number, "+573001234567")
		self.assertFalse(WhatsAppReminderLog.objects.filter(user=self.other_user).exists())

	def test_service_sends_template_and_prevents_duplicate_sent_reminders(self):
		match, reminder_date = self._match()
		client = FakeWhatsAppClient()

		first_summary = MorningWhatsAppReminderService(client=client).run(reminder_date=reminder_date)
		second_summary = MorningWhatsAppReminderService(client=client).run(reminder_date=reminder_date)

		self.assertEqual(first_summary.sent, 2)
		self.assertEqual(second_summary.skipped, 2)
		self.assertEqual(len(client.calls), 2)
		ana_call = next(call for call in client.calls if call["to"] == "+573001234567")
		self.assertEqual(ana_call["body_parameters"][0], "Ana")
		self.assertEqual(ana_call["body_parameters"][1], 1)
		self.assertEqual(WhatsAppReminderLog.objects.filter(status=WhatsAppReminderLog.STATUS_SENT).count(), 2)

	def test_management_command_supports_dry_run(self):
		match, reminder_date = self._match()
		stdout = StringIO()

		call_command(
			"send_whatsapp_morning_reminders",
			f"--date={reminder_date.isoformat()}",
			"--dry-run",
			stdout=stdout,
		)

		self.assertIn("Recordatorios WhatsApp procesados", stdout.getvalue())
		self.assertEqual(WhatsAppReminderLog.objects.filter(status=WhatsAppReminderLog.STATUS_DRY_RUN).count(), 2)


