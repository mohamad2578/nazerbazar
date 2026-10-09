# راه‌اندازی دامنه nazer724.ir

سرور: `171.22.24.139` — این پروژه روی پورت `8097` بالاست و پورت ۸۰ سرور را پروژه دیگری
(هلال احمر) گرفته است. بنابراین دو کار لازم است:

1. **DNS** تا دامنه به این سرور اشاره کند
2. **vhost روی nginx پورت ۸۰** تا درخواست‌های `nazer724.ir` به کانتینر این پروژه برود

> **پیشنهاد:** اگر خواستید کار ساده‌تر و مطمئن‌تر باشد، بخش «روش جایگزین» در انتهای همین
> فایل را ببینید؛ به‌جای راه‌اندازی نیم‌سرور، DNS را به ابرآروان می‌سپارید و فقط یک رکورد A
> می‌سازید. مرحله ۲ (vhost) در هر دو روش لازم است.

---

## مرحله ۱ — نصب و پیکربندی نیم‌سرور (BIND9)

```bash
apt update && apt install -y bind9 bind9-utils
```

کد پروژه را به‌روز کنید و فایل‌ها را سر جایشان بگذارید:

```bash
cd ~/nazerbazar && git pull
mkdir -p /etc/bind/zones
cp deploy/dns/db.nazer724.ir /etc/bind/zones/
cp deploy/dns/named.conf.options /etc/bind/named.conf.options
cat deploy/dns/named.conf.local >> /etc/bind/named.conf.local
```

درستی فایل‌ها را بررسی کنید (هر دو دستور باید بی‌خروجی یا با پیام OK تمام شوند):

```bash
named-checkconf && named-checkzone nazer724.ir /etc/bind/zones/db.nazer724.ir
```

سرویس را بالا بیاورید:

```bash
systemctl enable --now bind9 && systemctl restart bind9 && systemctl status bind9 --no-pager
```

تست محلی — باید `171.22.24.139` را برگرداند:

```bash
dig @127.0.0.1 nazer724.ir +short
```

### باز کردن پورت ۵۳

DNS هم UDP و هم TCP پورت ۵۳ را لازم دارد:

```bash
ufw allow 53/udp && ufw allow 53/tcp && ufw status
```

**مهم:** در پنل پارس‌پک هم باید پورت ۵۳ روی UDP و TCP باز شود، وگرنه از بیرون جواب نمی‌دهد.
بعد از باز کردن، از یک شبکه دیگر تست کنید:

```bash
dig @171.22.24.139 nazer724.ir +short
```

---

## مرحله ۲ — vhost روی nginx پورت ۸۰

اول ببینید پیکربندی فعلی چیست و کدام بلوک `default_server` است:

```bash
nginx -T | grep -nE "server_name|listen|default_server" | head -40
```

اگر هیچ بلوکی `default_server` ندارد، **اول** بلوک پروژه هلال احمر را صریحاً پیش‌فرض کنید
(`listen 80 default_server;`) تا با افزودن فایل جدید، پیش‌فرض عوض نشود.

سپس:

```bash
cp ~/nazerbazar/deploy/nginx/nazer724.ir.conf /etc/nginx/sites-available/nazer724.ir
ln -s /etc/nginx/sites-available/nazer724.ir /etc/nginx/sites-enabled/nazer724.ir
nginx -t
```

فقط اگر `nginx -t` گفت `syntax is ok` و `test is successful`:

```bash
systemctl reload nginx
```

تست بدون نیاز به DNS (درخواست را با نام دامنه به IP می‌فرستد):

```bash
curl -sI -H "Host: nazer724.ir" http://171.22.24.139/ | head -5
```

باید صفحه ناظر ۷۲۴ بیاید نه هلال احمر.

---

## مرحله ۳ — تنظیم دامنه در جنگو

در فایل `~/nazerbazar/.env` این دو خط را اضافه یا اصلاح کنید:

```
ALLOWED_HOSTS=nazer724.ir,www.nazer724.ir,171.22.24.139,localhost
CSRF_TRUSTED_ORIGINS=http://nazer724.ir,http://www.nazer724.ir,https://nazer724.ir,https://www.nazer724.ir
```

سپس:

```bash
cd ~/nazerbazar && docker compose up -d
```

---

## مرحله ۴ — ثبت نیم‌سرورها در nic.ir

۱. در پنل nic.ir وارد بخش **«میزبان‌ها» (Host Objects)** شوید و دو میزبان بسازید:

| نام میزبان | نشانی IP |
|---|---|
| `ns1.nazer724.ir` | `171.22.24.139` |
| `ns2.nazer724.ir` | `171.22.24.139` |

۲. در صفحه دامنه `nazer724.ir`، نیم‌سرورها را روی همین دو مورد تنظیم کنید.

۳. انتشار معمولاً چند ساعت تا ۲۴ ساعت طول می‌کشد. برای بررسی:

```bash
dig NS nazer724.ir +short
dig nazer724.ir +short
```

> **نکته‌ای که ممکن است به آن بخورید:** nic.ir گاهی دو نیم‌سرور روی یک IP را قبول نمی‌کند،
> چون هدفِ داشتن دو نیم‌سرور، پایداری در زمان قطعی است و با یک سرور این هدف برآورده نمی‌شود.
> اگر خطا گرفتید، سراغ «روش جایگزین» بروید.

---

## مرحله ۵ — HTTPS (بعد از اینکه دامنه باز شد)

نصب PWA روی موبایل فقط با HTTPS کار می‌کند، پس این مرحله را جدی بگیرید:

```bash
apt install -y certbot python3-certbot-nginx
certbot --nginx -d nazer724.ir -d www.nazer724.ir
```

certbot خودش بلوک HTTPS را به همان فایل اضافه و تمدید خودکار را تنظیم می‌کند.
بعد از آن، در `.env` این را هم اضافه کنید و `docker compose up -d` بزنید:

```
SECURE_SSL_REDIRECT=1
```

---

## روش جایگزین (ساده‌تر و مطمئن‌تر): DNS ابری

راه‌اندازی نیم‌سرور روی یک سرور، یک نقطه شکست واحد می‌سازد: اگر سرور یا سرویس bind
بخوابد، دامنه به‌کلی ناپدید می‌شود — نه فقط سایت، بلکه ایمیل و هر زیردامنه دیگر هم.

به‌جایش:

۱. در [ابرآروان](https://panel.arvancloud.ir) (رایگان) دامنه `nazer724.ir` را اضافه کنید
۲. دو نیم‌سروری که به شما می‌دهد را در nic.ir ثبت کنید
۳. در پنل آروان یک رکورد **A** بسازید: `@` → `171.22.24.139` و یکی هم برای `www`

مرحله ۲ (vhost) و مرحله ۳ (تنظیم جنگو) در این روش هم لازم است؛ فقط مرحله ۱ و ۴ حذف می‌شوند.
