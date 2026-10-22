"""Turn an assistant reply into text a speech engine reads well.

The agent writes for the screen as well as the ear: it may use symbols, units, markdown or emoji that a speech
engine would read badly ("₹285" as "rupee sign two eight five", "500g" as "five hundred g").
"""
import re

MAX_CHARS = 600  # a reply is a few sentences; this is a ceiling, not a target

# Pictographs and emoji, which engines either skip noisily or read out by name.
_EMOJI = re.compile(
    "["
    "\U0001F300-\U0001FAFF"  # symbols, pictographs, emoticons, transport, supplemental
    "\U00002600-\U000027BF"  # misc symbols and dingbats
    "\U0001F000-\U0001F2FF"
    "\U0000FE0F\U0000200D"  # variation selector, zero-width joiner
    "]+"
)

_UNITS = {
    "kg": "kilograms", "g": "grams", "mg": "milligrams",
    "l": "litres", "ml": "millilitres",
    "mah": "milliamp hours", "w": "watts", "gb": "gigabytes", "tb": "terabytes", "mb": "megabytes",
}
# A number directly followed by a unit: "500g", "1L", "5 kg", "20W", "20000mAh".
_NUMBER_UNIT = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s?(kg|mg|g|ml|l|mah|w|gb|tb|mb)\b", re.IGNORECASE)
_RUPEE_SIGN = re.compile(r"(?:₹|\bRs\.?|\bINR)\s?(\d+(?:,\d+)*(?:\.\d+)?)", re.IGNORECASE)
_NUMBER_GROUPS = re.compile(r"(?<=\d),(?=\d{2,3}(?!\d))")  # 1,016 and 12,34,567 -> 1016 and 1234567
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_URL = re.compile(r"https?://\S+")
_MARKDOWN = re.compile(r"[*_`#>~|]+")


def _spell_unit(match: re.Match) -> str:
    number, unit = match.group(1), _UNITS[match.group(2).lower()]
    if float(number) == 1:
        unit = unit.removesuffix("s")  # "1 litre", not "1 litres"
    return f"{number} {unit}"


def _cut(text: str, limit: int) -> str:
    """At most `limit` characters, ending at a sentence if one fits, otherwise at a word."""
    if len(text) <= limit:
        return text
    window = text[:limit]
    sentence_end = max(window.rfind(". "), window.rfind("! "), window.rfind("? "), window.rfind("।"))
    if sentence_end >= limit // 3:
        return window[: sentence_end + 1].strip()
    return window.rsplit(" ", 1)[0].strip()


def speakable(text: str, limit: int = MAX_CHARS) -> str:
    """The reply as plain words. Returns "" when there is nothing to say (for example, only emoji)."""
    text = _LINK.sub(r"\1", text)
    text = _URL.sub("", text)
    text = _EMOJI.sub(" ", text)
    text = _MARKDOWN.sub(" ", text)
    text = _RUPEE_SIGN.sub(lambda m: f"{m.group(1)} rupees", text)
    text = _NUMBER_GROUPS.sub("", text)
    text = _NUMBER_UNIT.sub(_spell_unit, text)
    text = text.replace("&", " and ").replace("%", " percent").replace("×", " times ")
    text = re.sub(r"\s+", " ", text).strip()
    return _cut(text, limit)
