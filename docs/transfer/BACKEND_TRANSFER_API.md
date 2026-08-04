# Transfer API — backend tayyor

**Status:** prod'da — `https://api.uzwellness.com`
**Branch:** `main` (`d9c1d9c`)
**OpenAPI:** `https://api.uzwellness.com/docs`

Spec bo'yicha hammasi bajarildi. Quyida 3 ta ataylab qilingan farq va integratsiya
uchun kerak bo'ladigan tafsilotlar.

Umumiy konventsiyalar o'zgarmagan: pul — string decimal, ro'yxatlar —
`{items, total, limit, offset}`, qisman yangilash — PATCH, tarjimalar —
`{uz, ru, en}` + `?include_translations=true`, `?currency=USD` yoki
`X-Currency` header bilan hamma narxda `display_price`/`display_currency`
qo'shiladi.

---

## 0. Spec'dan 3 ta farq

### 1. `PATCH /transfers/{id}` — bitta body, rolga qarab tekshiriladi

Ikkita alohida schema o'rniga bitta `TransferRequestUpdate` bor (OpenAPI'da
to'g'ri ko'rinishi va 422 xatolari normal ishlashi uchun).

Mijoz operator maydonini yuborsa → **403**, `detail` da qaysi maydon ekani
yozilgan:

```json
{ "detail": "Only the transfer operator can change: status, vehicle_id" }
```

Mijozga ruxsat etilgan maydonlar (boshqa hammasi operator uchun):

```
flight_number, flight_time, return_flight_number,
return_flight_time, notes, contact_phone
```

### 2. `POST /transfers` — `route_from_id`/`route_to_id` ixtiyoriy

Spec'da majburiy edi, lekin eski erkin-matnli transfer buyurtmalari
buzilmasligi uchun ixtiyoriy qoldirildi:

| Nima yuborsang | Nima bo'ladi |
|---|---|
| `route_from_id` + `route_to_id` | Joriy tarif bo'yicha narxlanadi, `applied_price` to'ladi |
| `pickup_location` + `dropoff_location` (matn) | Narxsiz — operator qo'lda `price` qo'yadi |

