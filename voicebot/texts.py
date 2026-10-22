"""Служебные фразы промпта и схемы на языке сценария.

Всё, что бот говорит и спрашивает, лежит в YAML. Здесь только обвязка вокруг
этого: заголовки промпта, пометки к вопросам, описания служебных полей.
Новый язык — новый словарь в TEXTS и `language: <код>` в YAML сценария.
"""

TEXTS = {
    "ru": {
        "questions": "# Вопросы\nЗадай их по порядку, по одному. Формулировки — ориентир, говори естественно.",
        "rules": "# Правила",
        "required": "[обязательный]",
        "ask_if": "Задавай, только если: {}.",
        "enum": "Ответ должен свестись к одному из вариантов: {}.",
        "note": "Подсказка: {}",
        "end_call": (
            "# Как завершить звонок\n"
            "Чтобы положить трубку, вызови инструмент endCall. "
            "Прощальную фразу («{end_message}») система скажет сама, не произноси её перед этим.\n"
            "Обязательные вопросы отмечены [обязательный]: не завершай разговор, пока не задал их, "
            "если только собеседник не отказался говорить или условие вопроса не выполнено."
        ),
        "schema": (
            "Ответы, полученные в телефонном разговоре. Заполняй поле только если собеседник "
            "действительно это сказал; если ответа не было — пропусти поле, не угадывай."
        ),
        "outcome": "Чем закончился звонок: ",
        "outcomes": {
            "completed": "получены ответы на все обязательные вопросы",
            "partial": "поговорили, но часть обязательных вопросов осталась без ответа",
            "no_service": "собеседник не оказывает нужную услугу",
            "callback_requested": "попросили перезвонить позже",
            "refused": "отказались разговаривать",
            "wrong_number": "не та организация или не тот номер",
            "no_human": "не удалось поговорить с человеком (автоответчик, меню, тишина)",
        },
        "callback_time": "Когда просили перезвонить, если просили. Иначе не заполняй.",
        "comment": (
            "Важные детали, которые не поместились в другие поля (условия, оговорки, "
            "диапазоны цен). Если таких нет — не заполняй."
        ),
        "summary": "Резюме разговора в 1–3 предложениях на русском.",
    },
    "en": {
        "questions": "# Questions\nAsk them in order, one at a time. The wording is a guide, speak naturally.",
        "rules": "# Rules",
        "required": "[required]",
        "ask_if": "Ask only if: {}.",
        "enum": "The answer must map to one of: {}.",
        "note": "Hint: {}",
        "end_call": (
            "# How to end the call\n"
            "To hang up, call the endCall tool. "
            'The system will say the goodbye ("{end_message}") itself, do not say it before that.\n'
            "Required questions are marked [required]: do not end the call until you have asked them, "
            "unless the person refused to talk or the question's condition is not met."
        ),
        "schema": (
            "Answers obtained in a phone conversation. Fill a field only if the person actually "
            "said it; if there was no answer, skip the field, do not guess."
        ),
        "outcome": "How the call ended: ",
        "outcomes": {
            "completed": "all required questions were answered",
            "partial": "we talked, but some required questions were not answered",
            "no_service": "they do not offer the service we need",
            "callback_requested": "they asked to call back later",
            "refused": "they refused to talk",
            "wrong_number": "wrong organisation or wrong number",
            "no_human": "could not reach a person (voicemail, phone menu, silence)",
        },
        "callback_time": "When they asked to be called back, if they did. Otherwise leave empty.",
        "comment": (
            "Important details that do not fit other fields (conditions, caveats, price ranges). "
            "Leave empty if there are none."
        ),
        "summary": "Summary of the conversation in 1-3 sentences in English.",
    },
}


def texts(language: str) -> dict:
    return TEXTS[language]
