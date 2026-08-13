"""UCM-46 - The declaration as a partial OSCAL system-security-plan (NIST).

The internal schema is already *conceptually* OSCAL — a versioned catalog, a
profile that tailors it for one asset, a plan that records what that asset
implements — so the crosswalk is the deliverable and this is its proof of work:
the same document `statement.py` projects, expressed in the OSCAL SSP model
(v1.1.3) for the subset of fields this engine actually has facts for.

**It is a partial export and it says so in its own metadata.** Nothing here is a
conformance claim: an SSP is a document about an authorised system, and this is a
composed baseline for an asset. What the export is good for is the thing the
ticket asks for — that a reviewer can take the artefact into an OSCAL toolchain
and read the composition without translating it by hand.

Four mapping decisions carry the weight, and each is written up in
`docs/oscal-crosswalk.md` with the alternative that was rejected:

* **`control-id` is the capability, not the framework control.** OSCAL resolves
  control ids against the imported profile; the profile of this engine is the
  asset's requirement set, whose members are the framework-neutral capabilities.
  Mapping the framework control there instead would have made every zone's
  mechanism a separate control and lost the requirement they answer to.
* **A zone is a component.** `type="network"` — an IEC 62443 zone is a grouping
  of assets under one security level, which is the closest core value. One
  `implemented-requirement` per capability then carries one `by-component` per
  zone it was composed in, which is exactly how the same requirement gets a
  different answer in the corridor and in the SIS.
* **`implementation-status` uses core values only.** `implemented`,
  `alternative` for a declared compensatory control, `not-applicable` for a
  justified gating exclusion, `partial` for residual coverage. The one case OSCAL
  has no state for — a gap the operator accepted *in writing*, which is neither
  planned nor not-applicable — is exported as `partial` and disambiguated by an
  extension property, and that gap in the model is reported as a finding rather
  than smoothed over.
* **Everything non-core goes in `props` under our own `ns`.** Tier, phase,
  jurisdiction, provenance, gating rule, audit sequence: OSCAL prescribes a
  namespace for exactly this, and inventing core names would make the document
  lie about what it conforms to.
"""

from __future__ import annotations

from typing import Any
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field

from app.baseline.schemas import (
    BaselineStatement,
    CapabilityOutcome,
    MechanismDisposition,
    StatementMechanism,
    StatementRow,
    StatementZone,
)
from app.core.wording import say

# The model version this export targets. Pinned, like everything else that
# governs an artefact of this engine: a document that did not say which version
# of the model it was written against could not be validated against any.
OSCAL_VERSION = "1.1.3"

# Namespace for the properties OSCAL does not define. A URN and not an http URI
# on purpose: this POC owns no domain, and claiming one in a document meant to be
# read by a third party would be the one lie in an artefact about traceability.
NS = "urn:tfm:mfhe:oscal"

# Deterministic identity. OSCAL wants a UUID on almost everything and this engine
# is reproducible by invariant, so they are derived from what they name rather
# than drawn at random: the same baseline exported twice is byte-identical.
_UUID_NS = uuid5(NAMESPACE_URL, "urn:tfm:mfhe:oscal")


def _hyphenate(name: str) -> str:
    return name.replace("_", "-")


class _Oscal(BaseModel):
    """Field names are hyphenated on the wire, which is how OSCAL spells them."""

    model_config = ConfigDict(
        alias_generator=_hyphenate, populate_by_name=True, extra="forbid"
    )


class Prop(_Oscal):
    name: str
    value: str
    ns: str | None = None
    remarks: str | None = None


class Link(_Oscal):
    href: str
    rel: str | None = None
    text: str | None = None


class Party(_Oscal):
    uuid: str
    type: str
    name: str | None = None
    remarks: str | None = None


class Role(_Oscal):
    id: str
    title: str
    description: str | None = None


class ResponsibleParty(_Oscal):
    role_id: str
    party_uuids: list[str]


class Revision(_Oscal):
    title: str | None = None
    version: str
    oscal_version: str | None = None
    remarks: str | None = None


