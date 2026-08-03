"""UCM-14 - The presentational guard: the check that the model only explained.

The prompt asks the model to describe and never to advise. This module is what
makes that an enforced property instead of a hope, because a 7B model that is
asked to be helpful will eventually be helpful in the one way it must not: "el
mejor candidato", "debería elegir", "descarte los demás". Two deterministic
checks, both run on every generated text:

* **No verdict language.** A declared Spanish lexicon of recommendation,
  obligation, selection and comparison. A hit withholds the prose.
* **No ungrounded citation.** The `basis` the model returns must be a subset of
  the evidence that candidate actually has (`evidence.py`). Citing a similarity
  score a catalog candidate never had is a fabrication, and a fluent fabrication
  next to a real control is worse than no sentence at all.

What "withheld" means matters as much as the checks: the *prose* is dropped and
the candidate stays exactly where it was, with the engine's own deterministic
rationale in its place and the reason written next to it. The guard can never
remove a candidate, reorder one, or change a score — it only ever decides which
of two texts is shown.

Two limits, declared rather than discovered. A lexicon catches the phrasings it
lists and not a verdict expressed in words nobody wrote down; and it is the
prompt, not the guard, that does most of the work. The guard is the net, not the
floor — it turns a silent breach of invariant 1 into a visible one.

Negations are skipped on purpose: "la similitud no descarta la equivalencia" is
description, not instruction, and withholding it would train the reader to
ignore the flag.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

from app.core.wording import say_all
from app.explain.schemas import EvidenceKey

# Category -> pattern. The category names are Spanish because they end up in the
# reason the operator reads. Patterns run over accent-stripped lower-case text,
# so `deberia` also catches `debería`.
VERDICT_LEXICON: tuple[tuple[str, str], ...] = (
    (
        "recomendación",
        r"\b(recomiendo|recomendamos|recomienda|recomendabl\w*|recomendad\w*|recomendacion\w*"
        r"|aconsej\w+|sugiero|conviene)\b",
    ),
    ("obligación", r"\b(deberi\w+|debes|debe usted|tiene que|es necesario que)\b"),
    (
        "instrucción de selección",
        r"\b(elija|elige|escoja|escoge|seleccione|selecciona|adopte|adopta|descarte|descarta"
        r"|priorice|prioriza|implemente|implementa|utilice|utiliza)\b",
    ),
    (
        "juicio comparativo",
        r"\b(mejor|peor|optim[oa]s?|idone[oa]s?|preferible|superior|mas adecuad\w*"
        r"|mas apropiad\w*|mas complet\w*|mas fuerte|mas debil)\b",
    ),
    (
        "orden o ranking",
        r"\b(primera opcion|opcion principal|opcion recomendada|ranking|clasificacion)\b",
    ),
)

COMPILED: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (category, re.compile(pattern)) for category, pattern in VERDICT_LEXICON
)

# A verdict under negation is a description of a limit, not advice.
NEGATIONS = frozenset({"no", "ni", "nunca", "jamas", "tampoco", "sin"})

WORD = re.compile(r"[\w]+")


def normalise(text: str) -> str:
    """Lower-case and accent-free, so the lexicon does not depend on typing."""
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")


@dataclass(frozen=True)
class GuardVerdict:
    """Whether this prose may be shown, and — when it may not — why not."""

    passed: bool
    # The exact terms found, in the order they appear. Reported, never guessed at.
    matches: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()
    # Evidence keys the model cited without the candidate having them.
    ungrounded: tuple[EvidenceKey, ...] = ()
    # Spanish, for the operator: withholding without saying so would be its own
    # silent omission.
    reason: str | None = None


def verdict_terms(text: str) -> list[tuple[str, str]]:
    """Every verdict term in the text, as (category, term), negations skipped."""
    normalised = normalise(text)
    found: list[tuple[str, str]] = []
    for category, pattern in COMPILED:
        for match in pattern.finditer(normalised):
            if _negated(normalised, match.start()):
                continue
            found.append((category, match.group(0)))
    return found


def screen(
    text: str,
    basis: Iterable[EvidenceKey] = (),
    allowed: Iterable[EvidenceKey] = (),
) -> GuardVerdict:
    """Decide whether a generated explanation may be shown as written."""
    terms = verdict_terms(text)
    permitted = set(allowed)
    ungrounded = tuple(key for key in dict.fromkeys(basis) if key not in permitted)

    if not terms and not ungrounded:
        return GuardVerdict(passed=True)

    return GuardVerdict(
        passed=False,
        matches=tuple(term for _, term in terms),
        categories=tuple(dict.fromkeys(category for category, _ in terms)),
        ungrounded=ungrounded,
        reason=_reason(terms, ungrounded),
    )


def _negated(text: str, start: int) -> bool:
    """True when the word right before the match negates it."""
    before = WORD.findall(text[:start])
    return bool(before) and before[-1] in NEGATIONS


def _reason(terms: list[tuple[str, str]], ungrounded: tuple[EvidenceKey, ...]) -> str:
    parts: list[str] = []
    if terms:
        categories = ", ".join(dict.fromkeys(category for category, _ in terms))
        quoted = ", ".join(f"«{term}»" for term in dict.fromkeys(term for _, term in terms))
        parts.append(
            f"el texto generado contenía lenguaje de decisión ({categories}): {quoted}"
        )
    if ungrounded:
        keys = say_all(ungrounded)
        parts.append(
            f"la explicación citaba evidencia que este candidato no tiene ({keys})"
        )
    return (
        "Explicación retenida: "
        + "; ".join(parts)
        + ". Se muestra la justificación determinista del motor. La capa de explicaciones es "
        "presentacional: no ordena, no selecciona y no descarta — eso lo hacen las reglas y el "
        "humano. El candidato sigue disponible sin ningún cambio."
    )
