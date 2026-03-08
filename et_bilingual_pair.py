from __future__ import annotations

import hashlib
from typing import Iterable


_PAIR_PREFIX = "et-pair-"

# Only pair *text-block* tags. Avoid container tags like ol/ul/li/div/section,
# otherwise bilingual lists/endnotes can get incorrectly grouped.
_PAIRABLE_TAGS = {
    "p",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
}


def _lang_of(tag) -> str:
    lang = tag.get("lang") or tag.get("xml:lang") or ""
    return str(lang).strip().lower()


def _is_zh(tag) -> bool:
    return _lang_of(tag).startswith("zh")


def _classes(tag) -> list[str]:
    cls = tag.get("class")
    if not cls:
        return []
    return [c for c in cls if isinstance(c, str)]


def _has_pair_class(tag) -> bool:
    return any(c.startswith(_PAIR_PREFIX) for c in _classes(tag))


def _has_side_class(tag) -> bool:
    cls = _classes(tag)
    return "et-src" in cls or "et-tr" in cls


def _ensure_class(tag, name: str) -> None:
    cls = _classes(tag)
    if name not in cls:
        cls.append(name)
        tag["class"] = cls


def auto_tag_adjacent_zh_pairs_in_soup(
    soup,
    *,
    pair_prefix: str = _PAIR_PREFIX,
    pairable_tags: Iterable[str] = _PAIRABLE_TAGS,
) -> int:
    """Tag adjacent source/zh sibling blocks as `.et-src/.et-tr` with a shared `et-pair-xxx` class.

    This is intentionally *non-destructive*: it does not move nodes or rewrite inner HTML.

    Pairing heuristic (safe-by-default):
    - Only pairs direct siblings under the same parent.
    - Only pairs when both tags are in `pairable_tags` and have the same tag name.
    - Only pairs when the second sibling is `lang=zh*` and the first is not.
    - Skips any element that already has `et-src/et-tr` or an existing `et-pair-*` class.

    Returns number of pairs tagged.
    """

    try:
        from bs4 import Tag  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("BeautifulSoup (bs4) is required.") from exc

    pairable = set(str(t).lower() for t in pairable_tags)

    used: set[str] = set()
    tagged = 0
    seq = 0

    # Collect existing pair classes to avoid accidental reuse.
    for el in soup.find_all(True):
        for c in _classes(el):
            if c.startswith(pair_prefix):
                used.add(c)

    for parent in soup.find_all(True):
        if parent.name in {"script", "style"}:
            continue

        # Build a list of direct Tag children, skipping whitespace NavigableStrings.
        children: list[Tag] = [c for c in parent.children if isinstance(c, Tag)]
        if len(children) < 2:
            continue

        i = 0
        while i < len(children) - 1:
            a = children[i]
            b = children[i + 1]

            a_name = (a.name or "").lower()
            b_name = (b.name or "").lower()

            if a_name != b_name or a_name not in pairable:
                i += 1
                continue

            if _has_side_class(a) or _has_side_class(b) or _has_pair_class(a) or _has_pair_class(b):
                i += 1
                continue

            if _is_zh(a) or not _is_zh(b):
                i += 1
                continue

            # Generate a deterministic-ish pair class. Include seq to avoid collisions.
            seq += 1
            src_text = a.get_text(" ", strip=True)
            tr_text = b.get_text(" ", strip=True)
            payload = f"{seq}|{a_name}|{src_text}||{tr_text}".encode("utf-8")
            h = hashlib.md5(payload).hexdigest()
            pair_class = f"{pair_prefix}{h}"
            while pair_class in used:
                seq += 1
                payload = f"{seq}|{a_name}|{src_text}||{tr_text}".encode("utf-8")
                h = hashlib.md5(payload).hexdigest()
                pair_class = f"{pair_prefix}{h}"

            used.add(pair_class)

            _ensure_class(a, "et-src")
            _ensure_class(b, "et-tr")
            _ensure_class(a, pair_class)
            _ensure_class(b, pair_class)

            tagged += 1
            i += 2

        # next parent

    return tagged
