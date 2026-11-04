"""کار زمان‌بندی‌شده روزانه (cron): عکس قیمت‌ها و تولید هشدارهای رصدخانه.

نمونه crontab:  10 0 * * *  docker compose exec -T backend python manage.py daily_jobs
"""
from django.core.management.base import BaseCommand

from apps.market.services import take_daily_snapshot
from apps.observatory.services import scan_alerts


class Command(BaseCommand):
    help = "snapshot روزانه قیمت‌ها و اسکن هشدارها"

    def handle(self, *args, **opts):
        from apps.shop.order_services import expire_unpaid_orders

        n = take_daily_snapshot()
        a = scan_alerts()
        released = expire_unpaid_orders(limit=500)   # سفارش اینترنتی رهاشده: لغو و موجودی آزاد می‌شود
        self.stdout.write(self.style.SUCCESS(f"snapshot: {n} ردیف، هشدار جدید: {a}، سفارش رهاشده: {released}"))
