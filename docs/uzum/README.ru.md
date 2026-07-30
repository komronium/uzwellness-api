# Uzum Bank Merchant API — интеграция UzWellness

Документ для команды Uzum Bank: всё, что нужно для ручного тестирования.
Реализация соответствует спецификации <https://developer.uzumbank.uz/merchant>.

## 1. Callback URL

```
https://api.uzwellness.com/api/payments/uzum
```

Эндпоинты (все — `POST`, `Content-Type: application/json`):

| Метод | URL |
|---|---|
| Проверка | `POST https://api.uzwellness.com/api/payments/uzum/check` |
| Создание | `POST https://api.uzwellness.com/api/payments/uzum/create` |
| Подтверждение | `POST https://api.uzwellness.com/api/payments/uzum/confirm` |
| Отмена | `POST https://api.uzwellness.com/api/payments/uzum/reverse` |
| Статус | `POST https://api.uzwellness.com/api/payments/uzum/status` |

## 2. Авторизация

HTTP Basic, заголовок обязателен в каждом запросе:

```
Authorization: Basic base64(<username>:<password>)
```

Логин, пароль и `serviceId` передаются отдельным защищённым сообщением
(в репозитории они не хранятся). На стороне UzWellness они задаются
переменными окружения `UZUM_MERCHANT_USERNAME`, `UZUM_MERCHANT_PASSWORD`,
`UZUM_SERVICE_ID`.

## 3. Идентификатор платежа (`params`)

Клиент вводит в приложении Uzum **номер бронирования** — 16 цифр,
например `2607301100123456`. Он передаётся так:

```json
"params": { "order_id": "2607301100123456" }
```

Дополнительно принимаются ключи `orderId`, `account`, `booking_code`, `code` —
на случай, если в приложении поле называется иначе. По `booking_code`
работает и короткий код брони из 8 символов (например `A7K2M9QX`).

Тестовая бронь для ручного прогона выдаётся вместе с учётными данными.

## 4. Сумма

`amount` — **в тийинах**, валюта только **UZS**. Сумма должна точно совпадать
с суммой брони, иначе возвращается `10011`. Если бронь номинирована в USD,
она пересчитывается по курсу ЦБ РУз на момент запроса.

Пример: бронь на 1 250 000 UZS → `"amount": 125000000`.

## 5. Модель состояний

```
/create → CREATED ──/confirm──→ CONFIRMED ──/reverse──→ REVERSED (возврат)
             │
             ├──/reverse──→ REVERSED (отмена без списания)
             └── 30 минут без /confirm → FAILED
```

Повторный `/create` для брони, по которой уже есть активная транзакция или
успешная оплата, возвращает `10008`.

## 6. Формат ответов

Успех — HTTP `200`:

```json
{
  "serviceId": 123123,
  "transId": "5c398d7e-76b6-11ee-96da-f3a095c6289d",
  "status": "CONFIRMED",
  "confirmTime": 1698361458054,
  "data": {
    "order_id": { "value": "2607301100123456" },
    "property":  { "value": "Charvak Resort" },
    "guest":     { "value": "Ali Valiyev" },
    "check_in":  { "value": "2026-08-01" },
    "check_out": { "value": "2026-08-08" }
  },
  "amount": 125000000
}
```

Ошибка — HTTP `400`:

```json
{
  "serviceId": 123123,
  "transId": "5c398d7e-76b6-11ee-96da-f3a095c6289d",
  "status": "FAILED",
  "confirmTime": 1698361458054,
  "errorCode": "10014"
}
```

## 7. Реализованные коды ошибок

| Код | Когда возвращается |
|---|---|
| `10001` | Нет заголовка `Authorization`, неверная схема или неверные логин/пароль |
| `10002` | Тело запроса — не валидный JSON или не JSON-объект |
| `10003` | Вебхук вызван не методом `POST` |
| `10005` | Нет обязательного поля или в `params` нет `order_id` |
| `10006` | `serviceId` не совпадает с выданным |
| `10007` | Бронь с таким `order_id` не найдена |
| `10008` | Бронь уже оплачена либо по ней есть активная транзакция |
| `10009` | Бронь отменена |
| `10010` | Транзакция с таким `transId` уже создана |
| `10011` | `amount` не совпадает с суммой брони (или ≤ 0) |
| `10014` | `transId` неизвестен; также для `/status` по «протухшей» транзакции |
| `10015` | `/confirm` по отменённой, возвращённой или просроченной транзакции; бронь отменена |
| `10016` | `/confirm` по уже подтверждённой транзакции |
| `10017` | `/reverse` по транзакции в состоянии FAILED |
| `10018` | `/reverse` по уже отменённой транзакции |
| `99999` | Внутренняя ошибка (например, недоступен курс валюты) |

## 8. Postman

Коллекция: [`uzwellness-uzum-merchant.postman_collection.json`](./uzwellness-uzum-merchant.postman_collection.json).

Перед запуском заполните переменные коллекции: `username`, `password`,
`serviceId`, `orderId`. `transId` генерируется автоматически в запросе
`Create`. Порядок прогона: **Check → Create → Confirm → Status**; сценарий
отмены: **Check → Create → Reverse → Status**. Папка «Негативные сценарии»
проверяет коды `10001`, `10006`, `10007`, `10011`, `10014`.
