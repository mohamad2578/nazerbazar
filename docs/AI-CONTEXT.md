# ناظر ۷۲۴ — راهنمای توسعه‌دهنده و هوش مصنوعی

این فایل را **قبل از هر تغییر** بخوانید. هدفش این است که بدون حدس‌زدن بتوانید پروژه را توسعه دهید:
قواعد تغییرناپذیر، نقشه کد، جریان‌های حساس (پول، موجودی، پرداخت)، دام‌ها و وضعیت راستی‌آزمایی‌شده.
معرفی محصول و نقش‌ها در [README.md](../README.md) است.

> مخزن عمومی است. هیچ رمز، کلید API، گذرواژه سرور یا شماره/آدرس شخصی در کد یا مستندات نگذارید
> (کلید امضای اندروید و مقدارهای Secret در `mobile/keystore/` است که در گیت نیست).

## ۱. یک‌نگاه

| | |
|---|---|
| بک‌اند | Django 5.2 + DRF، JWT، PostgreSQL 16 (محلی: SQLite)، `backend/` |
| فرانت | React 19 + Vite + TypeScript + Tailwind 4 + TanStack Query، PWA، همه‌جا RTL فارسی، `frontend/` |
| موبایل | Capacitor 7: پوشش وب. دو اپ از یک پروژه: «ناظر ۷۲۴» (`customer`) و «ناظر پیک» (`courier`)، `mobile/` |
| استقرار | `docker compose` (`db`, `backend`, `scheduler`, `web`)؛ nginx سرور جلوی آن؛ `deploy/` |
| زبان رابط/پیام‌ها | فارسی. پیام خطای API فارسی است و فرانت همان را نمایش می‌دهد |

اجرا و آزمون:

```bash
cd backend && python manage.py test                      # ~۱۵۰ آزمون، ۱ تا ۲ دقیقه
python manage.py test apps.core.test_fuzz                # آزمون ورودی خراب روی همه نشانی‌ها
cd frontend && npx tsc -b && npm run build               # تایپ‌چک + ساخت نهایی (همان کاری که Dockerfile می‌کند)
```

ویندوز: برای چاپ فارسی در ترمینال `PYTHONIOENCODING=utf8 PYTHONUTF8=1` بگذارید.

## ۲. قواعد تغییرناپذیر (نقض نکنید)

1. **پول:** در دیتابیس و API همیشه **ریال** (عدد صحیح). نمایش و ورودی کاربر **تومان** است (`toToman/toRial/toman()` در `frontend/src/lib/format.ts`). هرگز float برای پول.
2. **داده واقعی روی سرور:** فروشگاه‌ها و قیمت‌های واقعی ثبت شده است. دستورهای `reset_stores` و `reset_products` را روی سرور **نزنید**. مایگریشن فقط افزایشی (ستون جدید با مقدار پیش‌فرض)؛ حذف/تغییر نوع ستون ممنوع مگر با برنامه مهاجرت داده.
3. **حوزه دسترسی:** هر کاربر فقط داده حوزه خود را می‌بیند (`apps/core/scoping.py`؛ هر مدل `SCOPE` دارد). ViewSet جدید پنل از `ScopedModelViewSet` ارث می‌برد.
4. **داده حساس هرگز در پاسخ عمومی یا نقش نظارتی نیاید:** `cost_price`، `stock`، `min_stock` (فقط مالک/مدیر کل)، نشانی/مختصات/تلفن مشتری (فقط مالک فروشگاه، پیک اختصاص‌یافته و خود مشتری)، رمز/کلیدهای درگاه (فقط مالک فروشگاه).
5. **شبیه‌ساز پرداخت** (`PAYMENT_BACKEND=console`) فقط وقتی کار می‌کند که `DEBUG` یا `PAYMENT_ALLOW_MOCK` روشن باشد. روی سرور واقعی روشنش نکنید؛ هر کسی می‌تواند «پرداخت موفق» جعل کند.
6. **فروشگاه ویژه** (`Store.is_featured`، فقط مدیر کل تعیین می‌کند): بدون اتحادیه؛ محصولاتش بدون تایید صمت؛ **فقط پرداخت اینترنتی و فقط ارسال با پیک**؛ سفارش ارسالی موقعیت نقشه می‌خواهد. این قواعد در `order_services.place_order` اعمال می‌شود (سمت سرور، نه فقط UI).
7. **موجودی فقط از `apps/shop/inventory.py → record()` تغییر می‌کند** (فروش، لغو، خرید، تعدیل). مستقیم روی `ShopProduct.stock` ننویسید؛ دفتر انبار با موجودی از هم می‌پاشد. `stock=None` یعنی نامحدود (بدون ردیف دفتر).
8. **API فقط شیء JSON می‌پذیرد** (`StrictJSONParser`)؛ تنها استثنا `/api/store/offers/` که فهرست می‌گیرد. هر ورودی کاربر باید اعتبارسنجی شود؛ آزمون `test_fuzz` هر نشانی را با ورودی خراب می‌زند و ۵۰۰ را رد می‌کند.
9. **تست:** هر قاعده/باگ جدید آزمون می‌خواهد. آزمون‌ها در `apps/core/tests.py` (کلاس‌ها به ترتیب فیچر) و `apps/core/test_fuzz.py` است. قبل از commit کل مجموعه سبز باشد.

