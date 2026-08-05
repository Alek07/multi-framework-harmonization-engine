"""UCM-43 - A catalog split across one file per framework is the same catalog.

The split exists so a framework can be authored, reviewed — or handed to the
CISO — on its own, without opening the other four. That is an authoring
convenience and it has to stay exactly that: what the engine loads, validates
and fingerprints must not be able to tell how many files it came from.

So the guarantees asserted here are about *sameness*, plus the two ways a
manifest can lie about its parts:

* a split of a catalog loads to the same model as the catalog in one file;
* the model does not depend on the order the sources are listed in — that order
  reaches the Qdrant collection name through the parsed model
  (`app/retrieval/index.py`), and a collection name that changed because someone
  reordered a list would be a false alarm about stale vectors;
* **a single file is still read verbatim**, in its authored order. Every catalog
  already shipped keeps parsing and hashing as it did before the split existed,
  which is what lets a baseline signed against v0.1.0 stay reproducible;
* a source that does not exist, or that contributes no control because its key
  was mistyped, is an error — never a catalog that quietly holds less.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.catalog.loader import BACKEND_ROOT, load_catalog

# Pinned on purpose to the last single-file catalog rather than to whatever
# CATALOG_PATH points at today: these tests are about the two *shapes* being the
# same catalog, so they need one of each, and v0.1.0 is frozen for good.
SINGLE_FILE = BACKEND_ROOT / "data/catalog/catalog.v0.1.0.json"


def read_shipped() -> dict[str, Any]:
    return dict(json.loads(SINGLE_FILE.read_text(encoding="utf-8")))


def split(tmp_path: Path, data: dict[str, Any], sources: list[str] | None = None) -> Path:
    """Write `data` as a manifest plus one source file per framework."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    by_framework: dict[str, dict[str, list[Any]]] = {}
    for control in data["controls"]:
        part = by_framework.setdefault(control["framework"], {"controls": [], "mappings": []})
        part["controls"].append(control)
    for mapping in data["mappings"]:
        framework = next(
            c["framework"] for c in data["controls"] if c["id"] == mapping["control_id"]
        )
        by_framework[framework]["mappings"].append(mapping)

    for framework, part in by_framework.items():
        name = f"{framework.lower()}.json"
        (tmp_path / name).write_text(json.dumps(part, ensure_ascii=False), encoding="utf-8")

    declared = sources if sources is not None else sorted(f"{f.lower()}.json" for f in by_framework)
    manifest = {
        **{k: v for k, v in data.items() if k not in ("controls", "mappings")},
        "sources": declared,
    }
    path = tmp_path / "catalog.split.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return path


def test_the_shipped_catalog_is_a_split_one_and_loads(tmp_path: Path) -> None:
    """The default catalog goes through the merge path, and its invariants hold."""
    catalog = load_catalog()

    assert catalog.orphan_capabilities() == set()
    assert catalog.unused_controls() == set()
    assert {c.framework.value for c in catalog.controls} == {
        "CSF",
        "IEC62443",
        "CIS",
        "NIS2",
        "IMO",
    }


def test_a_split_catalog_is_the_catalog(tmp_path: Path) -> None:
    shipped = load_catalog(SINGLE_FILE)
    merged = load_catalog(split(tmp_path, read_shipped()))

    assert merged.catalog_version == shipped.catalog_version
    assert merged.capabilities == shipped.capabilities
    assert sorted(merged.controls, key=lambda c: c.id) == sorted(
        shipped.controls, key=lambda c: c.id
    )
    assert sorted(merged.mappings, key=lambda m: (m.capability_id, m.control_id)) == sorted(
        shipped.mappings, key=lambda m: (m.capability_id, m.control_id)
    )
    # And the invariants of the whole are checked over the whole, not per file.
    assert merged.orphan_capabilities() == set()
    assert merged.unused_controls() == set()


def test_the_model_does_not_depend_on_the_order_of_the_sources(tmp_path: Path) -> None:
    data = read_shipped()
    frameworks = sorted({c["framework"].lower() for c in data["controls"]})

    ordered = load_catalog(split(tmp_path / "a", data, [f"{f}.json" for f in frameworks]))
    reversed_ = load_catalog(
        split(tmp_path / "b", data, [f"{f}.json" for f in reversed(frameworks)])
    )

    assert ordered.model_dump_json() == reversed_.model_dump_json()


def test_a_single_file_catalog_keeps_its_authored_order(tmp_path: Path) -> None:
    """No sorting on the single-file path: a shipped catalog parses as it always did."""
    data = read_shipped()
    loaded = load_catalog(SINGLE_FILE)

    assert [c.id for c in loaded.controls] == [c["id"] for c in data["controls"]]
    assert [m.control_id for m in loaded.mappings] == [m["control_id"] for m in data["mappings"]]


def test_a_source_that_does_not_exist_is_an_error(tmp_path: Path) -> None:
    manifest = split(tmp_path, read_shipped())
    manifest.write_text(
        json.dumps({**json.loads(manifest.read_text(encoding="utf-8")), "sources": ["nope.json"]}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="source that does not exist"):
        load_catalog(manifest)


def test_a_source_whose_key_is_mistyped_is_an_error(tmp_path: Path) -> None:
    """The failure mode the guard exists for: a typo would remove controls in silence."""
    manifest = split(tmp_path, read_shipped())
    source = tmp_path / "cis.json"
    mistyped = {"control": json.loads(source.read_text(encoding="utf-8"))["controls"]}
    source.write_text(json.dumps(mistyped), encoding="utf-8")

    with pytest.raises(ValueError, match="contributes no control"):
        load_catalog(manifest)


def test_a_catalog_without_content_is_an_error(tmp_path: Path) -> None:
    data = read_shipped()
    empty = (("capabilities", "without capabilities"), ("controls", "without controls"))
    for part, message in empty:
        path = tmp_path / f"empty-{part}.json"
        path.write_text(json.dumps({**data, part: []}, ensure_ascii=False), encoding="utf-8")
        with pytest.raises(ValueError, match=message):
            load_catalog(path)