class Metadata(_Oscal):
    title: str
    last_modified: str
    version: str
    oscal_version: str = OSCAL_VERSION
    props: list[Prop] = Field(default_factory=list)
    links: list[Link] = Field(default_factory=list)
    roles: list[Role] = Field(default_factory=list)
    parties: list[Party] = Field(default_factory=list)
    responsible_parties: list[ResponsibleParty] = Field(default_factory=list)
    remarks: str | None = None


class ImportProfile(_Oscal):
    href: str
    remarks: str | None = None


class SystemId(_Oscal):
    id: str
    identifier_type: str | None = None


class InformationType(_Oscal):
    uuid: str
    title: str
    description: str


class SystemInformation(_Oscal):
    information_types: list[InformationType]


class Status(_Oscal):
    state: str
    remarks: str | None = None


class AuthorizationBoundary(_Oscal):
    description: str


class SystemCharacteristics(_Oscal):
    system_ids: list[SystemId]
    system_name: str
    description: str
    props: list[Prop] = Field(default_factory=list)
    security_sensitivity_level: str | None = None
    system_information: SystemInformation
    status: Status
    authorization_boundary: AuthorizationBoundary
    remarks: str | None = None


class RoleAssignment(_Oscal):
    role_id: str
    party_uuids: list[str] = Field(default_factory=list)


class SystemUser(_Oscal):
    uuid: str
    title: str | None = None
    role_ids: list[str] = Field(default_factory=list)
    remarks: str | None = None


class Component(_Oscal):
    uuid: str
    type: str
    title: str
    description: str
    status: Status
    props: list[Prop] = Field(default_factory=list)
    remarks: str | None = None


class SystemImplementation(_Oscal):
    users: list[SystemUser]
    components: list[Component]
    remarks: str | None = None


class ImplementationStatus(_Oscal):
    state: str
    remarks: str | None = None


class ByComponent(_Oscal):
    component_uuid: str
    uuid: str
    description: str
    props: list[Prop] = Field(default_factory=list)
    links: list[Link] = Field(default_factory=list)
    implementation_status: ImplementationStatus | None = None
    remarks: str | None = None


class ImplementedRequirement(_Oscal):
    uuid: str
    control_id: str
    props: list[Prop] = Field(default_factory=list)
    links: list[Link] = Field(default_factory=list)
    by_components: list[ByComponent] = Field(default_factory=list)
    remarks: str | None = None


class ControlImplementation(_Oscal):
    description: str
    implemented_requirements: list[ImplementedRequirement]


class SystemSecurityPlan(_Oscal):
    uuid: str
    metadata: Metadata
    import_profile: ImportProfile
    system_characteristics: SystemCharacteristics
    system_implementation: SystemImplementation
    control_implementation: ControlImplementation


class OscalDocument(_Oscal):
    """The root wrapper OSCAL JSON documents carry."""

    system_security_plan: SystemSecurityPlan


# The four core states this export uses, and the one it uses under protest.
_STATE_BY_OUTCOME: dict[CapabilityOutcome, str] = {
    CapabilityOutcome.IMPLEMENTED: "implemented",
    # "There is an alternative implementation for this control": a compensatory
    # control is precisely that, and the reason is in the remarks.
    CapabilityOutcome.COMPENSATED: "alternative",
    # The requirement is not met at this layer and the plan says where it went.
    CapabilityOutcome.DEFERRED: "not-applicable",
    # OSCAL has no state for "assumed in writing". `partial` is the least wrong of
    # the five and the extension property below is what says what really happened.
    CapabilityOutcome.ACCEPTED_GAP: "partial",
    CapabilityOutcome.OPEN_GAP: "partial",
    CapabilityOutcome.ROADMAP: "planned",
}


def oscal_ssp(statement: BaselineStatement) -> OscalDocument:
    """The signed baseline as a partial OSCAL SSP, derived from the declaration.

    Takes the projected statement rather than the ledger, so the two artefacts
    cannot drift: whatever the SoA says, this says the same thing in NIST's
    vocabulary or it does not say it at all.
    """
    baseline_id = str(statement.baseline_id)
    signer = _uuid("party", baseline_id, statement.signed_by)

    return OscalDocument(
        system_security_plan=SystemSecurityPlan(
            uuid=baseline_id,
            metadata=_metadata(statement, signer),
            import_profile=ImportProfile(
                href=f"#{_uuid('profile', statement.profile_id)}",
                remarks=(
                    "El «perfil» de este motor es el conjunto de capacidades exigidas al activo, "
                    "derivado del catálogo versionado y del perfil del activo por zonas. No se "
                    "exporta aquí: este documento es la parte SSP del crosswalk."
                ),
            ),
            system_characteristics=_characteristics(statement),
            system_implementation=_implementation(statement, signer),
            control_implementation=_control_implementation(statement),
        )
    )


