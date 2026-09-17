"""The deterministic screen over what the model proposed.

The model is asked for a premise *and* for the fragment of the control's own text
it read the premise from. This module makes that second half worth asking for: the
quote has to actually be in the control, so a premise recalled from training
rather than found in the sentence is dropped mechanically, with a reason, instead
of being argued about at review time.

Nothing here is thrown away silently: a refused premise travels to the proposal
file as a `RejectedPremise` carrying the guard's reason, because the reviewer is
the authority and the guard is a filter that can be wrong.
"""

from __future__ import annotations

import re
import unicodedata

from app.catalog.schemas import Presupposition
from app.tagging.schemas import PremiseDraft, RejectedPremise

# A quote shorter than this anchors nothing: "de" appears in every control in the
# catalog, so accepting it would make the check pass while checking nothing.
MIN_QUOTE_CHARS = 12

_NON_WORD = re.compile(r"[^\w\s]+")
_SPACES = re.compile(r"\s+")


def normalise(text: str) -> str:
    """Lower-case, accent-free, punctuation-free, single-spaced.

    The model is quoting prose back at us, and it re-types rather than copies:
    accents drift, a comma is dropped, the casing of the first word changes. None
    of that should decide whether a premise survives, and all of it would if the
    comparison were literal.
    """
    decomposed = unicodedata.normalize("NFD", text.lower())
    stripped = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return _SPACES.sub(" ", _NON_WORD.sub(" ", stripped)).strip()


def screen(
    drafts: list[PremiseDraft], title: str, description: str
) -> tuple[list[Presupposition], list[RejectedPremise]]:
    """Split what the model proposed into what is anchored and what is not."""
    source = normalise(f"{title} {description}")
    kept: list[Presupposition] = []
    rejected: list[RejectedPremise] = []
    seen: set[str] = set()

    for draft in drafts:
        reason = _refusal(draft, source, seen)
        if reason is not None:
            rejected.append(
                RejectedPremise(
                    premise=draft.premise.value,
                    expected=draft.expected,
                    note=draft.note,
                    quote=draft.quote,
                    reason=reason,
                )
            )
            continue

        seen.add(draft.premise.value)
        kept.append(
            Presupposition(premise=draft.premise, expected=draft.expected, note=draft.note.strip())
        )

    return kept, rejected


def _refusal(draft: PremiseDraft, source: str, seen: set[str]) -> str | None:
    """Why this premise may not stand, or `None` when it may. Spanish: it is read."""
    if draft.premise.value in seen:
        return "La premisa ya estaba declarada para este control; se conserva la primera lectura."

    quote = normalise(draft.quote)
    if len(quote) < MIN_QUOTE_CHARS:
        return (
            f"La cita es demasiado corta para anclar la premisa "
            f"({len(quote)} caracteres, mínimo {MIN_QUOTE_CHARS})."
        )
    if quote not in source:
        return "La cita no aparece en el título ni en la descripción del control."
    if not draft.note.strip():
        return (
            "La premisa llega sin explicación, y una premisa que nadie sabe explicar "
            "es un filtro."
        )

    return None
