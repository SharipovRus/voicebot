// Собирается командой `python -m voicebot site`, руками не править.
window.VOICEBOT = {
  "publicKey": "e1c14ff9-5fa6-4e1f-8e1a-ec66e156581f",
  "scenarios": [
    {
      "name": "abandoned_application",
      "language": "ru",
      "assistantId": "585c8ae0-9781-4515-b602-f9a59f398cd0",
      "firstMessage": "Здравствуйте! Меня зовут Алина, я голосовой ассистент банка «Не подозрительный банк». Вы недавно начали оформлять дебетовую карту в нашем приложении, но не закончили. Удобно минуту поговорить?",
      "demoHint": "Вы — клиент, который начал оформлять дебетовую карту в приложении банка и бросил на подтверждении личности. Отвечайте как угодно: назовите свою причину, откажитесь, попросите перезвонить или попробуйте продиктовать номер карты.",
      "questions": [
        "Вы остановились на шаге подтверждения личности. Подскажите, что помешало закончить?",
        "А что именно было неудобно или непонятно?",
        "Вам ещё интересно оформить дебетовую карту?",
        "Можно прислать SMS со ссылкой на этот номер, чтобы продолжить с того же места?",
        "Когда специалисту удобно вам перезвонить?"
      ],
      "analytics": "analytics/abandoned_application.html",
      "calls": 0
    },
    {
      "name": "abandoned_application_en",
      "language": "en",
      "assistantId": "36328326-1874-4b80-8faf-6cacd1290c80",
      "firstMessage": "Hi! My name is Alina, I'm a voice assistant at Not Shady Bank. You recently started applying for a debit card in our app but didn't finish. Do you have a minute to talk?",
      "demoHint": "You are a customer who started applying for a debit card in the bank's app and gave up at identity verification. Answer however you like: give your own reason, say no, ask to be called back, or try reading out a card number.",
      "questions": [
        "You stopped at the identity verification step. Could you tell me what got in the way?",
        "What exactly was inconvenient or unclear?",
        "Are you still interested in getting a debit card?",
        "Can we text a link to this number so you can continue where you left off?",
        "When would it suit you for a specialist to call you back?"
      ],
      "analytics": "analytics/abandoned_application_en.html",
      "calls": 0
    }
  ]
};
