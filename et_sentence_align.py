from __future__ import annotations

from collections import deque
import re
import sys
import time
from dataclasses import dataclass
from typing import Iterable


DEFAULT_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
_PAIR_PREFIX = "et-pair-"


def split_sentences(text: str) -> list[str]:
    """Heuristic multilingual sentence splitter.

    Notes:
    - Chinese sentence terminators (。！？) do NOT require whitespace after them.
    - English '.' is treated as a terminator unless it looks like a domain/email/decimal (single '.' between ASCII alnum).

    This is intentionally simple; the downstream aligner supports 1↔N merges to tolerate imperfect splitting.
    """

    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []

    def is_ws(ch: str) -> bool:
        return bool(ch) and ch.isspace()

    def is_ascii_alnum(ch: str) -> bool:
        return bool(ch) and ch.isascii() and ch.isalnum()

    out: list[str] = []
    start = 0
    i = 0

    def push(end: int) -> None:
        nonlocal start
        if end <= start:
            return
        out.append(text[start:end])
        start = end

    while i < len(text):
        ch = text[i]

        if ch in ("。", "！", "？", "!", "?"):
            end = i + 1
            while end < len(text) and text[end] in ("。", "！", "？", "!", "?"):
                end += 1
            while end < len(text) and is_ws(text[end]):
                end += 1
            push(end)
            i = end
            continue

        if ch == ".":
            j = i
            while j < len(text) and text[j] == ".":
                j += 1

            prev = text[i - 1] if i > 0 else ""
            next_ = text[j] if j < len(text) else ""
            dot_count = j - i

            # Single dot between ASCII alnum => likely domain/email/decimal/version; do not split.
            if dot_count == 1 and is_ascii_alnum(prev) and is_ascii_alnum(next_):
                i = j
                continue

            end2 = j
            while end2 < len(text) and is_ws(text[end2]):
                end2 += 1
            push(end2)
            i = end2
            continue

        i += 1

    if start < len(text):
        out.append(text[start:])

    return out


@dataclass(frozen=True)
class AlignmentGroup:
    src: list[int]
    tr: list[int]
    score: float


def _find_pair_class(tag_classes: Iterable[str]) -> str | None:
    for c in tag_classes:
        if isinstance(c, str) and c.startswith(_PAIR_PREFIX):
            return c
    return None


def align_sentence_groups(
    src_sentences: list[str],
    tr_sentences: list[str],
    *,
    model=None,
    model_name: str = DEFAULT_MODEL_NAME,
    max_group: int = 3,
    merge_penalty: float = 0.05,
    skip_penalty: float = 0.60,
) -> list[AlignmentGroup]:
    """Align two sentence lists with a monotonic DP using multilingual sentence embeddings.

    Returns alignment groups (each group can be 1↔1, 1↔N, N↔1, N↔N up to `max_group`).

    Requires: sentence-transformers (and its deps).
    """

    if not src_sentences or not tr_sentences:
        return []

    if max_group < 1:
        raise ValueError("max_group must be >= 1")

    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("Missing dependency: numpy. Install sentence-transformers (it brings numpy).") from exc

    if model is None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "Missing dependency: sentence-transformers. Run: pip install sentence-transformers"
            ) from exc
        model = SentenceTransformer(model_name)

    # Encode both sides in one batch (better throughput).
    all_sents = src_sentences + tr_sentences
    emb = model.encode(all_sents, convert_to_numpy=True, normalize_embeddings=True)
    src_emb = emb[: len(src_sentences)]
    tr_emb = emb[len(src_sentences) :]

    return align_sentence_groups_from_embeddings(
        src_emb,
        tr_emb,
        max_group=max_group,
        merge_penalty=merge_penalty,
        skip_penalty=skip_penalty,
    )