# --- metadata and the system ---------------------------------------------------


def _metadata(statement: BaselineStatement, signer: str) -> Metadata:
    versions = statement.versions
    return Metadata(
        title=f"Línea base compuesta y firmada — {statement.profile_name}",
        last_modified=statement.signed_at.isoformat(),
        # The document's version is the catalog's: the same composition over
        # another catalog is another baseline (invariant 3).
        version=versions.get("catalog", "0"),
        oscal_version=OSCAL_VERSION,
        props=[
            _prop("export-kind", "partial"),
            _prop("engine", "multi-framework-harmonization-engine"),
            *[_prop(f"version-{name}", value) for name, value in sorted(versions.items())],
            _prop("tier-0-complete", str(statement.tier_0_complete).lower()),
            _prop("ledger-chain-valid", str(statement.chain.valid).lower()),
            _prop("ledger-events", str(statement.chain.events)),
        ],
        links=[
            Link(
                href=statement.audit_log_path,
                rel="reference",
                text="Bitácora append-only de la que se proyecta este documento",
            )
        ],
        roles=[
            Role(
                id="signatory",
                title="Persona que compone y firma la línea base",
                description=(
                    "Actor humano de la composición soberana: el motor ofrece opciones "
                    "equivalentes y no elige ninguna."
                ),
            )
        ],
        parties=[Party(uuid=signer, type="person", name=statement.signed_by or "—")],
        responsible_parties=[
            ResponsibleParty(role_id="signatory", party_uuids=[signer])
        ],
        remarks=(
            "Export parcial al modelo SSP de OSCAL "
            f"{OSCAL_VERSION}. No es una declaración de conformidad con OSCAL ni con ninguna de "
            "las normas que el catálogo referencia: es la línea base compuesta en este motor, "
            "expresada en el modelo de NIST para el subconjunto de campos del que el motor tiene "
            f"hechos. Lo que no cabe en el modelo viaja en propiedades del espacio de nombres "
            f"{NS}. El documento se proyecta de la bitácora firmada y no recalcula nada."
        ),
    )


def _characteristics(statement: BaselineStatement) -> SystemCharacteristics:
    zones = ", ".join(zone.zone_id for zone in statement.zones)
    targets = [zone.target_sl for zone in statement.zones if zone.target_sl is not None]
    return SystemCharacteristics(
        system_ids=[SystemId(id=statement.profile_id, identifier_type=NS)],
        system_name=statement.profile_name,
        description=(
            f"Activo de infraestructura crítica compuesto en {len(statement.zones)} zona(s): "
            f"{zones}. La línea base se compone por zona: el mismo catálogo con distinto "
            "SL-objetivo y distintas premisas produce distinta línea base."
        ),
        props=[
            _prop("zones", str(len(statement.zones))),
            *[
                _prop("zone-target-sl", str(zone.target_sl), remarks=zone.zone_id)
                for zone in statement.zones
                if zone.target_sl is not None
            ],
        ],
        security_sensitivity_level=f"SL{max(targets)}" if targets else None,
        system_information=SystemInformation(
            information_types=[
                InformationType(
                    uuid=_uuid("information-type", statement.profile_id),
                    title="Datos de proceso y de control industrial",
                    description=(
                        "El motor no clasifica la información del activo: compone la línea base "
                        "a partir de las premisas técnicas declaradas y del SL-objetivo de cada "
                        "zona. Este tipo de información se declara para satisfacer el modelo, y "
                        "no lleva niveles de impacto porque el motor no los calcula."
                    ),
                )
            ]
        ),
        status=Status(
            state="other",
            remarks=(
                "Ni operativo ni en desarrollo: este documento describe una línea base compuesta "
                "y firmada, no un sistema autorizado. Se declara «other» para no afirmar un "
                "estado de autorización que nadie ha concedido."
            ),
        ),
        authorization_boundary=AuthorizationBoundary(
            description=(
                f"Las zonas declaradas en el perfil del activo: {zones}. La frontera es la del "
                "perfil compuesto, no la de una autorización formal."
            )
        ),
    )


