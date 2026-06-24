import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class WhatsAppCloudAPIError(Exception):
    """Raised when WhatsApp Cloud API rejects or cannot process a message."""


@dataclass
class WhatsAppSendResult:
    provider_message_id: str = ""
    raw_response: dict | None = None


class WhatsAppCloudClient:
    """Small WhatsApp Business Cloud API client using approved message templates."""

    def __init__(self):
        self.access_token = getattr(settings, "WHATSAPP_ACCESS_TOKEN", "")
        self.phone_number_id = getattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "")
        self.api_version = getattr(settings, "WHATSAPP_CLOUD_API_VERSION", "v20.0")
        self.timeout = getattr(settings, "WHATSAPP_TIMEOUT", 15)

    def _validate_settings(self):
        if not self.access_token or not self.phone_number_id:
            raise ImproperlyConfigured(
                "Configura WHATSAPP_ACCESS_TOKEN y WHATSAPP_PHONE_NUMBER_ID para enviar recordatorios por WhatsApp."
            )

    def send_template(self, *, to, template_name, language_code, body_parameters):
        self._validate_settings()
        endpoint = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": to.lstrip("+"),
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
                "components": [
                    {
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": str(parameter)}
                            for parameter in body_parameters
                        ],
                    }
                ],
            },
        }
        request = Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.timeout) as response:
                response_payload = json.loads(response.read().decode("utf-8") or "{}")
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise WhatsAppCloudAPIError(f"WhatsApp API HTTP {exc.code}: {error_body}") from exc
        except URLError as exc:
            raise WhatsAppCloudAPIError(f"No se pudo conectar con WhatsApp API: {exc.reason}") from exc

        messages = response_payload.get("messages") or []
        provider_message_id = messages[0].get("id", "") if messages else ""
        return WhatsAppSendResult(provider_message_id=provider_message_id, raw_response=response_payload)

