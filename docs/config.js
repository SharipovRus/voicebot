// Собирается командой `python -m voicebot site`, руками не править.
window.VOICEBOT = {
  "publicKey": "e1c14ff9-5fa6-4e1f-8e1a-ec66e156581f",
  "scenarios": [
    {
      "name": "car_service_en",
      "language": "en",
      "assistantId": "45248497-ac85-4bd4-80c1-f35b135a601e",
      "firstMessage": "Hi! My name is Alina, I'm a voice assistant calling on behalf of a customer. Do you have a minute for a couple of quick questions about a car service?",
      "questions": [
        "Can you change the engine oil and the oil filter? The car is a 2018 Volkswagen Golf with the 1.4 TSI engine.",
        "How much will it cost in total, including oil, filter and labour?",
        "Can the customer bring their own oil?",
        "When is the earliest available slot to bring the car in?",
        "How long will the job take?",
        "What is your address?"
      ],
      "analytics": "analytics/car_service_en.html",
      "calls": 0
    },
    {
      "name": "sto_service",
      "language": "ru",
      "assistantId": "242906a2-a8df-49e6-b2f0-edfc2491c702",
      "firstMessage": "Здравствуйте! Меня зовут Алина, я голосовой ассистент, звоню по поручению клиента. Удобно ответить на пару вопросов про обслуживание автомобиля?",
      "questions": [
        "Можно ли у вас заменить моторное масло и масляный фильтр? Машина — Toyota Camry 2018 года с двигателем 2.5.",
        "Сколько это будет стоить в итоге — с маслом, фильтром и работой?",
        "Можно ли приехать со своим маслом?",
        "Когда ближайшее свободное время, чтобы приехать?",
        "Сколько по времени займёт работа?",
        "Подскажите ваш адрес?"
      ],
      "analytics": "analytics/sto_service.html",
      "calls": 0
    }
  ]
};