def _implementation(statement: BaselineStatement, signer: str) -> SystemImplementation:
    return SystemImplementation(
        users=[
            SystemUser(
                uuid=_uuid("user", str(statement.baseline_id), statement.signed_by),
                title=statement.signed_by or "—",
                role_ids=["signatory"],
                remarks=(
                    "El único actor humano que el motor registra es quien compone y firma. El "
                    "motor no modela usuarios del activo."
                ),
            )
        ],
        components=[_component(statement, zone) for zone in statement.zones],
        remarks=(
            "Cada zona del activo se exporta como un componente de tipo «network»: una zona IEC "
            "62443 agrupa activos bajo un mismo nivel de seguridad, que es lo más cercano en los "
            "valores del modelo. Es una interpretación declarada, no un valor que OSCAL defina "
            "para zonas."
        ),
    )


def _component(statement: BaselineStatement, zone: StatementZone) -> Component:
    return Component(
        uuid=_uuid("component", str(statement.baseline_id), zone.zone_id),
        type="network",
        title=f"Zona {zone.zone_id}",
        description=zone.rationale,
        status=Status(state="operational" if zone.tier_0_complete else "other"),
        props=[
            _prop("zone-id", zone.zone_id),
            *([_prop("zone-domain", zone.domain)] if zone.domain else []),
            *(
                [_prop("zone-target-sl", str(zone.target_sl))]
                if zone.target_sl is not None
                else []
            ),
            *(
                [_prop("zone-safety-relevant", str(zone.safety_relevant).lower())]
                if zone.safety_relevant is not None
                else []
            ),
            *([_prop("zone-role", zone.role)] if zone.role else []),
            _prop("tier-0-complete", str(zone.tier_0_complete).lower()),
        ],
    )


# --- the control implementation ------------------------------------------------


def _control_implementation(statement: BaselineStatement) -> ControlImplementation:
    """One implemented-requirement per capability, one by-component per zone.

    Grouped this way because it is what the engine actually produces: the same
    requirement is answered differently in different zones, and OSCAL's own way
    of saying that is a component-scoped implementation of one control.
    """
    grouped: dict[str, list[tuple[StatementZone, StatementRow]]] = {}
    for zone in statement.zones:
        for row in zone.rows:
            grouped.setdefault(row.capability_id, []).append((zone, row))

    return ControlImplementation(
        description=(
            f"{len(grouped)} capacidad(es) exigida(s) del catálogo, cada una con la respuesta que "
            "recibió en cada zona. Ninguna desaparece: el gating de este motor excluye mecanismos "
            "y nunca capacidades exigidas, así que una capacidad sin mecanismo aplicable aparece "
            "igualmente, con su hueco declarado y la justificación escrita de quien firmó."
        ),
        implemented_requirements=[
            _requirement(statement, capability_id, entries)
            for capability_id, entries in grouped.items()
        ],
    )


def _requirement(
    statement: BaselineStatement,
    capability_id: str,
    entries: list[tuple[StatementZone, StatementRow]],
) -> ImplementedRequirement:
    first = entries[0][1]
    return ImplementedRequirement(
        uuid=_uuid("requirement", str(statement.baseline_id), capability_id),
        control_id=capability_id,
        props=[
            _prop("capability-name", first.capability_name),
            _prop("required", "true", remarks="Una capacidad exigida no se deroga al componer."),
            *[
                _prop("mandate", mandate.source, remarks=mandate.rationale or None)
                for mandate in first.mandates
            ],
        ],
        links=[Link(href=statement.audit_log_path, rel="reference")],
        by_components=[_by_component(statement, zone, row) for zone, row in entries],
        remarks=first.engine_rationale or None,
    )


