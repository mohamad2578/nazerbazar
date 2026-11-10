# راهنمای فرانت‌اند ناظر ۷۲۴

React 19 + Vite + TypeScript + Tailwind 4 + TanStack Query + React Router. همه‌جا RTL فارسی، موبایل‌محور و PWA.
قواعد کلی پروژه و نقشه بک‌اند: [AI-CONTEXT.md](AI-CONTEXT.md).

## اجرا و ساخت

```bash
cd frontend
npm install
npm run dev                       # http://localhost:5173 ؛ /api و /media به 127.0.0.1:8000 پروکسی می‌شود
BACKEND_URL=http://127.0.0.1:8001 node node_modules/vite/bin/vite.js --port 5201 --host 127.0.0.1   # بک‌اند روی پورت دیگر
npx tsc -b                        # تایپ‌چک (باید بی‌خطا باشد؛ noUnusedLocals روشن است)
npm run build                     # tsc + vite build + PWA؛ همان کاری که Dockerfile می‌کند
```

متغیرهای زمان build: `VITE_API_URL` (پیش‌فرض `/api`)، `VITE_MAP_TILES` (کاشی نقشه؛ پیش‌فرض OpenStreetMap).
بدون تست خودکار فرانت: درستی را با `tsc`، `build` و آزمون دستی در مرورگر بسنجید؛ منطق مالی/انبار در بک‌اند و با تست آن بررسی می‌شود.

## ساختار `src/`

| مسیر | محتوا |
|---|---|
| `App.tsx` | **همه مسیرها** (lazy) و محافظ‌ها: `RequireAuth` (ورود + نقش)، `RequirePanel`. سه بخش: سایت عمومی، `/panel/*`، `/courier` |
| `layouts/PublicLayout.tsx` | سربرگ سایت عمومی و نوار پایین موبایل |
| `layouts/PanelLayout.tsx` | منوی پنل: آرایه `NAV` (نقش‌ها، `section`/`reports` برای تنظیمات مدیر کل، `featured` فقط مالک فروشگاه ویژه) |
| `pages/public/` | خانه، کالا، فروشگاه (`StoreDetail`، `FeaturedShop` + `FeaturedStorefront` برای فروشگاه ویژه)، نقشه، حساب (کیف پول/نشانی)، سفارش‌های من، … |
| `pages/panel/` | صفحات پنل؛ `panel/erp/` انبار و حسابداری؛ `Orders`، `Couriers`، `MyShop`، `Products`… |
| `pages/courier/CourierApp.tsx` | اپ پیک (بدون layout، مستقل) |
| `components/` | `ui.tsx` (کیت رابط)، `ShopCart`، `AddressBook`، `MapView`، `charts`، `ImageUpload`… |
| `lib/` | `api.ts`، `auth.tsx`، `format.ts`، `orders.ts`، `erp.ts`، `prefs.ts`، `settings.ts`، `track.ts` |

## لایه API و ورود (`lib/api.ts`, `lib/auth.tsx`)

- `api.get/post/patch/put/del<T>(path, ...)`: JWT را از `localStorage` (`nb.tokens`) می‌فرستد، با ۴۰۱ خودکار refresh می‌کند و در شکست، رویداد `nb:logout` می‌دهد.
  خطای سرور `ApiError` است و `message` آن همان پیام فارسی سرور است (برای toast). `fieldErrors(error)` خطای فیلدها را برای زیر فیلد فرم می‌دهد.
- فایل‌ها با `FormData` فرستاده می‌شود (Content-Type خودکار). `download(path, name)` برای خروجی‌های اکسل/CSV با توکن.
- لیست‌های صفحه‌بندی‌شده `Page<T>` هستند (`results`, `count`, `next`).
- `useAuth()` → `{ user, login, logout, reload }`. `user` شامل `role`، `store` (با `is_featured`) و `is_courier` است؛ منو و دسترسی صفحه‌ها از همین‌ها تصمیم می‌گیرند.
  **امنیت واقعی در بک‌اند است**؛ پنهان‌کردن منو فقط UX است.
- `useAccess()` (`lib/settings.ts`): تنظیمات مدیر کل (بخش‌های بسته‌شده برای اتحادیه، گزارش‌های صمت، اجازه ثبت قیمت).

## پول و فرمت (`lib/format.ts`)

