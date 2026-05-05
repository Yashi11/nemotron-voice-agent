# SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Regex / pure-python parsers for deterministic entity extraction.

Consumed by :mod:`cascaded.agentic_airline.orchestrators._intent_llm` (first-turn
intent + entity classifier) and :mod:`cascaded.agentic_airline.orchestrators._common`
(``extract_pnr`` for the awaiting-PNR substate).  City → IATA mapping,
flight-number canonicalisation, and spelled-code reassembly all live
here so the LLM gets clean inputs.
"""

from __future__ import annotations

import re

# Cities we recognize by name in caller speech, mapped to IATA codes.
# Keys are lowercase; multi-word entries matched with word-boundary-anchored
# substring search so "new york" beats "york" alone.
CITY_TO_IATA: dict[str, str] = {
    "new york": "JFK",
    "nyc": "JFK",
    "jfk": "JFK",
    "los angeles": "LAX",
    "la": "LAX",
    "lax": "LAX",
    "seattle": "SEA",
    "sea": "SEA",
    "san francisco": "SFO",
    "sfo": "SFO",
    "miami": "MIA",
    "mia": "MIA",
    "boston": "BOS",
    "bos": "BOS",
    "chicago": "ORD",
    "ord": "ORD",
    "london": "LHR",
    "lhr": "LHR",
    "dallas": "DFW",
    "dfw": "DFW",
    "denver": "DEN",
    "den": "DEN",
    "atlanta": "ATL",
    "atl": "ATL",
    "las vegas": "LAS",
    "vegas": "LAS",
    "las": "LAS",
    "phoenix": "PHX",
    "phx": "PHX",
}


_CONFIRM_RE = re.compile(
    r"\b(?:yes|yeah|yep|yup|sure|confirm(?:ed)?|ok(?:ay)?|sounds?\s+good|"
    r"go\s+ahead|do\s+it|book\s+it|let['']?s\s+do\s+it|that\s+works|alright|"
    r"please\s+do|go\s+for\s+it)\b",
    re.IGNORECASE,
)

_DENY_RE = re.compile(
    r"\b(?:no|nope|nah|don['']?t|negative|not\s+really|scratch\s+that|"
    r"never\s+mind|forget\s+it|stop)\b",
    re.IGNORECASE,
)

_RESTART_RE = re.compile(
    r"\b(?:actually|instead|wait|hold\s+on|change\s+that|scratch\s+that|"
    r"never\s+mind|on\s+second\s+thought|no[,\s]+make\s+it|"
    r"different\s+(?:destination|city|flight))\b",
    re.IGNORECASE,
)

_FLIGHT_RE = re.compile(r"\b([A-Z]{2,3})\s*([0-9]{2,4})\b", re.IGNORECASE)

# PNR spoken-form expansion.  Callers on a phone call almost never speak
# compact ``ABC123`` — they say "A B C 1 2 3" or "Alpha Bravo Charlie one
# two three".  Normalize both representations to a canonical 6-char code
# before applying the exact-shape regex.
_NATO_TO_LETTER: dict[str, str] = {
    "alpha": "A",
    "alfa": "A",
    "bravo": "B",
    "charlie": "C",
    "delta": "D",
    "echo": "E",
    "foxtrot": "F",
    "golf": "G",
    "hotel": "H",
    "india": "I",
    "juliet": "J",
    "juliett": "J",
    "kilo": "K",
    "lima": "L",
    "mike": "M",
    "november": "N",
    "oscar": "O",
    "papa": "P",
    "quebec": "Q",
    "romeo": "R",
    "sierra": "S",
    "tango": "T",
    "uniform": "U",
    "victor": "V",
    "whiskey": "W",
    "xray": "X",
    "yankee": "Y",
    "zulu": "Z",
}
_WORD_TO_DIGIT: dict[str, str] = {
    "zero": "0",
    "oh": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
}
_PNR_SHAPE_RE = re.compile(r"([A-Z]{3})(\d{3})")

_FIRST_RE = re.compile(
    r"\b(?:first|earlier|earliest|1st|morning|am)\b",
    re.IGNORECASE,
)
_SECOND_RE = re.compile(
    r"\b(?:second|later|latest|2nd|afternoon|evening|pm)\b",
    re.IGNORECASE,
)


def is_plain_confirm(text: str) -> bool:
    """True when ``text`` is a bare confirmation ("yes", "ok", "book it").

    Returns False when the text *also* carries a restart signal, so
    "actually yes, change that to MIA" routes through the restart path.
    """
    if not text:
        return False
    return bool(_CONFIRM_RE.search(text)) and not is_restart_signal(text)


def is_plain_deny(text: str) -> bool:
    """True when ``text`` is a bare denial ("no", "scratch that", "forget it")."""
    if not text:
        return False
    return bool(_DENY_RE.search(text)) and not is_restart_signal(text)


def is_restart_signal(text: str) -> bool:
    """True when ``text`` contains a change-of-mind marker that should reset the flow."""
    return bool(text and _RESTART_RE.search(text))


def extract_pnr(text: str) -> str | None:
    """Parse a 6-character PNR (3 letters + 3 digits) from caller speech.

    Two strategies:

    1. A single token that already has PNR shape ("ABC123", lowercased ok).
    2. A *consecutive run* of single-character / NATO-phonetic / digit-word
       tokens that glues to PNR shape when joined ("A B C 1 2 3",
       "Alpha Bravo Charlie one two three").

    Non-contributing tokens break the run, which prevents false positives
    like "there is AA311" (a flight number sitting next to a filler word
    would otherwise drift into a spurious PNR match).  Returns the
    canonical uppercase code, or None.
    """
    if not text:
        return None
    tokens = re.findall(r"[A-Za-z0-9]+", text)
    for tok in tokens:
        m = _PNR_SHAPE_RE.search(tok.upper())
        if m is not None:
            return m.group(1) + m.group(2)

    run: list[str] = []

    def _check(pieces: list[str]) -> str | None:
        if not pieces:
            return None
        m2 = _PNR_SHAPE_RE.search("".join(pieces))
        return (m2.group(1) + m2.group(2)) if m2 else None

    for tok in tokens:
        lo = tok.lower()
        if lo in _NATO_TO_LETTER:
            run.append(_NATO_TO_LETTER[lo])
        elif lo in _WORD_TO_DIGIT:
            run.append(_WORD_TO_DIGIT[lo])
        elif len(tok) == 1 and tok.isalpha():
            run.append(tok.upper())
        elif len(tok) == 1 and tok.isdigit():
            run.append(tok)
        else:
            found = _check(run)
            if found:
                return found
            run = []
    return _check(run)


def extract_flight_number(text: str) -> str | None:
    """Return a canonical ``AA311`` flight number from ``text`` or None.

    Matches 2–3 call-sign letters followed by 2–4 digits, case-insensitive.
    Strips any whitespace between letters and digits.
    """
    if not text:
        return None
    m = _FLIGHT_RE.search(text)
    if not m:
        return None
    return f"{m.group(1).upper()}{m.group(2)}"


def extract_iata(text: str) -> str | None:
    """Return the IATA code for the first recognized city or airport in ``text``.

    Longer phrases ("new york") are matched before shorter ones ("york")
    so overlapping entries don't swap winners depending on dict order.
    Also tolerates spelled-out ASR outputs ("S F O", "l-h-r") by
    collapsing lone-letter runs before the primary lookup.
    """
    if not text:
        return None
    collapsed = _collapse_spelled_letters(text)
    lower = collapsed.lower()
    for phrase, iata in sorted(CITY_TO_IATA.items(), key=lambda kv: -len(kv[0])):
        if re.search(r"\b" + re.escape(phrase) + r"\b", lower):
            return iata
    return None


_SPELLED_LETTERS_RE = re.compile(r"(?:\b[A-Za-z]\b[\s.,\-]+){2,}\b[A-Za-z]\b")


def _collapse_spelled_letters(text: str) -> str:
    """Collapse runs of 3+ single letters separated by space/comma/dot into one token.

    "Can I reb it to S F O" → "Can I reb it to SFO".  "Change to L, H, R"
    → "Change to LHR".  Leaves ordinary words untouched.
    """

    def _merge(match: re.Match) -> str:
        run = match.group(0)
        letters = re.findall(r"[A-Za-z]", run)
        return "".join(letters)

    return _SPELLED_LETTERS_RE.sub(_merge, text)


def extract_origin_destination(text: str) -> tuple[str | None, str | None]:
    """Parse "from X to Y" / "to Y" patterns. Returns ``(origin, destination)`` IATA codes.

    A "to" can appear as filler ("want to rebook"), so we scan *every*
    ``to X`` / ``into X`` occurrence and keep the first one whose tail
    phrase maps to a known city.  Unknown destinations still return
    ``None`` so the caller can re-ask.
    """
    if not text:
        return None, None
    lower = text.lower()
    _tail = r"(?:\s+(?:instead|please|now|actually|though|today|tomorrow)|[.?!,]|$)"
    m = re.search(r"from\s+([\w\s]+?)\s+to\s+([\w\s]+?)" + _tail, lower)
    if m:
        origin_iata = _phrase_to_iata(m.group(1))
        dest_iata = _phrase_to_iata(m.group(2))
        if dest_iata is not None:
            return origin_iata, dest_iata
    for m in re.finditer(r"\b(?:to|into)\s+([\w\s]+?)" + _tail, lower):
        dest_iata = _phrase_to_iata(m.group(1))
        if dest_iata is not None:
            return None, dest_iata
    return None, None


def pick_alternative_index(text: str, total: int) -> int | None:
    """Return 0-based index into the alternatives list, or None if ambiguous.

    Handles "first"/"second", "earlier"/"later", "morning"/"afternoon".
    Returns None when both keywords appear or neither does.
    """
    if total <= 0 or not text:
        return None
    has_first = bool(_FIRST_RE.search(text))
    has_second = bool(_SECOND_RE.search(text))
    if has_first and not has_second:
        return 0
    if has_second and not has_first and total >= 2:
        return 1
    return None


def _phrase_to_iata(phrase: str) -> str | None:
    """Map a phrase ("new york please", "miami instead") to an IATA code.

    Tries the whole phrase, then 3/2/1-word tails, then 3/2/1-word heads,
    so embedded filler ("miami now", "new york today") still resolves.
    """
    p = phrase.strip().lower()
    if not p:
        return None
    if p in CITY_TO_IATA:
        return CITY_TO_IATA[p]
    words = p.split()
    for n in (3, 2, 1):
        if len(words) >= n:
            tail = " ".join(words[-n:])
            if tail in CITY_TO_IATA:
                return CITY_TO_IATA[tail]
            head = " ".join(words[:n])
            if head in CITY_TO_IATA:
                return CITY_TO_IATA[head]
    return None
