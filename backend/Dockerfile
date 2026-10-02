FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libjpeg62-turbo zlib1g && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
# در برخی شبکه‌ها (ازجمله ایران) files.pythonhosted.org فیلتر/ناپایدار است؛
# ابتدا آینه‌های جایگزین را امتحان می‌کنیم و در نهایت PyPI اصلی را.
RUN pip install --no-cache-dir --index-url https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com -r requirements.txt \
    || pip install --no-cache-dir --index-url https://pypi.arvancloud.ir/simple/ --trusted-host pypi.arvancloud.ir -r requirements.txt \
    || pip install --no-cache-dir -r requirements.txt
COPY . .
RUN DEBUG=0 SECRET_KEY=build python manage.py collectstatic --noinput
EXPOSE 8000
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py seed_base && gunicorn config.wsgi:application -b 0.0.0.0:8000 -w ${GUNICORN_WORKERS:-3} --timeout 60"]
