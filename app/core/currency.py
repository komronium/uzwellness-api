"""Display-currency conversion built on the X_UZS exchange-rate pairs."""

from decimal import ROUND_HALF_UP, Decimal

from app.core.config import settings

_TWO = Decimal("0.01")
_ONE = Decimal(1)

DEFAULT_DISPLAY_CURRENCY = "UZS"


def supported_display_currencies() -> list[str]:
    currencies: list[str] = []
    for currency in ("UZS", *settings.EXCHANGE_RATE_SYNC_CURRENCIES):
        code = currency.strip().upper()
        if code and code not in currencies:
            currencies.append(code)
    return currencies


class CurrencyConverter:
    """Converts amounts between currencies via UZS cross rates.

    ``target`` is the request's display currency. ``rates`` maps pairs like
    ``USD_UZS`` to how many UZS one unit of the currency costs.
    """

    def __init__(self, target: str, rates: dict[str, Decimal]) -> None:
        self.target = target.strip().upper()
        self._rates = {pair.upper(): rate for pair, rate in rates.items()}

    @property
    def rates_to_uzs(self) -> dict[str, Decimal]:
        return dict(self._rates)

    def _rate_to_uzs(self, currency: str) -> Decimal | None:
        currency = currency.strip().upper()
        if currency == "UZS":
            return _ONE
        return self._rates.get(f"{currency}_UZS")

    def convert(
        self,
        amount: Decimal | None,
        source_currency: str,
        target_currency: str | None = None,
    ) -> Decimal | None:
        """Convert to ``target_currency`` (the display currency by default).

        Returns None when the amount is None or a needed rate is missing.
        """
        if amount is None:
            return None
        source = source_currency.strip().upper()
        target = (target_currency or self.target).strip().upper()
        if source == target:
            return amount.quantize(_TWO, ROUND_HALF_UP)
        source_rate = self._rate_to_uzs(source)
        target_rate = self._rate_to_uzs(target)
        if source_rate is None or target_rate is None:
            return None
        return (amount * source_rate / target_rate).quantize(_TWO, ROUND_HALF_UP)