سرور **ریال** می‌فرستد و می‌گیرد؛ کاربر **تومان** می‌بیند و وارد می‌کند. همیشه از این‌ها استفاده کنید و `/10` و `*10` دستی ننویسید:
`toman(rial)` (رشته نمایشی با «تومان»)، `toToman(rial)`، `toRial(tomanString)` (ارقام فارسی و جداکننده را می‌فهمد)، `num()`, `date()`, `dateTime()`, `ago()`.
`PriceInput` (در `ui.tsx`) مقدار را به‌صورت رشته تومان نگه می‌دارد؛ هنگام ارسال با `toRial`/`toIntRial` تبدیل کنید.
برای کارت‌های آماری مبلغ بزرگ: `moneyCompact()` (`lib/erp.ts`).

## الگوی صفحه جدید

1. فایل در `pages/panel/...` با `export default function X()`؛ بالای فایل یک توضیح JSDoc که کار صفحه را می‌گوید.
2. داده: `useQuery({ queryKey: ["erp-xxx", filters], queryFn: () => api.get<T>("/erp/xxx/", filters) })`. کلید را با نام ویژگی شروع کنید.
3. ثبت/ویرایش: `useMutation` + `onSuccess` که `qc.invalidateQueries({ queryKey: [...] })` را برای **همه** کلیدهای وابسته (لیست، داشبورد) صدا می‌زند؛ پیام خطا از `onError`/`fieldErrors`.
4. فرم‌ها در `Sheet` (پنجره کشویی) با `Field` و `Input/Select/PriceInput`؛ دکمه اصلی در `footer`.
5. `App.tsx`: `lazy` import + `<Route path="..." element={<RequireAuth roles={[...]}><X /></RequireAuth>} />`؛ آیتم منو در `NAV` (`PanelLayout.tsx`).
6. بعد از تغییر: `npx tsc -b` و `npm run build`.

## رابط کاربری

- رنگ‌ها توکن CSS (`index.css`: `bg-surface`, `text-muted`, `bg-brand-soft`…)؛ حالت تاریک خودکار. رنگ ثابت (hex) ننویسید مگر در فاکتور چاپی/نمودار.
- `Stat`, `Card`, `Badge` (tone: ok/warn/danger/brand), `Segmented`, `DataTable`, `Loading`, `Empty`, `ErrorBox`, `useToast()` در `ui.tsx`.
- متن‌ها فارسی؛ ارقام نمایشی با `Intl("fa-IR")`. در فیلد LTR (موبایل، کد) `dir="ltr"` و `className="text-left"` بگذارید.
- موبایل اول: صفحه‌ها در ۳۷۵px بررسی شود؛ ردیف‌های لیست به‌صورت کارت، نه جدول عریض.
- نمودارها: `components/charts.tsx` (Recharts؛ `BarsChart`, `TrendChart`).

## ویژگی‌های ویژه

- **فاکتور چاپی** (`lib/erp.ts`): `printSalesInvoice` و `printPurchaseInvoice` HTML مستقل را در پنجره جدید باز می‌کنند (همه متن‌ها `esc()` می‌شود؛ هر فیلد جدید را escape کنید). مبلغ به حروف: `rialWords`.
- **سبد خرید فروشگاه ویژه:** وضعیت در `FeaturedStorefront`، ذخیره در `sessionStorage` با کلید `nb.cart.<storeId>`؛ تسویه در `ShopCart` (فروشگاه ویژه: فقط پرداخت اینترنتی و پیک؛ پس از ثبت، مرورگر به `payment_url` درگاه می‌رود).
- **نشانی‌ها:** `AddressBook` (موقعیت نقشه برای فروشگاه ویژه الزامی است).
- **اپ پیک:** `/courier` هر ۲۰ ثانیه فهرست را تازه می‌کند؛ دکمه‌های گردش (تحویل‌گرفتن/تحویل/ناموفق) بسته به وضعیت سفارش.
- **PWA:** پس از استقرار ممکن است نسخه قدیمی کش بماند؛ ببندید/باز کنید یا داده سایت را پاک کنید (`registerType: autoUpdate`).

## دام‌ها

- `noUnusedLocals` روشن است؛ import یا متغیر بلااستفاده build را می‌شکند.
- `window.scrollTo` را داخل `useEffect` با آکولاد بنویسید (برگرداندن مقدار از effect خطا می‌دهد).
- در کامپایل اول Vite، صفحه‌های lazy ثانیه‌ها خالی می‌مانند؛ دوباره بارگذاری کنید.
- پروکسی dev هدر `Host` را تغییر می‌دهد؛ بازگشت از درگاه (`/api/public/payments/callback/`) در dev به پورت بک‌اند می‌رود (در تولید با nginx درست است).
