import re

from datetime import date, datetime, timedelta
from typing import Optional


MONTHS = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}


def get_today() -> date:
    """
    Return today's date.
    """

    return date.today()


def normalize_date(
    parsed_date: date
) -> str:
    """
    Convert a Python date into YYYY-MM-DD format.
    """

    return parsed_date.strftime("%Y-%m-%d")


def parse_guest_date(
    text: str
) -> Optional[str]:
    """
    Parse common English, Hinglish, and Hindi
    date expressions.

    Supported examples:
    - today
    - aaj
    - आज
    - tomorrow
    - kal
    - कल
    - day after tomorrow
    - parso
    - परसों
    - 3rd sept
    - 3rd sept 2026
    - 15 September
    - 15 September 2026
    - 15/09/2026
    - 15-09-2026
    - 2026-09-15
    """

    clean_text = text.strip().lower()

    if not clean_text:
        return None

    today = get_today()

    # Day after tomorrow must be checked before
    # tomorrow because it contains the word "tomorrow".
    if (
        "day after tomorrow" in clean_text
        or "parso" in clean_text
        or "परसों" in clean_text
    ):
        return normalize_date(
            today + timedelta(days=2)
        )

    # Tomorrow / कल
    if (
        "tomorrow" in clean_text
        or re.search(r"\bkal\b", clean_text)
        or "कल" in clean_text
    ):
        return normalize_date(
            today + timedelta(days=1)
        )

    # Today / आज
    if (
        "today" in clean_text
        or re.search(r"\baaj\b", clean_text)
        or "आज" in clean_text
    ):
        return normalize_date(today)

    # Try ISO and numeric date formats.
    date_formats = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d/%m/%y",
        "%d-%m-%y",
    ]

    for date_format in date_formats:
        try:
            parsed = datetime.strptime(
                clean_text,
                date_format
            ).date()

            return normalize_date(parsed)

        except ValueError:
            continue

    # Convert ordinal numbers:
    # 1st -> 1
    # 2nd -> 2
    # 3rd -> 3
    # 4th -> 4
    clean_text = re.sub(
        r"(\d+)(st|nd|rd|th)",
        r"\1",
        clean_text
    )

    # Match:
    # 3 sept
    # 3 sept 2026
    # 15 september
    # 15 september 2026
    match = re.search(
        r"\b(\d{1,2})\s+([a-z]+)(?:\s+(\d{4}))?\b",
        clean_text
    )

    if match:
        day = int(match.group(1))
        month_name = match.group(2)
        year_text = match.group(3)

        month = MONTHS.get(month_name)

        if month is None:
            return None

        if year_text:
            year = int(year_text)
        else:
            year = today.year

            try:
                candidate = date(
                    year,
                    month,
                    day
                )

                if candidate < today:
                    year += 1

            except ValueError:
                return None

        try:
            parsed = date(
                year,
                month,
                day
            )

            return normalize_date(parsed)

        except ValueError:
            return None

    return None


def calculate_nights(
    check_in: Optional[str],
    check_out: Optional[str]
) -> Optional[int]:
    """
    Calculate the number of nights between check-in
    and check-out.
    """

    if not check_in or not check_out:
        return None

    try:
        check_in_date = datetime.strptime(
            check_in,
            "%Y-%m-%d"
        ).date()

        check_out_date = datetime.strptime(
            check_out,
            "%Y-%m-%d"
        ).date()

        return (
            check_out_date - check_in_date
        ).days

    except ValueError:
        return None


def is_valid_stay(
    check_in: Optional[str],
    check_out: Optional[str]
) -> bool:
    """
    Check that check-out is after check-in.
    """

    nights = calculate_nights(
        check_in,
        check_out
    )

    return (
        nights is not None
        and nights > 0
    )


def resolve_dates(
    check_in: Optional[str],
    check_out: Optional[str]
) -> tuple[Optional[str], Optional[str]]:
    """
    Normalize check-in and check-out dates into
    YYYY-MM-DD format.
    """

    resolved_check_in = None
    resolved_check_out = None

    if check_in:
        parsed = parse_guest_date(
            str(check_in)
        )

        resolved_check_in = (
            parsed if parsed else check_in
        )

    if check_out:
        parsed = parse_guest_date(
            str(check_out)
        )

        resolved_check_out = (
            parsed if parsed else check_out
        )

    return (
        resolved_check_in,
        resolved_check_out
    )

def parse_date_range(
    text: str
) -> tuple[Optional[str], Optional[str]]:
    """
    Parse date ranges such as:

    - 15th to 17th
    - 15 to 17
    - 15th Sept to 17th Sept
    - 15th September to 17th September
    """

    clean_text = text.lower().strip()
    today = get_today()

    pattern = (
        r"\b(\d{1,2})(?:st|nd|rd|th)?\s*"
        r"(?:to|-|till|until)\s*"
        r"(\d{1,2})(?:st|nd|rd|th)?\b"
    )

    match = re.search(
        pattern,
        clean_text
    )

    if not match:
        return None, None

    start_day = int(match.group(1))
    end_day = int(match.group(2))

    try:
        check_in_date = date(
            today.year,
            today.month,
            start_day
        )

        check_out_date = date(
            today.year,
            today.month,
            end_day
        )

        # If the start date has already passed this month,
        # use the next month.
        if check_in_date < today:
            if today.month == 12:
                check_in_date = date(
                    today.year + 1,
                    1,
                    start_day
                )
                check_out_date = date(
                    today.year + 1,
                    1,
                    end_day
                )
            else:
                check_in_date = date(
                    today.year,
                    today.month + 1,
                    start_day
                )
                check_out_date = date(
                    today.year,
                    today.month + 1,
                    end_day
                )

        return (
            normalize_date(check_in_date),
            normalize_date(check_out_date)
        )

    except ValueError:
        return None, None


def parse_weekend_range(
    text: str
) -> tuple[Optional[str], Optional[str]]:
    """
    Convert weekend expressions into actual dates.

    The stay is:
    Saturday check-in
    Monday check-out
    """

    clean_text = text.lower().strip()

    if "weekend" not in clean_text:
        return None, None

    today = get_today()

    # weekday():
    # Monday    = 0
    # Tuesday   = 1
    # Wednesday = 2
    # Thursday  = 3
    # Friday    = 4
    # Saturday  = 5
    # Sunday    = 6

    days_until_saturday = (
        5 - today.weekday()
    ) % 7

    saturday = today + timedelta(
        days=days_until_saturday
    )

    monday = saturday + timedelta(
        days=2
    )

    return (
        normalize_date(saturday),
        normalize_date(monday)
    )