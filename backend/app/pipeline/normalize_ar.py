"""Mandatory Arabic text normalization (T047). [R5]

MUST be applied identically to:
  - documents during ingestion
  - private reference corpus during ingestion
  - user queries at retrieval time
  - the shared Egyptian-law corpus during preparation (shared-corpus/prepare_corpus.py)

This guarantees that query vectors and document vectors are comparable after
embedding.  Rules are purely deterministic — no ML, no external dependency.

Rules (research.md R5):
  1. Unicode NFC decomposition → recompose
  2. Alef forms (أ إ آ ﺃ ﺁ …) → bare alef  U+0627
  3. Alef-maqsura (ى)        → ya         U+064A
  4. Ta-marbuta at word boundary (ة→ه)
  5. Strip tashkeel / tanween / shadda / sukun (U+064B–U+0652)
  6. Strip tatweel / kashida (U+0640)
  7. Arabic-Indic digits (٠–٩) → ASCII (0–9)
  8. Remove non-printable / control characters (keep newlines, tabs, spaces)
  9. Collapse horizontal-space runs into a single space
 10. Collapse 3+ consecutive newlines into 2
 11. Strip trailing/leading whitespace per line
"""

from __future__ import annotations

import re
import unicodedata

# ── 2. alef variants → bare alef (U+0627) ────────────────────────────────────
# Using the dict form of str.maketrans (ordinal → ordinal) to avoid any
# off-by-one counting error in the string forms.
# Covers: ALEF WITH HAMZA ABOVE/BELOW, ALEF WITH MADDA ABOVE, Quranic alef
# variants (0671–0675), and Presentation Forms A/B alefs.
_ALEF_BARE = ord("ا")  # U+0627
_ALEF_VARIANTS = str.maketrans(
    {
        ord("أ"): _ALEF_BARE,  # U+0623 ALEF WITH HAMZA ABOVE
        ord("إ"): _ALEF_BARE,  # U+0625 ALEF WITH HAMZA BELOW
        ord("آ"): _ALEF_BARE,  # U+0622 ALEF WITH MADDA ABOVE
        ord("ٱ"): _ALEF_BARE,  # U+0671 ALEF WASLA
        ord("ٲ"): _ALEF_BARE,  # U+0672 ALEF WITH WAVY HAMZA ABOVE
        ord("ٳ"): _ALEF_BARE,  # U+0673 ALEF WITH WAVY HAMZA BELOW
        ord("ٵ"): _ALEF_BARE,  # U+0675 HIGH HAMZA ALEF
        ord("ﺁ"): _ALEF_BARE,  # U+FE81 ALEF WITH MADDA ABOVE ISOLATED
        ord("ﺂ"): _ALEF_BARE,  # U+FE82 ALEF WITH MADDA ABOVE FINAL
        ord("ﺃ"): _ALEF_BARE,  # U+FE83 ALEF WITH HAMZA ABOVE ISOLATED
        ord("ﺄ"): _ALEF_BARE,  # U+FE84 ALEF WITH HAMZA ABOVE FINAL
        ord("ﺇ"): _ALEF_BARE,  # U+FE87 ALEF WITH HAMZA BELOW ISOLATED
        ord("ﺈ"): _ALEF_BARE,  # U+FE88 ALEF WITH HAMZA BELOW FINAL
    }
)

# ── 3. alef-maqsura → ya ──────────────────────────────────────────────────────
_ALEF_MAQSURA = str.maketrans({ord("ى"): ord("ي")})  # U+0649 → U+064A

# ── 4. ta-marbuta at word boundary (space or end-of-string) → ha ─────────────
_TA_MARBUTA = re.compile(r"ة(?=\s|$)")

# ── 5+6. diacritics: harakat, tanween, shadda, sukun (064B–0652) + tatweel (0640)
_DIACRITICS = re.compile(r"[ًٌٍَُِّْـ]")

# ── 7. Arabic-Indic digits U+0660–U+0669 → ASCII 0–9 ─────────────────────────
_ARABIC_DIGITS = str.maketrans(
    {0x0660 + i: ord(str(i)) for i in range(10)}
)

# ── 8. non-printable / control chars (keep \n \t \r \x20) ────────────────────
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")

# ── 9. collapse horizontal whitespace runs into one space ────────────────────
# Does NOT touch newlines so paragraph structure is preserved.
_HSPACE = re.compile(r"[^\S\n]+")

# ── 10. collapse 3+ newlines → 2 (two = paragraph break) ────────────────────
_MULTI_NL = re.compile(r"\n{3,}")


def normalize(text: str) -> str:
    """Return the fully normalized form of *text*.

    Input may be raw OCR output or clean text. Empty input is returned as-is.
    The function is idempotent — calling it twice gives the same result.
    """
    if not text:
        return text

    # 1. Unicode NFC
    text = unicodedata.normalize("NFC", text)

    # 2. Alef variants → bare alef
    text = text.translate(_ALEF_VARIANTS)

    # 3. Alef-maqsura → ya
    text = text.translate(_ALEF_MAQSURA)

    # 4. Ta-marbuta → ha at word boundaries
    text = _TA_MARBUTA.sub("ه", text)

    # 5+6. Strip diacritics + tatweel
    text = _DIACRITICS.sub("", text)

    # 7. Arabic-Indic digits → ASCII
    text = text.translate(_ARABIC_DIGITS)

    # 8. Remove control characters
    text = _CONTROL.sub("", text)

    # 9. Collapse horizontal space
    text = _HSPACE.sub(" ", text)

    # 10. Collapse multiple blank lines
    text = _MULTI_NL.sub("\n\n", text)

    # 11. Strip each line
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(lines).strip()
