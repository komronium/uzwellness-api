# Uzum Checkout — frontend uchun qo'llanma

Saytdagi karta to'lovi. Frontend uchun bor-yo'g'i **2 ta endpoint**: to'lovni
ochish va holatni tekshirish. Uzum bilan gaplashish backend zimmasida —
frontend `X-API-Key`, `amount`, `orderNumber` kabi narsalarga hech qachon
tegmaydi.

Base URL: `https://api.uzwellness.com/api` (lokal: `http://localhost:8080/api`)

---

## 1. To'lovni ochish

```http
POST /payments/uzum-checkout/create
Authorization: Bearer <access_token>
Content-Type: application/json

{ "booking_id": "019ff6aa-...", "locale": "ru" }
```

`locale` — ixtiyoriy (`uz` | `ru` | `en`), Uzum to'lov formasining tili.
Yuborilmasa `?lang=` yoki `Accept-Language` ishlatiladi.

**200 OK**

```json
{
  "payment_id": "019ff6aa-2778-76a3-9d64-6b17c12568a7",
  "booking_id": "019ff6a9-...",
  "order_id": "629e892c-a55a-4428-be75-b4043bd950e7",
  "order_number": "2608120101061053-019ff6aa",
  "payment_url": "https://checkout.ipt-merch.com/?orderId=...",
  "amount": "1200000.00",
  "currency": "UZS",
  "status": "pending"
}
```

Keyin mijozni **`payment_url`** ga yuborasiz:

```js
window.location.href = data.payment_url;   // yoki window.open(...)
```

> `payment_id` ni saqlab qo'ying (localStorage/URL query) — qaytib kelganda
> holatni shu bo'yicha so'raysiz.

### Xatolar

| Kod | Ma'nosi | Frontend nima qiladi |
|---|---|---|
| `401` | token yo'q/eskirgan | login'ga yuboradi |
| `403` | bron boshqa mijoznikida | xato ko'rsatadi |
| `404` | bron topilmadi | xato ko'rsatadi |
| `409` | bron allaqachon to'langan yoki bekor qilingan | bron sahifasiga qaytaradi |
| `502` | Uzum so'rovni rad etdi (`detail` da sabab) | "keyinroq urinib ko'ring" |
| `503` | Checkout sozlanmagan yoki valyuta kursi yo'q | to'lov tugmasini yashiradi |

Bir bronni ikki marta `create` qilsangiz **yangi order ochilmaydi** — ochiq
forma bo'lsa o'sha `payment_url` qaytadi. Ya'ni "Оплатить" tugmasini qayta
bosish xavfsiz.

---

## 2. Qaytib kelgandan keyin holatni tekshirish

Uzum mijozni `successUrl` yoki `failureUrl` ga qaytaradi (hozircha
`https://uzwellness.com/payment/success` va `.../payment/failure`).

⚠️ **`successUrl` ga tushish "to'landi" degani emas.** Uzum bir vaqtning o'zida
bizga callback yuboradi, mijoz esa redirect bilan keladi — kim oldin yetib
kelishi noma'lum. Shuning uchun sahifa **doim so'raydi**:

```http
GET /payments/uzum-checkout/payments/{payment_id}
Authorization: Bearer <access_token>
```

```json
{
  "payment_id": "019ff6aa-...",
  "booking_id": "019ff6a9-...",
  "order_id": "629e892c-...",
  "status": "paid",
  "order_status": "COMPLETED",
  "amount": "1200000.00",
  "currency": "UZS"
}
```

Bu endpoint har chaqirilganda Uzumdan holatni **qayta o'qiydi**, shuning uchun
javob doim eng yangi.

| `status` | `order_status` | Mijozga |
|---|---|---|
| `pending` | `REGISTERED` | "To'lov kutilmoqda" + 2–3 soniyada qayta so'rash (~30 s davomida) |
| `paid` | `COMPLETED` | ✅ "To'landi", bron `confirmed` bo'ldi, email ketdi |
| `failed` | `DECLINED` | ❌ "To'lov rad etildi" + qayta urinish tugmasi (`create` ni qayta chaqiradi) |
| `refunded` | `REFUNDED` | "Pul qaytarildi" |

Polling namunasi:

```js
async function waitForPayment(paymentId, { tries = 10, delayMs = 3000 } = {}) {
  for (let i = 0; i < tries; i++) {
    const r = await api.get(`/payments/uzum-checkout/payments/${paymentId}`);
    if (r.status !== "pending") return r;      // paid | failed | refunded
    await new Promise((res) => setTimeout(res, delayMs));
  }
  return null;                                  // hali ham pending
}
```

`null` qaytsa — "To'lov tekshirilmoqda, natijani emailda yuboramiz" deb
yozing, panic qilmang: backend callback orqali baribir yakunlaydi.

---

## 3. Test qilish

Sandbox terminalda (`test-chk-api.uzumcheckout.uz`) test kartalar:

| Karta | Raqam | Amal qilish | 3-DS |
|---|---|---|---|
| HUMO | `9860 0901 0121 9724` | 10/26 | `777777` |
| UzCard | `8600 3129 2957 7175` | 09/26 | `777777` |

Haqiqiy pul ketmaydi. To'lov formasi Uzum domenida ochiladi (`UzWellness` nomi
va summa ko'rinadi).

---

## 4. Nima **kerak emas**