def align_sentence_groups_from_embeddings(
    src_emb,
    tr_emb,
    *,
    max_group: int = 1,
    merge_penalty: float = 0.05,
    skip_penalty: float = 0.60,
) -> list[AlignmentGroup]:
    """DP alignment on already-computed (normalized) embeddings."""

    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("Missing dependency: numpy.") from exc

    n = int(getattr(src_emb, "shape", [len(src_emb)])[0])
    m = int(getattr(tr_emb, "shape", [len(tr_emb)])[0])
    if n <= 0 or m <= 0:
        return []

    if max_group < 1:
        raise ValueError("max_group must be >= 1")

    def normalize(v: "np.ndarray") -> "np.ndarray":
        norm = float(np.linalg.norm(v))
        if norm <= 1e-12:
            return v
        return v / norm

    def group_vec(vectors: "np.ndarray", start: int, count: int) -> "np.ndarray":
        if count == 1:
            return vectors[start]
        v = vectors[start : start + count].mean(axis=0)
        return normalize(v)

    neg_inf = -1e18
    dp = [[neg_inf] * (m + 1) for _ in range(n + 1)]
    bp: list[list[tuple[int, int, int, int] | None]] = [[None] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = 0.0

    for i in range(n + 1):
        for j in range(m + 1):
            base = dp[i][j]
            if base <= neg_inf / 2:
                continue

            # Match moves: a↔b
            for a in range(1, max_group + 1):
                if i + a > n:
                    break
                src_v = group_vec(src_emb, i, a)
                for b in range(1, max_group + 1):
                    if j + b > m:
                        break
                    tr_v = group_vec(tr_emb, j, b)
                    sim = float(src_v @ tr_v)
                    score = base + sim - merge_penalty * ((a - 1) + (b - 1))
                    ni, nj = i + a, j + b
                    if score > dp[ni][nj]:
                        dp[ni][nj] = score
                        bp[ni][nj] = (i, j, a, b)

            # Skip moves (rare, but helps when one side has extra fragments).
            if i + 1 <= n:
                score = base - skip_penalty
                if score > dp[i + 1][j]:
                    dp[i + 1][j] = score
                    bp[i + 1][j] = (i, j, 1, 0)

            if j + 1 <= m:
                score = base - skip_penalty
                if score > dp[i][j + 1]:
                    dp[i][j + 1] = score
                    bp[i][j + 1] = (i, j, 0, 1)

    # Backtrack.
    groups: list[AlignmentGroup] = []
    i, j = n, m
    while i != 0 or j != 0:
        step = bp[i][j]
        if step is None:
            if i > 0 and j > 0:
                groups.append(AlignmentGroup(src=list(range(i)), tr=list(range(j)), score=0.0))
            break

        pi, pj, a, b = step
        if a > 0 and b > 0:
            src_v = group_vec(src_emb, pi, a)
            tr_v = group_vec(tr_emb, pj, b)
            sim = float(src_v @ tr_v)
            groups.append(
                AlignmentGroup(
                    src=list(range(pi, pi + a)),
                    tr=list(range(pj, pj + b)),
                    score=sim,
                )
            )

        i, j = pi, pj

    groups.reverse()
    return groups


def build_index_mapping(
    src_count: int,
    tr_count: int,
    groups: list[AlignmentGroup],
) -> tuple[list[list[int]], list[list[int]]]:
    """Build per-sentence index mapping from aligned groups.

    Important behavior:
    - For 1↔N or N↔1 groups, we keep many-to-one / one-to-many (highlight multiple sentences).
    - For N↔N groups (N>1), mapping every sentence to the full opposite group is too coarse and
      makes the UI look like "one sentence highlights the whole paragraph". In that case we
      distribute correspondences by relative position within the group (rough 1-to-1).
    """

    src_to_tr: list[list[int]] = [[] for _ in range(src_count)]
    tr_to_src: list[list[int]] = [[] for _ in range(tr_count)]

    def map_index(k: int, k_count: int, t_count: int) -> int:
        if t_count <= 1:
            return 0
        if k_count <= 1:
            return 0
        mapped = round(k * (t_count - 1) / (k_count - 1))
        return max(0, min(t_count - 1, int(mapped)))

    for g in groups:
        a = len(g.src)
        b = len(g.tr)
        if a == 0 or b == 0:
            continue

        if a == 1 and b == 1:
            si = g.src[0]
            ti = g.tr[0]
            src_to_tr[si].append(ti)
            tr_to_src[ti].append(si)
            continue

        if a == 1:
            si = g.src[0]
            src_to_tr[si].extend(g.tr)
            for ti in g.tr:
                tr_to_src[ti].append(si)
            continue

        if b == 1:
            ti = g.tr[0]
            tr_to_src[ti].extend(g.src)
            for si in g.src:
                src_to_tr[si].append(ti)
            continue

        # N↔N (both > 1): distribute by relative position.
        for idx, si in enumerate(g.src):
            mapped_t = g.tr[map_index(idx, a, b)]
            src_to_tr[si].append(mapped_t)

        for idx, ti in enumerate(g.tr):
            mapped_s = g.src[map_index(idx, b, a)]
            tr_to_src[ti].append(mapped_s)

    # Dedup + sort.
    src_to_tr = [sorted(set(v)) for v in src_to_tr]
    tr_to_src = [sorted(set(v)) for v in tr_to_src]
    return src_to_tr, tr_to_src


def _fill_single_index_mapping(mapping: list[list[int]], target_count: int) -> list[int]:
    """Convert 0/1-valued mapping lists into a dense 1-valued mapping.

    For indices with missing mapping, fill by linear interpolation between nearest known anchors.
    If there are no anchors, fall back to relative-position mapping.
    """

    n = len(mapping)
    if n == 0:
        return []
    if target_count <= 0:
        return [0] * n

    single: list[int | None] = [v[0] if v else None for v in mapping]
    anchors = [(i, v) for i, v in enumerate(single) if v is not None]

    def rel_map(i: int) -> int:
        if n <= 1:
            return 0
        return int(round(i * (target_count - 1) / (n - 1)))

    if not anchors:
        return [rel_map(i) for i in range(n)]

    # Fill leading.
    first_i, first_v = anchors[0]
    for i in range(0, first_i):
        single[i] = first_v

    # Fill gaps.
    for (i0, v0), (i1, v1) in zip(anchors, anchors[1:]):
        gap = i1 - i0
        if gap <= 1:
            continue
        for i in range(i0 + 1, i1):
            t = (i - i0) / gap
            single[i] = int(round(v0 + t * (v1 - v0)))

    # Fill trailing.
    last_i, last_v = anchors[-1]
    for i in range(last_i + 1, n):
        single[i] = last_v

    # Clamp.
    out: list[int] = []
    for v in single:
        if v is None:
            out.append(rel_map(len(out)))
            continue
        out.append(max(0, min(target_count - 1, int(v))))
    return out


def align_et_pairs_in_soup(
    soup,
    *,
    model_name: str = DEFAULT_MODEL_NAME,
    max_group: int = 1,
    merge_penalty: float = 0.05,
    skip_penalty: float = 0.60,
    min_group_score: float = 0.15,
    show_progress: bool = True,
    progress_width: int = 28,
    progress_min_interval_s: float = 0.25,
    encode_batch_size: int = 64,
    chunk_max_sentences: int = 2048,
) -> int:
    """Find `.et-src/.et-tr` pairs and compute sentence-level alignment.

    Writes alignment metadata onto the original elements:
    - `data-et-uid`: unique id per paired element instance (avoids collisions if `et-pair-xxx` repeats)
    - `data-et-map`: comma-separated int list, mapping sentence index -> counterpart sentence index (one-to-one UX)
    - `data-et-sent-count`: sentence count used when producing `data-et-map`

    This function is intentionally **non-destructive**: it does NOT rewrite/flatten HTML content,
    so original markup (links, superscripts, lists, line breaks) stays intact.
    """

    nodes = soup.select(".et-src, .et-tr")

    # Pair up paragraphs first (FIFO per et-pair-xxx) to know the exact total.
    pending_src: dict[str, deque] = {}
    pending_tr: dict[str, deque] = {}
    pairs: list[tuple[object, object]] = []

    for el in nodes:
        classes = el.get("class") or []
        pair_class = _find_pair_class(classes)
        if not pair_class:
            continue
        is_src = "et-src" in classes
        is_tr = "et-tr" in classes
        if not (is_src or is_tr):
            continue

        if is_src:
            q = pending_tr.get(pair_class)
            if q and len(q) > 0:
                tr_el = q.popleft()
                pairs.append((el, tr_el))
            else:
                pending_src.setdefault(pair_class, deque()).append(el)
        else:
            q = pending_src.get(pair_class)
            if q and len(q) > 0:
                src_el = q.popleft()
                pairs.append((src_el, el))
            else:
                pending_tr.setdefault(pair_class, deque()).append(el)

    total_pairs = len(pairs)
    if total_pairs <= 0:
        return 0

    # Lazily load the embedding model once per document.
    if show_progress:
        print(f"Loading SentenceTransformer model: {model_name}", file=sys.stderr)
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency: sentence-transformers. Run: pip install sentence-transformers"
        ) from exc

    model = SentenceTransformer(model_name)

    last_draw = 0.0

    def draw_progress(done: int, *, final: bool = False) -> None:
        nonlocal last_draw
        if not show_progress:
            return
        now = time.time()
        if not final and (now - last_draw) < progress_min_interval_s:
            return
        last_draw = now

        if total_pairs <= 0:
            return
        pct = max(0.0, min(1.0, done / total_pairs))
        filled = int(round(progress_width * pct))
        bar = "#" * filled + "-" * (progress_width - filled)
        sys.stderr.write(f"\rAligning bilingual pairs: [{bar}] {done}/{total_pairs} ({pct*100:5.1f}%)")
        sys.stderr.flush()

    pending_src: dict[str, list] = {}
    pending_tr: dict[str, list] = {}

    def pop_or_none(d: dict[str, list], key: str):
        q = d.get(key)
        if not q:
            return None
        return q.pop(0)

    def push(d: dict[str, list], key: str, v) -> None:
        d.setdefault(key, []).append(v)

    aligned = 0
    uid_counter = 0

    # Chunk paragraph-pairs and batch encode all sentences in the chunk.
    chunk: list[tuple[object, object, list[str], list[str]]] = []
    chunk_sentence_count = 0

    def process_chunk() -> None:
        nonlocal aligned
        nonlocal chunk
        nonlocal chunk_sentence_count

        if not chunk:
            return

        texts: list[str] = []
        meta: list[tuple[object, object, list[str], list[str], int, int, int, int]] = []

        for src_el, tr_el, src_sents, tr_sents in chunk:
            src_start = len(texts)
            texts.extend(src_sents)
            tr_start = len(texts)
            texts.extend(tr_sents)
            meta.append((src_el, tr_el, src_sents, tr_sents, src_start, len(src_sents), tr_start, len(tr_sents)))

        emb = model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            batch_size=encode_batch_size,
            show_progress_bar=False,
        )

        for src_el, tr_el, src_sents, tr_sents, src_start, src_len, tr_start, tr_len in meta:
            src_emb = emb[src_start : src_start + src_len]
            tr_emb = emb[tr_start : tr_start + tr_len]

            groups = align_sentence_groups_from_embeddings(
                src_emb,
                tr_emb,
                max_group=max_group,
                merge_penalty=merge_penalty,
                skip_penalty=skip_penalty,
            )

            use_groups = groups
            if groups and min(g.score for g in groups) < min_group_score:
                use_groups = [
                    AlignmentGroup(
                        src=list(range(len(src_sents))),
                        tr=list(range(len(tr_sents))),
                        score=0.0,
                    )
                ]

            src_to_tr, tr_to_src = build_index_mapping(len(src_sents), len(tr_sents), use_groups)

            # Force one-to-one UX: each sentence maps to exactly one sentence index.
            src_single = _fill_single_index_mapping(src_to_tr, len(tr_sents))
            tr_single = _fill_single_index_mapping(tr_to_src, len(src_sents))

            # Persist alignment mapping without touching inner HTML.
            src_el["data-et-sent-count"] = str(len(src_sents))
            tr_el["data-et-sent-count"] = str(len(tr_sents))
            src_el["data-et-map"] = ",".join(str(j) for j in src_single)
            tr_el["data-et-map"] = ",".join(str(i) for i in tr_single)

            aligned += 1
            draw_progress(aligned)

        chunk = []
        chunk_sentence_count = 0

    for src_el, tr_el in pairs:
        uid_counter += 1
        uid = str(uid_counter)
        src_el["data-et-uid"] = uid
        tr_el["data-et-uid"] = uid

        src_text = src_el.get_text(" ", strip=True)
        tr_text = tr_el.get_text(" ", strip=True)

        src_sents = split_sentences(src_text) or ([src_text] if src_text else [])
        tr_sents = split_sentences(tr_text) or ([tr_text] if tr_text else [])

        chunk.append((src_el, tr_el, src_sents, tr_sents))
        chunk_sentence_count += len(src_sents) + len(tr_sents)

        if chunk_sentence_count >= chunk_max_sentences:
            process_chunk()

    process_chunk()

    draw_progress(aligned, final=True)
    if show_progress:
        sys.stderr.write("\n")
        sys.stderr.flush()

    return aligned