## ۳. نقشه بک‌اند (`backend/apps/`)

| اپ | مسئولیت |
|---|---|
| `core` | `TimeStamped`، `SystemSettings` (تنظیمات مدیر کل)، `scoping.py` (حوزه دسترسی)، `views.py` (`ScopedModelViewSet`)، `sms.py` (قاصدک/کاوه‌نگار)، `parsers.py`، `exceptions.py` (شبکه ایمنی ۴۰۰)، `backup.py`، دستورهای seed/`daily_jobs` |
| `accounts` | کاربر، نقش‌ها، OTP، اعلان (`notify`) |
| `orgs` | استان/شهرستان/اتاق/اتحادیه/فروشگاه و کارتابل تایید فروشگاه |
| `market` | کالای اساسی و نرخ مصوب (تایید دومرحله‌ای)، قیمت فروشگاه‌ها، کالای خدماتی و نرخ‌نامه، snapshot روزانه، API عمومی سایت |
| `shop` | فروشگاه اینترنتی: محصول، بسته، سفارش، کیف پول، پرداخت، پیک، انبار و حسابداری فروشگاه ویژه (بخش ۴) |
| `complaints` · `observatory` · `distribution` | شکایت، رصد بازار و هشدار، توزیع کالای تنظیم بازار |
| `analytics` · `visits` | گزارش‌های تحلیلی/اکسل، آمار بازدید |
| `cms` · `news` · `suppliers` | اسلاید صفحه اصلی، اخبار، ثبت‌نام تامین‌کنندگان |

نشانی‌ها: `config/urls.py` (ترتیب مهم است؛ توضیح بالای فایل). مستندات خودکار: `/api/docs/`.

## ۴. ماژول `shop` (حساس‌ترین بخش)

| فایل | نقش |
|---|---|
| `models.py` | `ShopProduct` (قیمت، `old_price`=قیمت مصرف‌کننده، `stock`, `per_user_limit`, `cost_price`, `min_stock`, `order`=الویت نمایش) |
| `orders.py` | `Order` (وضعیت‌ها، پرداخت، `tax`, `delivery_fee`, `invoice_no`, پیک)، `OrderItem` (قیمت و **قیمت تمام‌شده در لحظه فروش**)، `OrderEvent` |
| `order_services.py` | **منطق سفارش**: `place_order`، `start_online_payment`، `mark_order_paid`، لغو/بازگشت وجه، `expire_unpaid_orders`، `change_order_status` |
| `order_api.py` | API سفارش، کیف پول، بازگشت درگاه، نشانی‌ها، فاکتور |
| `payments.py` | درگاه‌ها (`zarinpal`, `zibal`, `console`)، درگاه **اختصاصی هر فروشگاه** (`StoreSettings.gateway_*`)، تایید پرداخت idempotent |
| `wallet.py` | کیف پول (فقط `credit`/`debit`، با قفل ردیف، هرگز منفی) |
| `commerce.py` | `ShopBundle`، `Wallet/WalletTx`، `Payment`، `UserAddress`، `Courier` |
| `courier_services.py` / `courier_api.py` | پیک: ارسال لیست، تحویل‌گرفتن، تحویل، تحویل ناموفق، حساب و تسویه، اپ پیک |
| `erp.py` | مدل‌های انبار/حسابداری: `StoreSettings`، `Supplier`، `StockMovement`، `PurchaseInvoice`، `SupplierPayment`، `Expense`، `CourierSettlement` |
| `inventory.py` | **تنها راه تغییر موجودی**: `record`، `adjust`، `create_purchase` (میانگین موزون با حمل و تخفیف)، شماره فاکتور |
| `erp_reports.py` | گزارش سود و زیان، موجودی، بدهی تامین‌کنندگان، حساب پیک، داشبورد |
| `erp_api.py` | API انبار و حسابداری (فقط مالک فروشگاه ویژه: `featured_store()`)، خروجی CSV |