- Uzumga to'g'ridan-to'g'ri so'rov yubormang (`X-API-Key` frontendga hech qachon
  berilmaydi).
- Summani o'zingiz hisoblamang va yubormang — backend bronning `final_price`
  idan oladi va kerak bo'lsa UZS ga o'giradi.
- `successUrl` dagi query parametrlarga ishonmang — holat faqat 2-banddagi
  endpointdan olinadi.
- Naqd to'lov boshqa oqim: `POST /payments/initiate` (`method: "cash"`).

---

## 5. Lokal test qilish (frontend dev uchun)

### 5.1. Backendni ko'tarish

```bash
# Postgres (bir marta)
docker run -d --name uzwellness-pg \
  -e POSTGRES_USER=sanotour -e POSTGRES_PASSWORD=sanotour \
  -e POSTGRES_DB=sanotour -p 5432:5432 postgres:16-alpine
# keyingi safar: docker start uzwellness-pg

cd uzwellness-api
uv run alembic upgrade head
uv run python -m scripts.demo_data     # demo sanatoriya/xona/foydalanuvchilar
uv run fastapi dev app/main.py --port 8080
```

`.env` da Uzum sandbox kredensiallari allaqachon turibdi
(`UZUM_CHECKOUT_API_URL=https://test-chk-api.uzumcheckout.uz`). Agar
`POST .../create` **503** qaytarsa — `.env` da `UZUM_CHECKOUT_TERMINAL_ID` /
`UZUM_CHECKOUT_API_KEY` bo'sh, backendchidan so'rang.

Swagger: `http://localhost:8080/docs`.

### 5.2. Tunnel (ngrok) **kerak emas**

Uzum callback'i `localhost` ga yeta olmaydi — lekin bu lokal testga xalaqit
bermaydi: `GET /payments/uzum-checkout/payments/{payment_id}` **Uzumning
o'zidan** holatni so'raydi. Ya'ni callback kelmasa ham to'lov `paid` bo'ladi.

### 5.3. To'liq oqim

```bash
API=http://localhost:8080/api

# 1) login (demo customer)
TOKEN=$(curl -s -X POST $API/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"ali@gmail.com","password":"User123!"}' | jq -r .access_token)

# 2) bron yaratish (yoki UI orqali) → booking_id ni oling
#    GET $API/rooms/search ... POST $API/bookings ...

# 3) to'lovni ochish
curl -s -X POST $API/payments/uzum-checkout/create \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"booking_id":"<BOOKING_ID>","locale":"ru"}' | jq
```

`payment_url` ni brauzerda oching va test kartani kiriting:

| Karta | Raqam | Amal qilish | 3-DS |
|---|---|---|---|
| HUMO | `9860 0901 0121 9724` | `10/26` | `777777` |
| UzCard | `8600 3129 2957 7175` | `09/26` | `777777` |

Haqiqiy pul ketmaydi.

```bash
# 4) holatni tekshirish
curl -s $API/payments/uzum-checkout/payments/<PAYMENT_ID> \
  -H "Authorization: Bearer $TOKEN" | jq
# {"status":"paid","order_status":"COMPLETED", ...}
```

### 5.4. To'lovdan keyin qayerga tushasiz

Sandbox terminalda `successUrl`/`failureUrl` — `https://uzwellness.com/...`
(Uzum faqat **https** qabul qiladi, `http://localhost` ni `2000` bilan rad
etadi). Shuning uchun to'lovdan keyin brauzer prod domenga tushadi — bu lokal
testda normal holat. O'z sahifangizni tekshirish uchun `payment_id` ni qo'lda
qo'ying:

```
http://localhost:3000/payment/success?payment_id=<PAYMENT_ID>
```

Agar redirect'ning o'zini ham lokal sinamoqchi bo'lsangiz — backendchidan
`.env` dagi `UZUM_CHECKOUT_SUCCESS_URL` / `FAILURE_URL` ni ngrok'ning https
manziliga o'zgartirishni so'rang.

### 5.5. Holatlarni ataylab hosil qilish

| Ssenariy | Qanday qilinadi | Kutilgan natija |
|---|---|---|
| Muvaffaqiyatli to'lov | test karta + 3-DS `777777` | `status: paid`, bron `confirmed` |
| Bekor qilish | to'lov formasidagi ❌ tugmasi | `status: pending` → forma yopildi, qayta `create` mumkin |
| Sessiya tugashi | 15 daqiqa kutish | `status: pending`, keyin `create` yangi order ochadi |
| Ikki marta `create` | tugmani ikki marta bosish | o'sha `payment_id` va URL qaytadi |
| Allaqachon to'langan | to'langan bronga yana `create` | `409` |
| Begona bron | boshqa user tokeni bilan `create` | `403` |

### 5.6. Tez-tez uchraydigan xatolar

| Belgi | Sabab |
|---|---|
| `401` | token eskirgan — `/auth/refresh` |
| `502` va `detail` da `3045` | terminalda auto-fiskalizatsiya yoqiq, backend `.env` da IKPU kodlari to'ldirilmagan |
| `502` va `detail` da `2000` | so'rov validatsiyadan o'tmadi (masalan `successUrl` https emas) — backendchiga ayting |
| `503` | Checkout sozlanmagan yoki `USD_UZS` kursi yo'q (`GET /exchange-rates`) |
| CORS xatosi | `.env` dagi `CORS_ORIGINS` ga sizning origin'ingiz qo'shilmagan |
