# -*- coding: utf-8 -*-
"""Chinese punctuation normalization.

Deterministic rule engine - no LLM calls.
Runs on every manuscript before writing to disk.
"""

from __future__ import annotations

import re


def normalize_punctuation(text: str) -> tuple[str, list[str]]:
    """Normalize Chinese punctuation in text.

    Returns (normalized_text, list_of_change_descriptions).
    """
    changes: list[str] = []
    result = text

    # 1. Three English dots -> Chinese ellipsis (before other replacements
    #    because other fixes may introduce dots in other contexts)
    cnt = result.count("...")
    if cnt:
        result = result.replace("...", "……")
        changes.append(f"ellipsis ... -> ... ({cnt} places)")

    # 2. Two English dots -> Chinese ellipsis
    cnt = result.count("..")
    if cnt:
        result = result.replace("..", "……")
        changes.append(f"ellipsis .. -> ... ({cnt} places)")

    # 3. Halfwidth -> fullwidth punctuation in Chinese context
    result = _normalize_fullwidth(result, changes)

    # 4. Quotes: English quotes -> Chinese double quotes (alternating left/right)
    result = _normalize_quotes(result, changes)

    # 5. Single em-dash -> double em-dash in Chinese context
    result = _normalize_dashes(result, changes)

    # 6. Remove extra spaces around Chinese punctuation
    result = _remove_spaces_around_cjk_punct(result, changes)

    # 7. Dialogue tag punctuation
    result = _normalize_dialogue_tags(result, changes)

    return result, changes


# Mapping: halfwidth -> fullwidth
_HALF_TO_FULL = {
    ",": "，",  # ，
    "!": "！",  # ！
    "?": "？",  # ？
    ":": "：",  # ：
    ";": "；",  # ；
    "(": "（",  # （
    ")": "）",  # ）
}


def _is_cjk(ch: str) -> bool:
    """Check if character is CJK (Chinese/Japanese/Korean) or fullwidth form."""
    cp = ord(ch)
    return (
        (0x4E00 <= cp <= 0x9FFF)       # CJK Unified
        or (0x3400 <= cp <= 0x4DBF)     # CJK Extension A
        or (0xF900 <= cp <= 0xFAFF)     # CJK Compatibility
        or (0xFF00 <= cp <= 0xFFEF)     # Fullwidth forms
        or (0x3000 <= cp <= 0x303F)     # CJK punctuation
    )


def _normalize_fullwidth(text: str, changes: list[str]) -> str:
    """Replace halfwidth punctuation with fullwidth in Chinese context.

    Only replaces when the punctuation is adjacent to CJK characters.
    Preserves dots between digits (e.g. 3.14, ch.3).
    """
    result = list(text)
    modified = 0

    for i, ch in enumerate(result):
        if ch not in _HALF_TO_FULL:
            continue

        # Period between digits: preserve (3.14, ch.3)
        if ch == "." and i > 0 and result[i - 1].isdigit():
            continue
        if ch == "." and i + 1 < len(result) and result[i + 1].isdigit():
            continue

        prev_cjk = i > 0 and _is_cjk(result[i - 1])
        next_cjk = i + 1 < len(result) and _is_cjk(result[i + 1])

        # Parentheses: left paren looks right, right paren looks left
        if ch == "(":
            if next_cjk:
                result[i] = "（"  # （
                modified += 1
        elif ch == ")":
            if prev_cjk:
                result[i] = "）"  # ）
                modified += 1
        elif prev_cjk or next_cjk:
            result[i] = _HALF_TO_FULL[ch]
            modified += 1

    if modified:
        changes.append(f"halfwidth->fullwidth ({modified} places)")
    return "".join(result)