### جریان سفارش

`place_order` (تراکنش، قفل `select_for_update` روی کالاها) → کنترل موجودی/سقف خرید → محاسبه (تخفیف بسته، مالیات، ارسال) → کسر موجودی از دفتر →
**بعد از commit** `start_online_payment` (تماس HTTP با درگاه؛ هرگز داخل تراکنش) → کاربر به درگاه می‌رود → `public/payments/callback/` →
`payments.verify` (همیشه از درگاه می‌پرسد؛ آدرس بازگشت قابل جعل است) → `mark_order_paid` → سفارش در کارتابل فروشگاه (`new`).

وضعیت‌ها: `awaiting_payment → new → confirmed → preparing → ready → out_for_delivery → delivered`، و `canceled`.
لغو: موجودی برمی‌گردد؛ پرداخت‌شده به **کیف پول** برمی‌گردد (نه حساب بانکی؛ در فروشگاه ویژه کیف پول قابل مصرف نیست؛ سیاست تسویه بانکی تصمیم باز است).
پرداخت دوم برای سفارش پرداخت‌شده به کیف پول برمی‌گردد. سفارش پرداخت‌نشده پس از ۳۰ دقیقه لغو می‌شود (`daily_jobs` هر ساعت + دیدن ویترین).

### انبار و حسابداری (تعریف‌ها)

- درآمد کالا = Σ(قیمت×تعداد) − تخفیف بسته؛ بدون مالیات و ارسال. بهای تمام‌شده = Σ(`OrderItem.cost_price`×تعداد) (قیمت لحظه فروش، نه امروز).
- سود ناخالص = درآمد − بهای تمام‌شده؛ سود خالص = ناخالص + درآمد ارسال − کارمزد پیک − هزینه‌ها. فقط سفارش `delivered` حساب می‌شود (بر اساس `delivered_at`).
- قیمت تمام‌شده = میانگین موزون خریدها؛ حمل (+) و تخفیف (−) فاکتور به نسبت ارزش ردیف‌ها تسهیم می‌شود. فاکتور خرید ویرایش/ابطال ندارد؛ اصلاح با «تعدیل».
- کارمزد درگاه در سود محاسبه **نمی‌شود**.
- پیک: `cash_on_hand` = نقد دریافتی (سفارش نقدی تحویل‌شده) − تحویل‌شده به فروشگاه؛ `fee_due` = کارمزد کسب‌شده − پرداخت‌شده. (فروشگاه ویژه فقط اینترنتی است، پس نقد برای آن تقریبا صفر است.)

### سایر قواعد مهم

- قیمت‌گذاری کالای اساسی و تایید نرخ: `market/services.py` (اتحادیه → در انتظار تایید اتاق؛ صمت و بالاتر بی‌درنگ). تغییر نرخ: پیامک قاصدک به فروشگاه‌های دارای قیمت (`core/sms.py`، قالب `GHASEDAK_PRICE_TEMPLATE`)، بدون پنهان‌شدن کالا. `SystemSettings.snap_store_prices` تعیین می‌کند قیمت فروشگاه‌ها با نرخ جدید هم‌تراز شود یا نه.
- نقش‌ها و ارتباط داده: `accounts.Role`؛ پیک نقش جدا ندارد (شهروندِ دارای `Courier`).

