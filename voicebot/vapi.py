"""Тонкий клиент Vapi API: создать звонок и дождаться его окончания.

Vapi берёт на себя всю «голосовую» часть: телефонию, распознавание речи,
LLM, синтез голоса, перебивания. Мы только отправляем настройки и забираем
результат.
"""

import time

import requests

API_URL = "https://api.vapi.ai"

# Звонок закончился без разговора — извлекать ответы не из чего, ждать нечего.
NO_CONVERSATION = {"customer-did-not-answer", "customer-busy", "voicemail"}


class VapiError(RuntimeError):
    pass


class VapiClient:
    def __init__(self, api_key: str, base_url: str = API_URL, timeout: float = 30):
        self._session = requests.Session()
        self._session.headers["Authorization"] = f"Bearer {api_key}"
        self._base_url = base_url
        self._timeout = timeout

    def create_call(self, assistant: dict, phone_number_id: str, customer_number: str) -> dict:
        """Запускает исходящий звонок. Возвращает объект звонка (status=queued)."""
        return self._request(
            "POST",
            "/call",
            json={
                "assistant": assistant,
                "phoneNumberId": phone_number_id,
                "customer": {"number": customer_number},
            },
        )

    def get_call(self, call_id: str) -> dict:
        return self._request("GET", f"/call/{call_id}")

    def ping(self) -> None:
        """Проверяет, что ключ API рабочий."""
        self._request("GET", "/assistant", params={"limit": 1})

    def get_phone_number(self, phone_number_id: str) -> dict:
        return self._request("GET", f"/phone-number/{phone_number_id}")

    def save_assistant(self, assistant: dict) -> tuple[dict, bool]:
        """Сохраняет ассистента в Vapi, чтобы с ним можно было поговорить из браузера.

        Для звонков на телефон это не нужно (там ассистент передаётся в самом
        запросе). Ассистент ищется по имени: есть — обновляем, нет — создаём.
        Возвращает (ассистент, создан ли новый).
        """
        assistants = self._request("GET", "/assistant", params={"limit": 100})
        existing = next((a for a in assistants if a.get("name") == assistant["name"]), None)
        if existing:
            return self._request("PATCH", f"/assistant/{existing['id']}", json=assistant), False
        return self._request("POST", "/assistant", json=assistant), True

    def wait_for_result(
        self,
        call_id: str,
        poll_seconds: float = 5,
        timeout_seconds: float = 900,
        analysis_grace_seconds: float = 60,
        on_status=None,
    ) -> dict:
        """Опрашивает звонок, пока он не закончится и не появятся извлечённые ответы.

        Ответы (structured outputs) Vapi считает уже после того, как трубку
        положили, поэтому после status=ended ждём ещё до analysis_grace_seconds.
        """
        deadline = time.monotonic() + timeout_seconds
        ended_at = None
        last_status = None
        while True:
            call = self.get_call(call_id)
            status = call.get("status")
            if status != last_status and on_status:
                on_status(status)
            last_status = status

            if status == "ended":
                ended_at = ended_at or time.monotonic()
                if (
                    (call.get("artifact") or {}).get("structuredOutputs")
                    or call.get("endedReason") in NO_CONVERSATION
                    or time.monotonic() - ended_at > analysis_grace_seconds
                ):
                    return call
            if time.monotonic() > deadline:
                raise VapiError(f"Звонок {call_id} не завершился за {timeout_seconds} с")
            time.sleep(poll_seconds)

    def _request(self, method: str, path: str, **kwargs) -> dict:
        response = self._session.request(method, self._base_url + path, timeout=self._timeout, **kwargs)
        if not response.ok:
            raise VapiError(f"Vapi {method} {path} → {response.status_code}: {response.text}")
        return response.json()