def _normalize_quotes(text: str, changes: list[str]) -> str:
    """Replace English quotes with Chinese double quotes.

    Strategy: for CJK-adjacent quotes, alternate left/right based on
    their order of appearance. The first is left, second right, etc.
    This handles 95%+ of cases correctly without NLP.
    """
    result = list(text)
    modified = 0

    # First pass: collect all CJK-adjacent quote positions
    positions = []
    for i, ch in enumerate(result):
        if ch not in ('"', '“', '”', '‘', '’'):
            continue
        prev_char = result[i - 1] if i > 0 else ''
        next_char = result[i + 1] if i + 1 < len(result) else ''
        prev_cjk = bool(prev_char) and _is_cjk(prev_char)
        next_cjk = bool(next_char) and _is_cjk(next_char)
        if prev_cjk or next_cjk:
            positions.append(i)

    if not positions:
        return text

    # Second pass: alternate left/right in order of appearance
    use_left = True
    for i in positions:
        result[i] = '“' if use_left else '”'  # " or "
        use_left = not use_left
        modified += 1

    if modified:
        changes.append(f"quote normalization ({modified} places)")
    return "".join(result)


def _normalize_dashes(text: str, changes: list[str]) -> str:
    """Ensure em-dashes in Chinese context use double width.

    Single U+2014 (em-dash) between CJK chars -> U+2014U+2014.
    Preserves: number ranges (10-20), already-double dashes.
    """
    result = list(text)
    modified = 0

    i = 0
    while i < len(result):
        ch = result[i]
        if ch != '—':  # em-dash
            i += 1
            continue

        # Already double? Skip both
        if i + 1 < len(result) and result[i + 1] == '—':
            i += 2
            continue

        prev_cjk = i > 0 and _is_cjk(result[i - 1])
        next_cjk = i + 1 < len(result) and _is_cjk(result[i + 1])
        prev_digit = i > 0 and result[i - 1].isdigit()
        next_digit = i + 1 < len(result) and result[i + 1].isdigit()

        # Number range: preserve
        if prev_digit and next_digit:
            i += 1
            continue

        # Mixed digit/CJK at boundary: preserve (e.g. "3—五")
        if (prev_digit and next_cjk) or (prev_cjk and next_digit):
            i += 1
            continue

        if prev_cjk or next_cjk:
            result[i] = '——'  # —— as two chars
            modified += 1

        i += 1

    if modified:
        text_result = "".join(result)
        text_result = text_result.replace('————', '——')
        changes.append(f"em-dash fix ({modified} places)")
        return text_result

    return "".join(result)


def _remove_spaces_around_cjk_punct(text: str, changes: list[str]) -> str:
    """Remove extra spaces around Chinese fullwidth punctuation."""
    result = re.sub(
        r'\s+([　-〿＀-￯])',
        r'\1',
        text,
    )
    result = re.sub(
        r'([（《「［])\s+',  # （《「［
        r'\1',
        result,
    )
    if result != text:
        changes.append("removed spaces around CJK punctuation")
    return result


def _normalize_dialogue_tags(text: str, changes: list[str]) -> str:
    """Fix common dialogue tag punctuation issues.

    "XX说" after a closing quote should have a comma before the quote.
    Pattern: close-quote + speech-verb -> close-quote + comma + speech-verb
    """
    result = text
    modified = 0

    # Pattern: closing quote followed directly by speech verb + content
    # e.g. 他说"..." -> 他说，"..."  (already correct, just checking)
    # e.g. "..."他说 -> "...，"他说
    result = re.sub(
        r'(”)([说答道问喊叫回应叹])',
        r'\1，\2',
        result,
    )
    cnt = len(re.findall(r'”，[说答道问喊叫回应叹]', result))
    modified = cnt

    if modified:
        changes.append(f"dialogue tag punctuation ({modified} places)")
    return result


def normalize_and_log(text: str, label: str = "") -> str:
    """Normalize punctuation and print changes to terminal."""
    normalized, changes = normalize_punctuation(text)
    if changes:
        prefix = f"[MCW-PUNCT] {label}: " if label else "[MCW-PUNCT] "
        print(prefix + " | ".join(changes))
    return normalized
