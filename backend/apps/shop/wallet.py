"""کیف پول مشتری: همه تغییر موجودی‌ها از همین‌جا و با قفل ردیف انجام می‌شود تا هرگز منفی نشود."""
from django.core.exceptions import ValidationError
from django.db import transaction

from .commerce import Wallet, WalletTx


def get_wallet(user, lock=False) -> Wallet:
    wallet, _ = Wallet.objects.get_or_create(user=user)
    if lock:
        wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
    return wallet


@transaction.atomic
def credit(user, amount: int, kind: str, note: str = "", order=None) -> Wallet:
    if amount <= 0:
        raise ValidationError({"amount": "مبلغ باید بیشتر از صفر باشد."})
    wallet = get_wallet(user, lock=True)
    wallet.balance += amount
    wallet.save(update_fields=["balance"])
    WalletTx.objects.create(wallet=wallet, amount=amount, balance_after=wallet.balance, kind=kind, note=note[:200], order=order)
    return wallet


@transaction.atomic
def debit(user, amount: int, kind: str, note: str = "", order=None) -> Wallet:
    wallet = get_wallet(user, lock=True)
    if amount <= 0 or wallet.balance < amount:
        raise ValidationError({"payment_method": "موجودی کیف پول کافی نیست."})
    wallet.balance -= amount
    wallet.save(update_fields=["balance"])
    WalletTx.objects.create(wallet=wallet, amount=-amount, balance_after=wallet.balance, kind=kind, note=note[:200], order=order)
    return wallet
