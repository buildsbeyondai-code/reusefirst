"""Domain layer: text normalisation and closeness scoring. Pure functions, no I/O.

Closeness is a *lexical* estimate (see docs/DECISIONS.md D2):
    closeness = 75% IDF-weighted concept coverage + 25% TF-IDF cosine
Coverage answers "what share of the requirement's key concepts does this
candidate mention?"; cosine rewards candidates focused on those concepts.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Callable, Iterable

# Generic words that carry no product meaning in a requirement.
STOP = frozenset(["a", "an", "and", "are", "as", "at", "be", "been", "but", "by", "can", "could", "do", "does", "for", "from", "has", "have", "how", "i", "if", "in", "into", "is", "it", "its", "me", "my", "of", "on", "or", "our", "should", "so", "some", "such", "than", "that", "the", "their", "them", "then", "there", "these", "they", "this", "to", "too", "up", "us", "was", "we", "were", "what", "when", "where", "which", "while", "who", "will", "with", "would", "you", "your", "any", "all", "also", "each", "etc", "via", "per", "like", "just", "only", "very", "more", "most", "other", "new", "build", "building", "built", "create", "make", "making", "want", "need", "needs", "wanting", "app", "apps", "application", "applications", "software", "tool", "tools", "system", "program", "project", "projects", "rather", "scratch", "instead", "give", "list", "check", "checks", "using", "use", "used", "able", "allow", "allows", "something", "thing", "things", "way", "ways", "help", "helps", "one", "ones", "two", "simple", "basic", "based", "good", "better", "best", "first", "above", "below", "user", "users", "feature", "features", "already", "exists", "exist", "existing", "whether", "requirement", "requirements", "so",
    # 2.0.2: generic English that inflated long requirements (measured neutral on the benchmark)
    "against", "every", "why", "never", "anything", "nothing", "everything", "always", "often", "re", "fully", "mostly", "shows", "show", "showing", "whose", "whom", "yet", "still", "even", "ever", "ok", "okay"])

# (display word used in search queries, synonyms). Matching any synonym counts as the concept.
SYN_GROUPS: list[tuple[str, set[str]]] = [
    ("analysis", {"analyse", "analyze", "analysis", "analyzer", "analyser", "assess", "assessment", "evaluate", "evaluation"}),
    ("requirements", {"requirement", "spec", "specification", "prd"}),
    ("similar", {"similar", "similarity", "closest", "closeness", "match", "matching", "duplicate", "related", "alternative", "alternatives", "nearest"}),
    ("reuse", {"reuse", "reusable", "prior-art", "recommend", "recommendation", "recommender"}),
    ("search", {"search", "find", "finder", "discover", "discovery", "lookup", "explore", "explorer"}),
    ("plugin", {"plugin", "plugins", "extension", "addon", "add-on", "skill", "skills"}),
    ("claude", {"claude", "anthropic", "claude-code"}),
    ("github", {"github", "repository", "repo", "repos"}),
    ("score", {"percentage", "percent", "score", "scoring", "rank", "ranking"}),
    ("dashboard", {"dashboard", "monitor", "monitoring"}),
    ("chatbot", {"chat", "chatbot", "assistant", "conversational"}),
    ("todo", {"todo", "task", "tasks", "kanban"}),
    ("notes", {"note", "notes", "notebook", "notetaking"}),
    ("invoice", {"invoice", "invoicing", "billing", "payment", "payments"}),
    ("authentication", {"auth", "authentication", "login", "oauth", "sso"}),
    ("pdf", {"pdf", "document", "documents", "docx"}),
]

# Generic action verbs say WHAT KIND of work, not which product: they get a reduced weight in scoring (2.0 ranking,
# measured in tests/benchmark). Nouns and domain words carry the requirement's meaning.
ACTION_WEIGHT = 0.35
_ACTIONS_RAW = ["generate", "generates", "generating", "write", "writes", "writing", "track", "tracking", "improve", "improving", "manage", "managing", "run", "running", "deploy", "deploying", "create", "get", "set", "add", "show", "view", "open", "edit", "update", "automate", "automatically", "convert", "send", "find", "monitor", "monitoring", "review", "reviewing"]

_SUFFIXES = ("ization", "isation", "ations", "ation", "ments", "ment", "ities", "ity",
             "ings", "ing", "ers", "er", "ies", "es", "ed", "ly", "s")


def stem(word: str) -> str:
    w = word.lower().strip("-_.")
    for suf in _SUFFIXES:
        if len(w) - len(suf) >= 4 and w.endswith(suf):
            return w[: -len(suf)] + ("y" if suf == "ies" else "")
    return w


_CANON: dict[str, str] = {}
DISPLAY: dict[str, str] = {}
for _display, _group in SYN_GROUPS:
    _key = stem(_display)
    DISPLAY[_key] = _display
    for _w in _group:
        _CANON[stem(_w)] = _key


ACTIONS: frozenset = frozenset()


def norm(word: str) -> str:
    s = stem(word)
    return _CANON.get(s, s)


ACTIONS = frozenset(norm(w) for w in _ACTIONS_RAW)


def weighted(idf: Callable[[str], float]) -> Callable[[str], float]:
    """IDF with generic action verbs down-weighted."""
    return lambda t: idf(t) * (ACTION_WEIGHT if t in ACTIONS else 1.0)


def tokens(text: str) -> list[str]:
    text = (text or "").lower().replace("open source", "opensource").replace("open-source", "opensource")
    return re.findall(r"[a-z][a-z0-9+#]*", text)


def terms(text: str) -> list[str]:
    """Normalised content terms of a text (stop words removed, stemmed, synonyms folded)."""
    return [norm(w) for w in tokens(text) if w not in STOP and len(w) > 1]


def concepts(requirement: str, extra: Iterable[str] = ()) -> list[str]:
    """Distinct key concepts of a requirement, in order of appearance."""
    ts = terms(requirement)
    # "requirement" is a stop word for most apps, but it IS the subject of a requirements-analysis app.
    if re.search(r"\brequirements?\b", requirement, re.I) and re.search(r"\banaly[sz]", requirement, re.I):
        ts.append(norm("requirement"))
    for k in extra:
        ts.extend(terms(k))
    out: list[str] = []
    for t in ts:
        if t not in out and t != "opensource":
            out.append(t)
    return out


MAX_DESC_CHARS = 350  # GitHub's own description limit; longer "descriptions" are pasted documents.


def clip(text: str) -> str:
    return (text or "")[:MAX_DESC_CHARS]


def surface_map(*texts: str) -> dict[str, str]:
    """Concept stem -> first real word that produced it, so queries and labels use real words ("recurring", not "recurr")."""
    out: dict[str, str] = {}
    for text in texts:
        for w in tokens(text):
            if w not in STOP and len(w) > 1:
                out.setdefault(norm(w), w)
    return out


def display(ts: list[str], surface: dict[str, str] | None = None) -> list[str]:
    surface = surface or {}
    return [DISPLAY.get(t) or surface.get(t, t) for t in ts]


def score(req_concepts: list[str], cand_terms: list[str], idf: Callable[[str], float],
          surface: dict[str, str] | None = None) -> dict:
    if not req_concepts or not cand_terms:
        return {"closeness": 0, "coverage": 0, "cosine": 0, "matched": [], "missing": display(req_concepts, surface)}
    cset = set(cand_terms)
    w = {t: idf(t) for t in req_concepts}
    matched = [t for t in req_concepts if t in cset]
    coverage = sum(w[t] for t in matched) / sum(w.values())
    ctf = Counter(cand_terms)
    dot = sum(w[t] * ctf[t] * idf(t) for t in req_concepts if t in ctf)
    na = math.sqrt(sum(v * v for v in w.values()))
    nb = math.sqrt(sum((c * idf(t)) ** 2 for t, c in ctf.items()))
    cos = dot / (na * nb)
    return {"closeness": round(100 * (0.75 * coverage + 0.25 * cos)), "coverage": round(100 * coverage),
            "cosine": round(100 * cos), "matched": display(matched, surface),
            "missing": display([t for t in req_concepts if t not in cset], surface)}


def verdict(pct: int) -> str:
    if pct >= 70:
        return "Reuse: install/configure the top match"
    if pct >= 50:
        return "Fork or extend the top match"
    if pct >= 30:
        return "Borrow parts; build the rest"
    return "Build new: no close match found"
