from django.db import models
from django.contrib.auth.models import User


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    bio = models.TextField(max_length=500, blank=True, default="", help_text="Breve descripción o bio personal")
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True, help_text="Foto de perfil")
    whatsapp_phone_number = models.CharField(
        "WhatsApp",
        max_length=20,
        blank=True,
        default="",
        help_text="Número en formato internacional, por ejemplo +573001234567.",
    )
    whatsapp_notifications_enabled = models.BooleanField(
        "recibir recordatorios por WhatsApp",
        default=False,
        help_text="El usuario aceptó recibir recordatorios de pronósticos por WhatsApp.",
    )
    whatsapp_opt_in_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Profile of {self.user.username}"


class WhatsAppReminderLog(models.Model):
    STATUS_DRY_RUN = "dry_run"
    STATUS_SENT = "sent"
    STATUS_FAILED = "failed"
    STATUS_SKIPPED = "skipped"
    STATUS_CHOICES = [
        (STATUS_DRY_RUN, "Prueba"),
        (STATUS_SENT, "Enviado"),
        (STATUS_FAILED, "Fallido"),
        (STATUS_SKIPPED, "Omitido"),
    ]

    REMINDER_MORNING_PREDICTION = "morning_prediction"
    REMINDER_TYPE_CHOICES = [
        (REMINDER_MORNING_PREDICTION, "Recordatorio matutino de pronósticos"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="whatsapp_reminder_logs")
    reminder_date = models.DateField(db_index=True)
    reminder_type = models.CharField(max_length=40, choices=REMINDER_TYPE_CHOICES, default=REMINDER_MORNING_PREDICTION)
    phone_number = models.CharField(max_length=20)
    pending_match_count = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES)
    provider_message_id = models.CharField(max_length=120, blank=True, default="")
    error_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("user", "reminder_date", "reminder_type"),
                name="unique_whatsapp_reminder_per_user_date_type",
            )
        ]

    def __str__(self):
        return f"{self.user} - {self.reminder_date} - {self.status}"