def _by_component(
    statement: BaselineStatement, zone: StatementZone, row: StatementRow
) -> ByComponent:
    included = [m for m in row.mechanisms if m.included]
    excluded = [
        m
        for m in row.mechanisms
        if m.disposition
        in {
            MechanismDisposition.NOT_APPLICABLE,
            MechanismDisposition.OBJECTIVE_WITHOUT_MECHANISM,
            MechanismDisposition.WRONG_SCOPE,
        }
    ]

    return ByComponent(
        component_uuid=_uuid("component", str(statement.baseline_id), zone.zone_id),
        uuid=_uuid("by-component", str(statement.baseline_id), zone.zone_id, row.capability_id),
        description=_description(row, included),
        props=[
            _prop("capability-outcome", row.outcome.value),
            _prop("tier", row.tier.value),
            _prop("in-signed-baseline", str(row.in_signed_baseline).lower()),
            *([_prop("phase", str(row.phase))] if row.phase is not None else []),
            *([_prop("priority", row.priority)] if row.priority else []),
            *([_prop("layer", row.layer)] if row.layer else []),
            *([_prop("gating-status", row.status.value)] if row.status else []),
            *[_prop("selected-control", _label(m), remarks=m.rationale or None) for m in included],
            *[
                _prop("jurisdiction", m.jurisdiction, remarks=_label(m))
                for m in included
                if m.jurisdiction
            ],
            *[
                _prop(
                    "excluded-control",
                    _label(m),
                    remarks=f"{say(m.disposition)} — {m.rule_id or 'sin regla'}: {m.rationale}",
                )
                for m in excluded
            ],
            *(
                [
                    _prop("gap-kind", row.gap.kind),
                    _prop("gap-residual", f"{row.gap.residual}"),
                ]
                if row.gap is not None
                else []
            ),
            *([_prop("gap-accepted", "true")] if row.gap_accepted else []),
            _prop("audit-sequences", ",".join(str(s) for s in row.audit_sequences)),
        ],
        links=[Link(href=statement.audit_log_path, rel="reference")],
        implementation_status=ImplementationStatus(
            state=_STATE_BY_OUTCOME[row.outcome],
            remarks=_status_remarks(row),
        ),
        remarks=row.human_rationale or row.engine_rationale or None,
    )


def _description(row: StatementRow, included: list[StatementMechanism]) -> str:
    if included:
        mechanisms = ", ".join(_label(m) for m in included)
        how = (
            "por decisión escrita del operador"
            if row.decided_by_human
            else "por ratificación al firmar, sin elección entre equivalentes"
        )
        return f"«{row.capability_name}»: {mechanisms}. {say(row.outcome)} {how}."
    return f"«{row.capability_name}»: {say(row.outcome)} — sin mecanismo en la capa del activo."


def _status_remarks(row: StatementRow) -> str:
    written = row.human_rationale or row.engine_rationale
    if row.outcome is CapabilityOutcome.ACCEPTED_GAP:
        return (
            "OSCAL no define un estado para «hueco asumido por escrito»: no es «planned» porque "
            "no hay plan, ni «not-applicable» porque la capacidad sigue exigida. Se exporta como "
            f"«partial» y la propiedad {NS} capability-outcome=accepted_gap es la que dice qué "
            f"ocurrió realmente. Justificación registrada: {written}"
        )
    if row.outcome is CapabilityOutcome.DEFERRED:
        return (
            "No aplica *en esta capa*: el requisito se traslada a la capa organizativa y sigue "
            f"exigido allí. {written}"
        )
    if row.outcome is CapabilityOutcome.ROADMAP:
        return (
            "Capacidad discrecional que el operador no decidió: está en la hoja de ruta por fases "
            f"y queda fuera de lo firmado. {written}"
        )
    return written


# --- small helpers -------------------------------------------------------------


def _prop(name: str, value: str, remarks: str | None = None) -> Prop:
    return Prop(name=name, value=value, ns=NS, remarks=remarks)


def _label(mechanism: StatementMechanism) -> str:
    if mechanism.framework and mechanism.official_id:
        return f"{mechanism.framework} {mechanism.official_id}"
    return mechanism.official_id or mechanism.control_id


def _uuid(kind: str, *parts: str) -> str:
    return str(uuid5(_UUID_NS, "/".join((kind, *parts))))


def as_json(document: OscalDocument) -> dict[str, Any]:
    """OSCAL spelling, and no nulls: an absent field is absent, not present-and-null."""
    return document.model_dump(mode="json", by_alias=True, exclude_none=True)
