"""UCM-53/UCM-19 - The whole flow through the API, on several assets, against a deployment.

Not a unit of it: the seven declared endpoints in the order an operator walks
them -- free text in, signed baseline and declaration of applicability out -- and
then the same walk again for assets that differ on the premises the engine reads.

What it is for. Every other test in this repo checks one layer with the ones
around it replaced: scripted model, fake index, in-process client. That is what
makes them fast and what lets them run on a laptop with nothing installed, and it
is also what they cannot prove -- that the seams hold, and that a decision taken
in the catalog survives the whole chain.

The claim under test is UCM-53's: a premise the catalog declares about a control
becomes a justified exclusion in the zone that does not meet it, and that
exclusion is still legible, with its rule and its evidence, in the signed
document at the far end. If it were lost anywhere between the gating and the
declaration, everything else could still be green.

The three assets bracket the premise space rather than trying to be realistic in
every detail: one that can host almost nothing, one that can host almost
everything, and one that is two zones at once and carries a maritime obligation.
They are given as *prose*, because the flow starts at the parse and an asset
handed over as a ready-made profile would skip the half of the argument that is
hardest.

Two things it deliberately reports instead of asserting. Which premises the parse
captures is measured and printed, never required -- a miss there is the argument
for human-in-the-loop, not a defect. And the operator's review is simulated in
one marked place, so it is always visible which values came from the model and
which from the person.

Run from the repo root, with the stack up:

    docker compose exec backend python scripts/e2e_flow.py
    docker compose exec backend python scripts/e2e_flow.py --asset ESC-AIRGAP
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class Asset:
    """An asset as the operator would hand it over: prose, plus what they answer.

    `review` is not a second parse. It is the table the person fills when the
    model leaves a required field empty, and it is printed field by field so the
    seam between the two is never invisible.
    """

    id: str
    label: str
    description: str
    review: dict[str, Any]
    summary: dict[str, Any] = field(default_factory=dict)


NATURE_ALL_FALSE = {
    "general_purpose_os": False,
    "networked": False,
    "hybrid_it_ot": False,
    "interactive_users": False,
    "office_it_surface": False,
}
NATURE_ALL_TRUE = dict.fromkeys(NATURE_ALL_FALSE, True)


ASSETS: list[Asset] = [
    Asset(
        id="ESC-AIRGAP",
        label="Sistema instrumentado de seguridad, aislado",
        description=(
            "El sistema instrumentado de seguridad de la estacion de bombeo PK-42 es un "
            "controlador embebido dedicado, sin conexion a ninguna red: opera aislado, con "
            "enclavamientos cableados. No ejecuta ningun sistema operativo de proposito general, "
            "no tiene pantalla ni teclado, nadie inicia sesion en el, y no se manejan alli ni "
            "correo ni documentos ofimaticos. Es la joya de la corona del activo y su funcion de "
            "seguridad es lo ultimo que puede fallar; el objetivo de nivel de seguridad es 4. El "
            "operador es una empresa de transporte de gas del sector energia. Un fallo de la "
            "funcion de seguridad provocaria una sobrepresion con rotura y fuga, de consecuencia "
            "catastrofica. El modelo de amenaza de referencia es ATT&CK for ICS y el incidente de "
            "referencia es TRITON/TRISIS."
        ),
        review={
            "name": "SIS de la estacion de bombeo PK-42",
            "case": "PURE_OT",
            "sectors": ["energy"],
            "target_sl": 4,
            "nature": NATURE_ALL_FALSE,
            "criticality": {
                "physical_consequence": "loss_of_safety_function",
                "scale": "catastrophic",
                "threat_model": "ATTACK_for_ICS",
            },
            "conduit_control": "hardwired_interlock",
        },
    ),
    Asset(
        id="ESC-PORT",
        label="Terminal portuaria de combustible, dos zonas",
        description=(
            "La terminal portuaria de combustible atiende el atraque de buques y tiene dos zonas. "
            "En el pantalan, el control de los brazos de carga corre sobre equipos embebidos sin "
            "sistema operativo de proposito general, conectados a la red de control, y operados de "
            "forma interactiva por el personal de muelle; alli no se manejan correo ni documentos "
            "ofimaticos, y el objetivo de nivel de seguridad es 3. En la sala de operacion "
            "portuaria hay estaciones Windows conectadas a la vez a la red corporativa y a la red "
            "de control, con correo, navegacion web y documentos, y personal que inicia sesion; su "
            "objetivo de nivel de seguridad es 2. La terminal opera en los sectores maritimo, de "
            "transporte y de energia. Un incidente provocaria un derrame de combustible con "
            "incendio en el atraque, de consecuencia catastrofica, y el incidente de referencia es "
            "NotPetya/Maersk."
        ),
        review={
            "name": "Terminal portuaria de combustible",
            "case": "HYBRID_IT_OT",
            "sectors": ["maritime", "transport", "energy"],
            "target_sl": 3,
            "nature": NATURE_ALL_TRUE,
            "criticality": {
                "physical_consequence": "fuel_spill_and_fire_at_berth",
                "scale": "catastrophic",
                "threat_model": "ATTACK_for_ICS",
            },
            "conduit_control": "mediated_ship_shore_interface",
        },
    ),
    Asset(
        id="ESC-OFFICE",
        label="Centro de control corporativo",
        description=(
            "El centro de control corporativo del operador de gasoducto esta en el nivel 5 de "
            "Purdue. Son servidores y puestos Windows conectados a la red corporativa, que ademas "
            "alcanza la red de control a traves de una DMZ industrial. El personal inicia sesion "
            "de forma interactiva y se manejan correo, navegacion web y documentos ofimaticos. El "
            "objetivo de nivel de seguridad es 2. El operador es una empresa de transporte de gas "
            "del sector energia. Un incidente causaria la perdida de visibilidad supervisora sobre "
            "la red de transporte, de consecuencia alta."
        ),
        review={
            "name": "Centro de control corporativo",
            "case": "HYBRID_IT_OT",
            "sectors": ["energy"],
            "target_sl": 2,
            "nature": NATURE_ALL_TRUE,
            "criticality": {
                "physical_consequence": "loss_of_supervisory_visibility",
                "scale": "high",
                "threat_model": "ATTACK_enterprise",
            },
            "conduit_control": "it_hygiene_and_identity",
        },
    ),
]

SIGNATURE = {
    "operator": "Responsable de ciberseguridad OT",
    "rationale": (
        "Bloque obligatorio revisado zona a zona; los mandatos que el motor no pudo cerrar se "
        "asumen por escrito tras valorar el riesgo residual."
    ),
}

PREMISE_RULE = "GATE-PREMISE-UNMET"


class Report:
    """Every check is recorded and printed; the run does not stop at the first one."""

    def __init__(self) -> None:
        self.failed = 0
        self.passed = 0

    def check(self, ok: bool, label: str, detail: str = "") -> bool:
        if ok:
            self.passed += 1
        else:
            self.failed += 1
        mark = "OK  " if ok else "FALLA"
        print(f"     [{mark}] {label}{f' - {detail}' if detail else ''}")
        return ok

    def note(self, label: str, value: Any) -> None:
        print(f"     .     {label}: {value}")

    def step(self, number: str, title: str) -> None:
        print()
        print(f"  == {number}  {title}")


def complete(asset: Asset, draft: dict[str, Any], missing: list[str], r: Report) -> dict[str, Any]:
    """The operator's review, simulated -- and printed, so the seam stays visible.

    Every zone the model found is kept. Dropping one would be the silent omission
    this engine exists to prevent, committed by its own test.
    """
    review = asset.review
    profile: dict[str, Any] = {
        "id": asset.id,
        "name": draft.get("name") or review["name"],
        "case": draft.get("case") or review["case"],
        "sectors": draft.get("sectors") or review["sectors"],
        "zones": [],
        "conduits": [],
        "criticality": {},
    }

    supplied: list[str] = []
    read: list[str] = []
    for index, raw in enumerate(draft.get("zones") or [{}]):
        zone = dict(raw)
        merged: dict[str, Any] = {
            "id": zone.get("id") or f"{asset.id}-Z{index}",
            "target_sl": zone.get("target_sl") or review["target_sl"],
            "nature": {},
            "safety_out_of_scope": bool(zone.get("safety_out_of_scope")),
        }
        # `sectors` above all: a zone's own sectors *override* the asset's, so
        # dropping them here would have silently handed every zone the asset-wide
        # reading -- and with it the sectoral exclusion that tells a jetty from an
        # operations room inside the same terminal.
        for optional in ("purdue", "role", "position", "reference", "sectors"):
            if zone.get(optional):
                merged[optional] = zone[optional]
        model_nature = zone.get("nature") or {}
        for flag, declared in review["nature"].items():
            value = model_nature.get(flag)
            if value is None:
                value, target = declared, supplied
            else:
                target = read
            target.append(f"{merged['id']}.{flag}")
            merged["nature"][flag] = bool(value)
        profile["zones"].append(merged)

    criticality = draft.get("criticality") or {}
    for field_name, declared in review["criticality"].items():
        profile["criticality"][field_name] = criticality.get(field_name) or declared
    for optional in ("consequence_path", "attack_reference"):
        if criticality.get(optional):
            profile["criticality"][optional] = criticality[optional]

    for index, conduit in enumerate(draft.get("conduits") or []):
        endpoints = conduit.get("endpoints") or []
        if len(endpoints) < 2:
            continue
        profile["conduits"].append(
            {
                "id": conduit.get("id") or f"C-{index}",
                "endpoints": endpoints,
                "control": conduit.get("control") or review["conduit_control"],
            }
        )

    r.note("zonas que el modelo encontro", [z["id"] for z in profile["zones"]])
    r.note("campos que el modelo dejo vacios", len(missing))
    r.note("premisas leidas por el modelo", f"{len(read)} de {len(read) + len(supplied)}")
    if supplied:
        r.note("premisas que declaro la persona", supplied)
    asset.summary["zones"] = [z["id"] for z in profile["zones"]]
    asset.summary["premises_read"] = len(read)
    asset.summary["premises_supplied"] = len(supplied)
    return profile


def parse_asset(client: httpx.Client, asset: Asset, r: Report) -> dict[str, Any]:
    r.step("1/7", "POST /asset/parse  -- texto libre a borrador revisable")
    body = client.post("/asset/parse", json={"description": asset.description}, timeout=900.0)
    r.check(body.status_code == 200, "el parseo responde", f"HTTP {body.status_code}")
    result = body.json()

    prov = result["provenance"]
    r.check(result["review_required"] is True, "el borrador exige revision humana")
    r.check(prov["temperature"] == 0.0 and prov["seed"] is not None, "temp 0 y semilla fijada")
    r.check(bool(prov["model_digest"]), "digest del modelo verificado")
    r.note("intentos del modelo", prov["attempts"])
    return result


def candidates(client: httpx.Client, asset: Asset, profile: dict, r: Report) -> dict[str, Any]:
    r.step("2/7", "POST /candidates  -- perfil a opciones equivalentes por capacidad")
    body = client.post("/candidates", json={"profile": profile}, timeout=1800.0)
    r.check(body.status_code == 200, "el motor responde", f"HTTP {body.status_code}")
    run = body.json()

    caps = [c for zone in run["zones"] for c in zone["capabilities"]]
    per_zone = {z["zone"]["zone_id"]: len(z["capabilities"]) for z in run["zones"]}
    r.check(set(per_zone.values()) == {37}, "37 capacidades en cada zona", str(per_zone))
    r.check(
        run["retrieval"]["status"] == "ok",
        "el recuperador contesto",
        run["retrieval"]["status"],
    )

    silent = [
        c["capability_id"]
        for c in caps
        if not c["offered_control_ids"]
        and not (
            c["resolution"]["gap"] or c["gating"]["gap"] or (c.get("retrieval") or {}).get("gap")
        )
    ]
    r.check(not silent, "0 omisiones silenciosas (invariante 2)", str(silent))

    excluded = [d for c in caps for d in c["gating"]["excluded"]]
    by_premise = [d for d in excluded if d["rule_id"] == PREMISE_RULE]
    r.check(
        all(d["rationale"].strip() and d["evidence"] for d in excluded),
        "toda exclusion lleva motivo y evidencia",
    )
    r.check(
        all(c["gating"]["required"] is True for c in caps),
        "ninguna capacidad deja de ser requerida",
    )

    surviving = {
        zone["zone"]["zone_id"]: len(
            {o["control"]["id"] for c in zone["capabilities"] for o in c["resolution"]["options"]}
            - {d["control_id"] for c in zone["capabilities"] for d in c["gating"]["excluded"]}
        )
        for zone in run["zones"]
    }
    r.note("controles del catalogo que sobreviven, por zona", surviving)
    r.note("exclusiones", f"{len(excluded)} - por premisa {len(by_premise)}")

    asset.summary.update(
        surviving=surviving,
        excluded=len(excluded),
        by_premise=len(by_premise),
        suggestions=run["retrieval"]["suggestions"],
        outstanding=sum(len(z["outstanding_capability_ids"]) for z in run["zones"]),
    )
    return run


def delta(client: httpx.Client, asset: Asset, profile: dict, zone_id: str, r: Report) -> None:
    r.step("3/7", "POST /delta  -- que anade responder tambien ante la UE")
    body = client.post(
        "/delta",
        json={"regions": ["US", "EU"], "profile": profile, "zone_id": zone_id},
        timeout=600.0,
    )
    r.check(body.status_code == 200, "el delta responde", f"HTTP {body.status_code}")
    result = body.json()
    r.check(result["zone"]["zone_id"] == zone_id, "es la zona pedida")
    r.check(len(result["capabilities"]) == 37, "cubre las 37 capacidades")
    added = sum(len(c["added"]) for c in result["capabilities"])
    r.note("capacidades que cambian al anadir EU", len(result["changed_capability_ids"]))
    asset.summary.update(delta_changed=len(result["changed_capability_ids"]), delta_added=added)


def compose(client: httpx.Client, asset: Asset, run: dict, profile: dict, r: Report) -> dict:
    r.step("4/7", "POST /baseline/compose  -- las decisiones del humano, firmadas")
    choices = [
        {
            "kind": "gap_accepted",
            "zone_id": zone["zone"]["zone_id"],
            "capability_id": capability_id,
            "rationale": (
                "Riesgo residual asumido por escrito: el activo no admite el mecanismo y la "
                f"compensacion pasa a la capa organizativa ({capability_id})."
            ),
        }
        for zone in run["zones"]
        for capability_id in zone["outstanding_capability_ids"]
    ]
    r.note("mandatos que el motor no pudo cerrar", len(choices))

    body = client.post(
        "/baseline/compose",
        json={
            "run_id": run["run_id"],
            "profile": profile,
            "choices": choices,
            "signature": SIGNATURE,
        },
        timeout=600.0,
    )
    r.check(body.status_code == 201, "la baseline se firma", f"HTTP {body.status_code}")
    baseline = body.json()
    r.check(baseline["tier_0_complete"] is True, "el bloque obligatorio esta completo")
    r.check(baseline["run_id"] == run["run_id"], "la firma apunta a esta corrida")
    asset.summary["baseline"] = baseline["baseline_id"]
    return baseline


def trail(client: httpx.Client, asset: Asset, baseline: dict, r: Report) -> None:
    r.step("5/7", "GET /baseline/{id}/audit-log  -- la traza completa y su cadena")
    body = client.get(f"/baseline/{baseline['baseline_id']}/audit-log", timeout=300.0)
    r.check(body.status_code == 200, "la bitacora responde", f"HTTP {body.status_code}")
    log = body.json()

    r.check(log["chain"]["valid"] is True, "la cadena de hashes verifica")
    r.check(
        log["engine_events"] > 0 and log["human_events"] > 0,
        "hay asientos de motor y de humano",
    )
    r.check(
        all(e["decision"].strip() and e["rationale"].strip() for e in log["events"]),
        "todo asiento dice que se decidio y por que",
    )
    actors = sorted({e["actor"] for e in log["events"]})
    r.check(set(actors) <= {"engine", "human"}, "solo motor y humano son actores", str(actors))
    r.note("asientos", f"{log['engine_events']} motor + {log['human_events']} humano")
    asset.summary.update(
        events=len(log["events"]),
        human_events=log["human_events"],
        chain_valid=log["chain"]["valid"],
    )


def listing(client: httpx.Client, baseline: dict, r: Report) -> None:
    r.step("6/7", "GET /baselines  -- lo firmado en este registro")
    body = client.get("/baselines", timeout=300.0)
    r.check(body.status_code == 200, "el listado responde", f"HTTP {body.status_code}")
    ids = [b["baseline_id"] for b in body.json()["baselines"]]
    r.check(baseline["baseline_id"] in ids, "la baseline recien firmada aparece")


def statement(client: httpx.Client, asset: Asset, baseline: dict, r: Report) -> None:
    r.step("7/7", "GET /baseline/{id}/statement  -- la declaracion de aplicabilidad")
    path = f"/baseline/{baseline['baseline_id']}/statement"
    body = client.get(path, timeout=300.0)
    r.check(body.status_code == 200, "la declaracion responde", f"HTTP {body.status_code}")
    soa = body.json()

    rows = [row for zone in soa["zones"] for row in zone["rows"]]
    per_zone = {zone["zone_id"]: len(zone["rows"]) for zone in soa["zones"]}
    r.check(set(per_zone.values()) == {37}, "una fila por capacidad en cada zona", str(per_zone))
    r.check(all(row["required"] is True for row in rows), "ninguna capacidad deja de ser exigida")
    r.check(soa["chain"]["valid"] is True, "el documento verifica su propia cadena")
    r.check(bool(soa["limitations"]), "el documento declara lo que no es")

    # The claim of UCM-53, at the far end of the chain.
    mechs = [m for row in rows for m in row["mechanisms"]]
    by_premise = [m for m in mechs if m["rule_id"] == PREMISE_RULE]
    expected = asset.summary.get("by_premise", 0)
    if expected:
        r.check(
            bool(by_premise),
            "las exclusiones por premisa llegan a la declaracion firmada",
            f"{len(by_premise)} mecanismo(s)",
        )
        r.check(
            all(m["disposition"] == "not_applicable" and m["evidence"] for m in by_premise),
            "cada una llega como exclusion justificada, con su evidencia",
        )
        sample = by_premise[0]
        r.note("ejemplo", f"{sample['control_id']} ({sample['official_id']})")
        r.note("evidencia", sample["evidence"][0] if sample["evidence"] else "-")
    else:
        r.note("exclusiones por premisa", "ninguna en este activo, y eso es la respuesta")

    # Counted over what the gating did *not* exclude, not over what the signature
    # took: a contextual obligation -- which is most of what the IMO contributes --
    # is an exigency rather than a mechanism, so it is offered and never "included".
    # Counting only the included ones reported zero IMO for a maritime terminal.
    gated_out = {"not_applicable", "objective_without_mechanism", "wrong_scope"}
    surviving = [m for m in mechs if m["disposition"] not in gated_out and m["framework"]]
    frameworks = sorted({m["framework"] for m in surviving})
    r.note("marcos que sobreviven al gating", frameworks)

    oscal = client.get(path, params={"format": "oscal"}, timeout=300.0)
    r.check(oscal.status_code == 200, "la variante OSCAL responde", f"HTTP {oscal.status_code}")
    r.check("system-security-plan" in oscal.text, "es un system-security-plan")
    asset.summary.update(
        statement_rows=len(rows),
        premise_in_statement=len(by_premise),
        frameworks=frameworks,
    )


def walk(client: httpx.Client, asset: Asset, r: Report) -> None:
    """One asset, all seven endpoints, in the order the operator walks them."""
    print()
    print(f"=== {asset.id}  {asset.label}")
    parsed = parse_asset(client, asset, r)
    profile = complete(asset, parsed["draft"], parsed["missing_required"], r)
    run = candidates(client, asset, profile, r)
    delta(client, asset, profile, run["zones"][0]["zone"]["zone_id"], r)
    baseline = compose(client, asset, run, profile, r)
    trail(client, asset, baseline, r)
    listing(client, baseline, r)
    statement(client, asset, baseline, r)


def compare(assets: list[Asset]) -> None:
    print()
    print("=== Mismo catalogo, mismas reglas, tres activos")
    header = (
        f"{'activo':12} {'zonas':>6} {'premisas':>9} {'sobreviven':>22} "
        f"{'excl':>5} {'prem':>5} {'abiertos':>9} {'IMO':>4}"
    )
    print(header)
    print("-" * len(header))
    for a in assets:
        s = a.summary
        if not s.get("surviving"):
            continue
        surviving = "/".join(str(v) for v in s["surviving"].values())
        premises = f"{s['premises_read']}/{s['premises_read'] + s['premises_supplied']}"
        imo = "si" if "IMO" in s.get("frameworks", []) else "-"
        print(
            f"{a.id:12} {len(s['zones']):6} {premises:>9} {surviving:>22} "
            f"{s['excluded']:5} {s['by_premise']:5} {s['outstanding']:9} {imo:>4}"
        )
    print()
    print("   premisas = leidas por el modelo / totales; el resto las declaro la persona")
    print("   sobreviven = controles del catalogo que el gating no excluyo, por zona")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000/api/v1")
    parser.add_argument("--asset", help="run only this one (ESC-AIRGAP, ESC-PORT, ESC-OFFICE)")
    parser.add_argument("--out", help="write the per-asset summary as JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    chosen = [a for a in ASSETS if not args.asset or a.id == args.asset]
    if not chosen:
        print(f"   no hay ningun activo llamado {args.asset}")
        return 2

    r = Report()
    print(f"   flujo completo contra {args.base_url} - {len(chosen)} activo(s)")
    with httpx.Client(base_url=args.base_url) as client:
        for asset in chosen:
            walk(client, asset, r)

    compare(chosen)
    print()
    print(f"=== {r.passed} comprobaciones pasan, {r.failed} fallan")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(
                {a.id: {"label": a.label, **a.summary} for a in chosen},
                handle,
                ensure_ascii=False,
                indent=2,
            )
    return 1 if r.failed else 0


if __name__ == "__main__":
    sys.exit(main())
