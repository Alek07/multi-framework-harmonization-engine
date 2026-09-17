"""How the engine's enum values are written in the Spanish text an operator reads.

Every `rationale`, `decision` and `notice` the API returns is read by a human
(language rule, CLAUDE.md §8). Interpolating an enum with `.value` put English
snake_case identifiers inside otherwise-Spanish sentences; this module is the one
lookup table that turns those into words. It is presentational and nothing else:
it never decides, filters or orders — only the prose changes.

Lookup is by the enum's *value* rather than the enum type, deliberately: this
module is imported by `engine`, `retrieval`, `baseline`, `delta` and `audit`, and
importing their schema modules back into `core` would close an import cycle.
"""

from collections.abc import Iterable
from enum import Enum

_WORDS: dict[str, str] = {
    # --- zones (ZoneDomain) ---
    "OT": "industrial (OT)",
    "IT": "ofimático (IT)",
    "HYBRID": "mixto IT/OT",
    # --- conflicts (ConflictType, ResolutionMethod) ---
    "overlap": "solape de alcance",
    "granularity": "granularidad 1:N",
    "contradiction": "contradicción real",
    "collapsed": "colapso por capacidad",
    "coverage_weights": "pesos de cobertura",
    "framework_precedence": "precedencia de marco",
    "safety_override": "override de seguridad de la planta",
    # --- gaps (GapKind) ---
    "no_candidate": "sin candidato",
    "no_effective_mechanism": "sin mecanismo aplicable",
    "partial_only": "solo cobertura parcial",
    "residual_coverage": "cobertura residual",
    # --- gating (GatingOutcome, CapabilityStatus) ---
    "not_applicable": "no aplica",
    "wrong_scope": "ámbito equivocado",
    "objective_without_mechanism": "objetivo sin mecanismo",
    "covered_by_mechanism": "cubierta por un mecanismo del activo",
    "compensatory_required": "requiere control compensatorio",
    "deferred_to_organizational_layer": "diferida a la capa organizativa",
    # --- prioritisation (PriorityTier, OrdinalLevel, MandateSource) ---
    "tier_0": "Tier 0",
    "tier_1": "Tier 1",
    "low": "baja",
    "medium": "media",
    "high": "alta",
    "sl_target": "SL-objetivo de la zona",
    "legal_obligation": "obligación legal",
    # --- catalog (MappingType, ProvenanceSource, ControlType) ---
    "total": "total",
    "partial": "parcial",
    "compensatory": "compensatorio",
    "contextual": "contextual",
    "official_crosswalk": "crosswalk oficial",
    "author_judgment": "juicio del autor del catálogo",
    "technical": "técnico",
    "legal": "legal",
    # --- retrieval (FilterAxis, RetrievalRelation, CandidateStatus) ---
    "jurisdiction": "jurisdicción",
    "zone": "zona",
    "mapping_type": "tipo de mapeo",
    "sector": "ámbito sectorial",
    "widens": "amplía la cobertura ofrecida",
    "confirms_mapping": "confirma un mapeo del catálogo",
    "eligible": "elegible",
    "superseded": "apartado por una regla",
    "contested": "en disputa",
    # --- composition (ChoiceKind, SelectionOrigin) ---
    "option_selected": "elección de un mecanismo",
    "option_rejected": "descarte de un mecanismo",
    "compensatory_declared": "declaración de un control compensatorio",
    "gap_accepted": "aceptación de un hueco",
    "catalog_mapping": "mapeo del catálogo",
    "adopted_suggestion": "sugerencia adoptada",
    # --- the declaration of applicability (MechanismDisposition, CapabilityOutcome) ---
    # `not_applicable`, `wrong_scope` and `objective_without_mechanism` are the
    # gating words above: an exclusion in the declaration *is* a gating outcome,
    # and saying it twice with two wordings would suggest they were two things.
    "selected": "elegido por el operador",
    "ratified": "ratificado al firmar",
    "offered": "ofrecido, no elegido",
    "rejected": "descartado por el operador",
    "implemented": "cubierta por un mecanismo incorporado",
    "compensated": "cubierta por un control compensatorio",
    "deferred": "diferida a la capa organizativa",
    "accepted_gap": "hueco aceptado por escrito",
    "open_gap": "hueco abierto",
    "roadmap": "discrecional, en la hoja de ruta",
    # --- jurisdictions, where the raw value is not a word ---
    "INTL-MARITIME": "internacional marítima",
    "INTL": "internacional",
    # --- sectors (Sector), for the sectoral-applicability exclusion ---
    "energy": "energía",
    "water": "agua",
    "maritime": "marítimo",
    "transport": "transporte",
    "health": "salud",
    "digital_infrastructure": "infraestructura digital",
    "banking_finance": "banca y finanzas",
    "public_administration": "administración pública",
    "manufacturing": "fabricación",
    "chemical": "químico",
    "food": "alimentación",
    # --- the facts an explanation may lean on (EvidenceKey) ---
    # `catalog_mapping`, `mapping_type` and `jurisdiction` are already above:
    # `SelectionOrigin` and `FilterAxis` name the same things, and one word per
    # concept is the point of the table.
    "coverage_weight": "el peso de cobertura",
    "mapping_provenance": "la procedencia del mapeo",
    "neighbouring_mapping": "el mapeo a otra capacidad",
    "similarity": "la similitud de texto",
    "framework": "el marco",
    "strength": "la exigencia declarada",
    "control_text": "el texto del control",
    "candidate_status": "lo que el núcleo dijo del candidato",
    "zone_context": "la lectura de la zona",
    # --- the asset premises a gating rule reads (TechNature) ---
    #
    # Every one of these is read inside the sentence "la zona (no) tiene ...",
    # both by a gating rule's evidence and by a control's declared premise, so
    # they have to be nouns that survive it. Two did not until v0.5.0: `networked`
    # and `hybrid_it_ot` conditioned no hand-written rule at all, so "la zona
    # tiene conectado en red" never actually rendered. The premises use both.
    "general_purpose_os": "sistema operativo de propósito general",
    "networked": "conexión de red",
    "hybrid_it_ot": "mezcla de IT y OT",
    "interactive_users": "usuarios que inician sesión",
    "office_it_surface": "superficie ofimática",
}


def say(value: Enum | str) -> str:
    """The Spanish words for one enum value, or the value itself if unmapped.

    Falling back to the raw value rather than raising is deliberate: a new enum
    member must never be able to break a response — the worst it can do is read
    like an identifier for one release, which is visible and cheap to fix.
    """
    key = value.value if isinstance(value, Enum) else value
    return _WORDS.get(str(key), str(key))


def say_all(values: Iterable[Enum | str]) -> str:
    """The same, over an iterable, joined for a sentence."""
    return ", ".join(say(value) for value in values)


# `strength` is the one field whose words need composing rather than looking up:
# the scale, the level on it and a free note are three values that read as one
# phrase. It stays here, with the rest of the Spanish, so the schema that carries
# the structure holds no prose. Takes primitives, not the model, to keep this
# module importable from `catalog.schemas` without a cycle.
_STRENGTH_PHRASES: dict[str, str] = {
    "ig": "IG{level} — grupo de implantación CIS",
    "sl_baseline": "exigible desde SL{level}",
    "outcome": "resultado esperado, no mecanismo",
    "legal": "obligación legal",
    "guideline": "directriz, no obligación",
}


def strength_words(kind: str, level: int | None, note: str = "") -> str:
    """The Spanish phrase for one control's declared demand."""
    phrase = _STRENGTH_PHRASES.get(kind, kind).format(level=level)
    return f"{phrase} ({note})" if note else phrase