Ikkalasidan biri bo'lishi shart. Route id'lar birga yuborilishi kerak (bittasi
yolg'iz → 422). Ikkala holatda ham natija `payment_state: "unpaid"`.

### 3. `DELETE` locations/vehicles — ishlatilayotgan bo'lsa 409

Hard delete o'rniga:

```json
{ "detail": "Location is used by a tariff or transfer; set is_active=false instead of deleting it" }
```

Sabab: o'chirilsa eski bronlarning transfer tarixi uzilib qolardi. UI'da
"O'chirish" tugmasi 409 kelganda "Nofaol qilish" ni taklif qilsin.

---

## 1. Rol

`transfer_admin` — platformada **bitta**. `super_admin` ham transfer
endpoint'larining hammasiga kira oladi (zaxira sifatida).

`POST /api/users` va `PATCH /api/users/{id}` yangi maydon oldi:
`transfer_commission_percent` (string decimal, `"0.00"`–`"100.00"`).

```jsonc
// POST /api/users   (super_admin)
{
  "email": "transfer@uzwellness.com",
  "password": "...",
  "full_name": "Transfer Operator",
  "role": "transfer_admin",
  "transfer_commission_percent": "15.00"   // transfer_admin uchun majburiy
}
```

| Holat | Javob |
|---|---|
| Ikkinchi transfer_admin | `409` `{detail:{code:"transfer_admin_exists", existing_user_id}}` |
| Komissiyasiz transfer_admin | `422` |
| Boshqa rolga komissiya berish | `400` |
| transfer_admin → boshqa rol | `200`, komissiya avtomat `null` bo'ladi |

`UserRead` da ham `transfer_commission_percent` qaytadi (transfer_admin
bo'lmasa `null`).

---

## 2. Locations — `/api/transfer-locations`

| Metod | Auth |
|---|---|
| GET (ro'yxat, bitta) | **public** |
| POST / PATCH / DELETE | transfer_admin, super_admin |

```
GET /api/transfer-locations?is_active=true&kind=airport&include_translations=false&lang=ru
```

`kind`: `airport` \| `city` \| `sanatorium` \| `custom`

```jsonc
// GET (default) — nom resolved string
{ "items": [ {
    "id": "...", "name": "Аэропорт Ташкент", "kind": "airport",
    "is_active": true, "created_at": "...", "updated_at": "..."
} ], "total": 1, "limit": 50, "offset": 0 }

// GET ?include_translations=true — nom dict
{ "items": [ { "id": "...", "name": {"uz":"...","ru":"...","en":"..."}, ... } ] }
```

POST/PATCH **doim** dict shaklda qaytaradi (admin nima saqlanganini 3 tilda
ko'rishi uchun):

```jsonc
// POST — uchchala locale ham majburiy
{ "name": {"uz":"Toshkent aeroporti","ru":"Аэропорт Ташкент","en":"Tashkent Airport"},
  "kind": "airport", "is_active": true }

// PATCH — qisman, yuborilmagan locale o'zgarmaydi
{ "name": {"ru":"Международный аэропорт Ташкент"} }
```

---

## 3. Tariffs — `/api/transfer-tariffs`

**Versiyalanadi, tahrirlanmaydi.** PATCH/DELETE **yo'q**. Narxni o'zgartirish =
yangi POST: eski qator yopiladi (`effective_to` to'ladi), yangisi ochiladi —
bitta tranzaksiyada.

| Endpoint | Auth |
|---|---|
| `GET /api/transfer-tariffs` | login qilgan har kim |
| `GET /api/transfer-tariffs/current` | **public** |
| `POST /api/transfer-tariffs` | transfer_admin, super_admin |

```
GET /api/transfer-tariffs?route_from_id=..&route_to_id=..&vehicle_type=sedan&current_only=false
```
`effective_from desc` bo'yicha tartiblangan — bu **tarix ekrani**.

```jsonc
{
  "id": "...",
  "route_from_id": "...", "route_to_id": "...",
  "vehicle_type": "sedan",
  "price": "450000.00", "currency": "UZS",
  "display_price": "36.00", "display_currency": "USD",   // ?currency=USD bo'lsa
  "effective_from": "2026-07-30T17:40:00Z",
  "effective_to": null,        // null = joriy
  "is_current": true
}
```

### Checkout uchun eng muhimi

```
GET /api/transfer-tariffs/current?route_from_id=..&route_to_id=..&vehicle_type=sedan
```

- **200** → narx bor, add-on blokini ko'rsat
- **404** → bu yo'nalish/mashina uchun tarif yo'q, blokni **umuman ko'rsatma**

Auth kerak emas, ya'ni login qilmagan foydalanuvchiga ham ko'rsata olasan.

### `vehicle_type`

`sedan` \| `minivan` \| `bus` — tarif shu bo'yicha keyed. Mijoz mashina turini
tanlaydi, narx o'zgaradi.

### Round trip

Narx = **to'g'ri yo'nalish tarifi + teskari yo'nalish tarifi**. Uchinchi
o'lchov yo'q.

⚠️ Ya'ni `round_trip` ishlashi uchun operator **ikkala yo'nalishga ham** tarif
qo'ygan bo'lishi kerak. Quote ko'rsatayotganda ikkalasini ham so'ra:

```js
const [out, back] = await Promise.all([
  fetch(`/api/transfer-tariffs/current?route_from_id=${A}&route_to_id=${B}&vehicle_type=${v}`),
  fetch(`/api/transfer-tariffs/current?route_from_id=${B}&route_to_id=${A}&vehicle_type=${v}`),
]);
// bittasi 404 bo'lsa — round_trip variantini o'chir (submit'da 422 keladi)
```

---

## 4. Vehicles — `/api/transfer-vehicles`

Hammasi transfer_admin / super_admin. `GET ?is_active&vehicle_type`.

```jsonc
// POST
{ "vehicle_type": "minivan", "capacity": 7, "plate": "01 A 777 AA", "label": "Hyundai Staria" }
```

`plate` unique — takrorlansa `409`. Transferga biriktirilgan mashinani
o'chirsang `409`.

---

## 5. Checkout add-on — bron ichida transfer

`POST /api/bookings` va `POST /api/bookings/room-offer` ixtiyoriy `transfer`
blokini qabul qiladi. **Mijoz hech qachon narx yubormaydi.**

```jsonc
{
  "room_id": "...", "check_in": "2027-05-10", "check_out": "2027-05-13", "guests": 2,

  "transfer": {
    "route_from_id": "...",          // majburiy
    "route_to_id": "...",            // majburiy
    "vehicle_type": "sedan",         // majburiy
    "direction": "arrival",          // majburiy: arrival | departure | round_trip
    "passengers_count": 2,           // default 1
    "flight_number": "HY101",
    "flight_time": "2027-05-10T08:30:00Z",
    "return_flight_number": null,
    "return_flight_time": null,
    "notes": null,
    "contact_phone": "+998901234567"
  }
}
```

### Flight maydonlari qoidasi (422 bermaslik uchun)

| direction | `flight_time` | `return_flight_time` |
|---|---|---|
| `arrival` | **majburiy** | yuborish **mumkin emas** |
| `departure` | ixtiyoriy | yuborish **mumkin emas** |
| `round_trip` | **majburiy** | **majburiy**, `flight_time` dan keyin |

### Javob — `BookingRead` uchta yangi maydon oldi

```jsonc
{
  "id": "...", "code": "A7K2M9QX",
  "final_price": "340.00",        // ← transfer narxi ICHIDA
  "currency": "USD",

  "transfer_price": "40.00",      // transfer ulushi
  "transfer_currency": "USD",
  "transfer": {                   // to'liq TransferRequest obyekti
    "id": "...", "status": "requested", "payment_state": "included",
    "pickup_location": "Tashkent Airport", "dropoff_location": "Charvak Resort",
    "applied_price": "40.00", "applied_currency": "USD",
    "direction": "arrival", "vehicle_type": "sedan", ...
  }
}
```

Transfer yo'q bronlarda uchchalasi ham `null`.

### Muhim xulqlar

**Atomik.** Tarif topilmasa — **bron ham yaratilmaydi** (422 qaytadi, hech
narsa saqlanmaydi). Ya'ni "bron bo'ldi, transfer bo'lmadi" holati mumkin emas.

**Valyuta.** Tarif valyutasi bron valyutasidan farq qilsa, avtomat o'giriladi va
**o'girilgan summa** snapshot qilinadi. `transfer_currency` doim bron
valyutasiga teng bo'ladi. (Kurs yo'q bo'lsa `503`.)

**Narx submit paytida qayta hisoblanadi.** Quote ko'rsatgandan keyin operator
tarifni o'zgartirgan bo'lsa, backend jim yangi narxni qo'llaydi. Shuning uchun
javobdagi `transfer_price` ni quote'dagi bilan solishtir, farq bo'lsa toast
ko'rsat.

**Invoice.** `GET /api/bookings/{id}/invoice` → `line_items` ichida:
```jsonc
{ "description": "Transfer (Tashkent Airport → Charvak Resort)", "qty": 1, "amount": "40.00" }
```

**Bekor qilish.** Bron bekor qilinsa, bog'liq transfer avtomat `cancelled`
bo'ladi va moliyadan chiqadi.

---

## 6. Transfers — `/api/transfers`

```
GET /api/transfers?status=requested&payment_state=unpaid&booking_id=..&limit=20&offset=0
```

- `transfer_admin` / `super_admin` → **hammasini** ko'radi
- boshqalar → faqat o'zinikini

`status`: `requested` \| `confirmed` \| `completed` \| `cancelled`
`payment_state`: `included` \| `unpaid` \| `paid`

### `payment_state` ma'nosi

| Qiymat | Qachon | Pul |
|---|---|---|
| `included` | Checkout ichida qo'shilgan | Bron to'lovi bilan birga keldi |
| `unpaid` | Brondan keyin qo'shilgan | Hali olinmagan, offline hisob-kitob |
| `paid` | Operator qo'lda belgilagan | Olingan |

### POST — brondan keyin qo'shish

```jsonc
{
  "booking_id": "...",            // ixtiyoriy
  "route_from_id": "...",         // tarif narxi kerak bo'lsa
  "route_to_id": "...",
  "vehicle_type": "sedan",
  "direction": "departure",
  "flight_time": null,
  "contact_phone": "+998901234567"
}
```

Natija doim `payment_state: "unpaid"` — bron to'langan bo'lsa ham to'lov qayta
ochilmaydi (single-payment oqimi buzilmasin).

### PATCH — rolga qarab

```jsonc
// operator
{ "status": "confirmed", "vehicle_id": "...", "driver_name": "Aziz",
  "driver_phone": "+998...", "payment_state": "paid", "admin_notes": "..." }

// mijoz — faqat shu 6 ta maydon
{ "flight_number": "HY202", "flight_time": "...", "contact_phone": "..." }
```

Operator `status` ni `confirmed` qilganda yoki `driver_name` ni birinchi marta
to'ldirganda mijozga **email ketadi** (avtomat, front tomondan hech narsa
kerak emas).

`vehicle_id` mavjud va `is_active` bo'lishi kerak, aks holda `422`.

### `POST /api/transfers/{id}/cancel`

`requested` yoki `confirmed` holatidan ishlaydi. Boshqasida `409`.

### `TransferRequestRead` — to'liq maydonlar

```
id, user_id, booking_id, direction, status, payment_state,
pickup_location, dropoff_location,          // matn snapshot
route_from_id, route_to_id, vehicle_id,     // strukturali
flight_number, flight_time, return_flight_number, return_flight_time,
passengers_count, vehicle_type,
price, currency,                            // eski qo'lda qo'yiladigan narx
applied_tariff_id, applied_price, applied_currency,   // tarifdan
display_price, display_currency,
driver_name, driver_phone, notes, admin_notes, contact_phone,
created_at, updated_at
```

⚠️ Narxni ko'rsatishda **`applied_price` ni ustun qo'y**, u `null` bo'lsagina
`price` ga tush. `display_price` allaqachon shu mantiq bilan hisoblangan.

---

## 7. Finance — `/api/transfer-finance`

transfer_admin + super_admin. `?date_from&date_to&currency`.

```jsonc
// GET /summary
{ "items": [ {
    "currency": "USD",
    "order_count": 2,
    "gross_amount": "80.00",
    "platform_commission_percent": "15.00",  // hamma qatorda bir xil bo'lmasa null
    "platform_commission_amount": "12.00",
    "net_payout_amount": "68.00",
    "unpaid_amount": "40.00"
} ] }
```

```jsonc
// GET /orders  → {items,total,limit,offset}
{
  "transfer_id": "...", "booking_id": "...", "booking_code": "A7K2M9QX",
  "direction": "departure", "vehicle_type": "sedan",
  "pickup_location": "...", "dropoff_location": "...",
  "status": "requested", "payment_state": "included",
  "gross_amount": "40.00",
  "platform_commission_percent": "15.00",
  "platform_commission_amount": "6.00",
  "net_payout_amount": "34.00",
  "currency": "USD", "created_at": "..."
}
```

- Bekor qilingan transferlar **umuman chiqmaydi**
- Narxsiz (qo'lda narxlanmagan) transferlar ham chiqmaydi
- Komissiya har transferga **snapshot** qilingan — foizni keyin o'zgartirish
  eski buyurtmalarga ta'sir qilmaydi
- `net_payout_amount = gross_amount − platform_commission_amount`

---

## 8. Xato kodlari

| HTTP | `detail` | Qachon |
|---|---|---|
| 409 | `{code:"transfer_admin_exists", existing_user_id}` | Ikkinchi transfer_admin |
| 422 | `{code:"no_tariff_for_route", route_from_id, route_to_id, vehicle_type}` | Tarif yo'q |
| 422 | `{code:"tariff_currency_mismatch", message}` | round_trip'da ikki oyoq har xil valyutada |
| 422 | matn | Validatsiya (flight qoidalari, route id'lar, va h.k.) |
| 403 | `"Only the transfer operator can change: ..."` | Mijoz operator maydoniga tegdi |
| 409 | matn | Ishlatilayotgan location/vehicle o'chirish, dublikat plate, bekor qilib bo'lmaydigan status |
| 503 | matn | Valyuta kursi yo'q |

`detail` ba'zan **string**, ba'zan **object** — `code` bor-yo'qligini tekshirib
ishlat.

---

## 9. Ishga tushirish tartibi

Bo'sh bazada checkout add-on bloki **ko'rinmaydi** — bu xato emas. Operator
quyidagilarni to'ldirmaguncha `/transfer-tariffs/current` doim 404 qaytaradi:

1. `super_admin` → `transfer_admin` user yaratadi (komissiya foizi bilan)
2. `transfer_admin` → locations qo'shadi (aeroport, sanatoriylar, shaharlar)
3. `transfer_admin` → har yo'nalish + mashina turi uchun tarif qo'yadi
   (round trip kerak bo'lsa — **teskari yo'nalishga ham**)
4. `transfer_admin` → mashinalarni qo'shadi (ixtiyoriy, faqat biriktirish uchun)

Portal UI shu tartibni ko'rsatsa yaxshi bo'lardi — bo'sh holatda "avval
location qo'shing" kabi.

---

## 10. Savol bo'lsa

`https://api.uzwellness.com/docs` — to'liq OpenAPI, hamma schema va misollar
o'sha yerda. Lokal ishlatmoqchi bo'lsang: repo'ni klon qilib
`uv run fastapi dev app/main.py --port 8080` → `localhost:8080/docs`.