## ۵. فرانت‌اند (`frontend/src/`)

- مسیرها همه در `App.tsx` (lazy)، سه بخش: سایت عمومی (`PublicLayout`)، پنل (`PanelLayout`، منو در آرایه `NAV`؛ آیتم‌های انبار/مالی با `featured: true` فقط برای مالک فروشگاه ویژه)، و اپ پیک (`/courier`، بدون layout).
- `lib/api.ts`: درخواست با JWT و refresh خودکار؛ خطای سرور → `ApiError` با پیام فارسی. `lib/format.ts`: تومان/ریال، تاریخ شمسی، اعداد فارسی. `lib/erp.ts`: فاکتور رسمی چاپی، مبلغ به حروف، قالب‌های کوتاه مبلغ. `lib/orders.ts`: انواع سفارش.
- کوئری‌ها با TanStack Query؛ کلیدها مثل `["erp-inventory", q, status]`. پس از mutation کلیدهای وابسته را `invalidateQueries` کنید (نمونه: `Purchases.tsx`).
- قالب‌های آماده در `components/ui.tsx` (`Sheet`, `Field`, `PriceInput`, `Stat`, `DataTable`…). رنگ‌ها توکن CSS است (`index.css`)؛ حالت تاریک خودکار.
- سبد خرید فروشگاه ویژه در `sessionStorage` (`nb.cart.<storeId>`) نگه داشته می‌شود.
- PWA: بعد از استقرار، مرورگر ممکن است نسخه قدیمی را کش کند (service worker)؛ ببندید/دوباره باز کنید یا داده سایت را پاک کنید.
- توسعه محلی: `BACKEND_URL=http://127.0.0.1:8001 node node_modules/vite/bin/vite.js --port 5201 --host 127.0.0.1`. `runserver --noreload` بعد از هر تغییر بک‌اند باید دوباره راه‌اندازی شود.

## ۶. موبایل (`mobile/`)

Capacitor وب را از `https://nazer724.ir` بارگذاری می‌کند (تغییر وب نیاز به APK جدید ندارد). `android/app/build.gradle` دو flavor دارد:
`customer` (شناسه `ir.nazer724.app`) و `courier` (شناسه `ir.nazer724.courier`، شروع از `/courier`، رنگ نارنجی؛ بازنویسی‌ها در `android/app/src/courier/`).
ساخت فقط روی GitHub Actions (`.github/workflows/android.yml`)؛ روی این کامپیوتر Android SDK نیست. **flavor پیک هنوز ساخته/آزمایش نشده است.**

## ۷. تنظیمات محیطی (`.env`، الگو: `.env.example`)

| متغیر | کار |
|---|---|
| `SECRET_KEY`، `DB_PASSWORD`، `DEBUG=0`، `ALLOWED_HOSTS`، `CSRF_TRUSTED_ORIGINS` | الزامی؛ پیش‌فرض‌های کد در غیاب `.env` **ناامن** است (DEBUG روشن) |
| `OTP_ECHO=0` | در سرور واقعی حتما ۰ (وگرنه کد ورود در پاسخ API می‌آید) |
| `SMS_BACKEND` (`console\|ghasedak\|kavenegar`)، `GHASEDAK_API_KEY/LINE`، `GHASEDAK_PRICE_TEMPLATE`، `GHASEDAK_OTP_TEMPLATE` | پیامک؛ قالب قاصدک با پارامترهای `%param1%..` (فروشگاه، کالا، قیمت) |
| `PAYMENT_BACKEND` (`zarinpal\|console`)، `ZARINPAL_MERCHANT_ID`، `ZARINPAL_SANDBOX`، `PAYMENT_ALLOW_MOCK` | درگاه سامانه (برای شارژ کیف پول و فروشگاه‌های بدون درگاه اختصاصی). بدون درگاه واقعی، پرداخت اینترنتی روی سرور واقعی بسته می‌ماند |
| `MARKET_DEFAULT_MAX_DISCOUNT`، `MARKET_UPDATE_GRACE_HOURS`، `MARKET_ALERT_CHANGE_PERCENT` | قواعد بازار |
| `DATABASE_URL`، `REDIS_URL`، `MEDIA_ROOT`، `LOG_LEVEL`، `CORS_ALLOWED_ORIGINS` | زیرساخت |

