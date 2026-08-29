from uuid import UUID

from apps.notifications.templates import render_message


def test_processing_message_uses_only_the_safe_short_order_reference():
    message = render_message(
        "CUSTOMER_ORDER_CONFIRMED",
        UUID("12345678-1234-5678-1234-567812345678"),
    )

    assert message == "سفارش شما با موفقیت ثبت شد. کد سفارش: 123456781234"
    assert "0912" not in message


def test_shipped_message_is_server_controlled():
    message = render_message(
        "CUSTOMER_ORDER_SHIPPED",
        UUID("abcdefab-cdef-abcd-efab-cdefabcdefab"),
    )

    assert message == "سفارش ABCDEFABCDEF به شرکت پست/حمل‌ونقل تحویل داده شد."
