from datetime import datetime

from app.core import clock


def utcnow() -> datetime:
    """Column default for every datetime column: naive UTC "now" from the clock (rule 5.15).

    Delegates to ``clock.now_utc`` through the module attribute at call time, so a
    default is evaluated per insert and a test that freezes ``app.core.clock.now_utc``
    also freezes what the models write. Binding ``now_utc`` directly would capture the
    function at import time and bypass such a freeze.
    """
    return clock.now_utc()