## ۸. استقرار و عملیات

1. مالک پروژه `git push origin main` را خودش می‌زند (ابزار هوش مصنوعی اجازه push ندارد؛ بدون تایید صریح push نکنید).
2. روی سرور: `cd ~/nazerbazar && git pull && docker compose up -d --build` (مایگریشن و `seed_base` خودکار اجرا می‌شود؛ «No migrations to apply» عادی است).
3. پس از استقرار (در صورت نیاز): `python manage.py seed_service_tariffs` (نرخ‌نامه تعویض روغن)، `seed_featured_store --mobile 09…` (فروشگاه ویژه آزمایشی).
4. **قبل از به‌روزرسانی پرخطر از پنل مدیر کل پشتیبان بگیرید.** سرویس `scheduler` هر ساعت `daily_jobs` را اجرا می‌کند (snapshot قیمت، هشدارها، آزادسازی سفارش‌های رهاشده).
5. سرور با پروژه‌های دیگر پورت ۸۰ را به‌اشتراک می‌گذارد؛ بلوک‌های nginx آن‌ها را عوض نکنید (`deploy/`).

## ۹. دام‌ها

- SQLite (محلی/تست) و PostgreSQL (واقعی) فرق دارند: `select_for_update` در SQLite اثری ندارد (هم‌زمانی فقط با بازبینی کد/PostgreSQL قابل اتکاست)، `max_length` اعمال نمی‌شود (متن بلند روی PostgreSQL خطا می‌دهد؛ ورودی را با `[:n]` ببرید).
- پاسخ لیست‌ها صفحه‌بندی‌شده (`results`) است مگر `pagination_class=None`.
- ثبت‌نام کاربر با موبایل است؛ مدیر مالک فروشگاه را با موبایل می‌سازد (کد پیامکی). رمز برای کاربر موجود تعیین نمی‌شود.
- آزمون‌ها با `PAYMENT_ALLOW_MOCK=True` اجرا می‌شوند (تشخیص `test` در `sys.argv`).
- ویندوز: PowerShell 5.1 عملگر `&&` ندارد؛ از `;` یا Git Bash استفاده کنید.

## ۱۰. وضعیت: اجراشده، آزمون‌شده، تایید‌نشده

- **با آزمون خودکار و بازبینی:** سفارش، موجودی، کیف پول، پرداخت (با شبیه‌ساز و `_post_json` شبیه‌سازی‌شده)، پیک، انبار/حسابداری/فاکتور، دسترسی نقش‌ها، ورودی خراب روی همه نشانی‌ها.
- **تایید‌نشده:** پرداخت واقعی با زرین‌پال/زیبال (فقط شبیه‌سازی)، رفتار هم‌زمانی واقعی روی PostgreSQL زیر بار، APK پیک، ارسال واقعی پیامک قاصدک روی سرور.
- **تصمیم‌های باز:** برگشت وجه سفارش اینترنتی (کیف پول یا بانک)، پذیرش پیک توسط خود او (الان بدون رضایت ثبت می‌شود)، پوش‌نوتیفیکیشن، ابطال فاکتور خرید، ردیابی زنده پیک.

## ۱۱. دستور کار برای تغییرهای رایج

- **API جدید:** تابع/ViewSet در `<app>/api.py`، منطق در `services.py`، مسیر در `config/urls.py` (قبل از `router`)، مجوز صریح (`IsAuthenticated` + نقش/حوزه)، اعتبارسنجی ورودی (عدد با سقف، متن با `[:n]`، شناسه با `int()` امن)، آزمون در `tests.py`، سپس `python manage.py test`.
- **مدل/ستون جدید:** `makemigrations` (فقط افزایشی با `default`)، `makemigrations --check` تمیز باشد.
- **صفحه پنل جدید:** فایل در `pages/panel/`، `lazy` + `Route` در `App.tsx`، آیتم `NAV` در `PanelLayout.tsx`، `tsc -b` و `npm run build` سبز.
- **متغیر محیطی جدید:** در `config/settings.py`، `.env.example` و جدول بخش ۷ همین فایل.
