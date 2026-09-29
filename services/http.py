"""Shared upstream cooldown handling."""

import math
import time
from email.utils import parsedate_to_datetime


def retry_deadline(value, minimum=60):
    deadline = time.time() + minimum
    try:
        seconds = float(value)
        if math.isfinite(seconds):
            deadline = max(deadline, time.time() + seconds)
    except ValueError:
        try:
            deadline = max(deadline, parsedate_to_datetime(value).timestamp())
        except (TypeError, ValueError, OverflowError):
            pass
    return deadline
