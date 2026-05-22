from app.services.email_service import (
    BookingEmailContext,
    send_booking_cancelled,
    send_booking_confirmed,
    send_booking_received,
)


class BookingNotifier:
    def booking_received(self, *, to: str, ctx: BookingEmailContext) -> None:
        send_booking_received(to=to, ctx=ctx)

    def booking_confirmed(self, *, to: str, ctx: BookingEmailContext) -> None:
        send_booking_confirmed(to=to, ctx=ctx)

    def booking_cancelled(self, *, to: str, ctx: BookingEmailContext) -> None:
        send_booking_cancelled(to=to, ctx=ctx)


def get_booking_notifier() -> BookingNotifier:
    return BookingNotifier()
