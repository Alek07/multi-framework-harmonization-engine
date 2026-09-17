"""Splicing a premise into a source line without touching anything else.

The merge is textual because the catalog sources keep one control per line, which
keeps `git diff` readable when a handful of controls gain a premise. The risk is
that textual surgery corrupts a versioned input, so the rest of the line is
asserted to survive byte for byte.
"""

from __future__ import annotations

import json

import pytest

from app.catalog.schemas import Presupposition
from app.tagging.merge import (
    fragment,
    holds_key,
    is_one_line_entry,
    key_line,
    splice,
)

LINE = (
    '    { "id": "CTL-CIS-1001", "framework": "CIS", "official_id": "10.1", '
    '"title": "Deploy and Maintain Anti-Malware Software", '
    '"paraphrased_description": "Desplegar y mantener software antimalware.", '
    '"jurisdiction": "US", "strength": {"kind": "ig", "level": 1}, "type": "technical" },'
)

PREMISES = [
    Presupposition(
        premise="general_purpose_os",
        expected=True,
        note="Requiere un sistema operativo de propósito general.",
    )
]


def parsed(line: str) -> dict[str, object]:
    """The spliced line, read back as the JSON object the loader will see."""
    return dict(json.loads(line.strip().rstrip(",")))


def test_the_premise_lands_and_the_line_still_parses() -> None:
    spliced = splice(LINE, fragment(PREMISES))
    control = parsed(spliced)

    assert control["presupposes"] == [
        {
            "premise": "general_purpose_os",
            "expected": True,
            "note": "Requiere un sistema operativo de propósito general.",
        }
    ]


def test_every_other_field_survives_byte_for_byte() -> None:
    before, after = parsed(LINE), parsed(splice(LINE, fragment(PREMISES)))
    del after["presupposes"]

    assert after == before


def test_the_indentation_and_the_trailing_comma_are_kept() -> None:
    """A line that lost its comma would break the file for every control after it."""
    spliced = splice(LINE, fragment(PREMISES))

    assert spliced.startswith("    { ")
    assert spliced.endswith(" },")


def test_the_last_control_of_a_file_has_no_comma_to_keep() -> None:
    last = LINE.rstrip(",")
    spliced = splice(last, fragment(PREMISES))

    assert spliced.endswith(" }")
    assert parsed(spliced)["presupposes"]


def test_re_running_the_merge_replaces_rather_than_duplicates() -> None:
    """The reviewer changes their mind; the merge must not stack two keys."""
    once = splice(LINE, fragment(PREMISES))
    twice = splice(once, fragment(PREMISES))

    assert twice == once
    assert twice.count('"presupposes"') == 1


def test_a_premise_can_be_replaced_by_a_different_one() -> None:
    once = splice(LINE, fragment(PREMISES))
    other = [Presupposition(premise="interactive_users", expected=True, note="Hay personas.")]
    twice = splice(once, fragment(other))

    assert parsed(twice)["presupposes"] == [
        {"premise": "interactive_users", "expected": True, "note": "Hay personas."}
    ]


def test_the_spanish_note_is_not_escaped_into_unreadability() -> None:
    """The catalog is read by people: `ensure_ascii` would turn it into \u00f3 soup."""
    assert "propósito" in fragment(PREMISES)


def test_a_line_that_is_not_a_control_entry_is_refused_not_mangled() -> None:
    with pytest.raises(ValueError, match="one-line control entry"):
        splice('  "controls": [', fragment(PREMISES))


# --- the pretty-printed sources (NIS2) ---------------------------------------

PRETTY_ID = '      "id": "CTL-NIS2-A21J",'


def test_a_one_line_entry_is_recognised_as_one() -> None:
    assert is_one_line_entry(LINE)
    assert is_one_line_entry(LINE.rstrip(","))


def test_a_pretty_printed_id_line_is_not_a_one_line_entry() -> None:
    """The NIS2 source keeps one key per line; splicing it would have corrupted it."""
    assert not is_one_line_entry(PRETTY_ID)
    assert not is_one_line_entry('  "controls": [')


def test_the_inserted_key_keeps_the_indentation_of_the_id_above_it() -> None:
    inserted = key_line(PRETTY_ID, fragment(PREMISES))

    assert inserted.startswith('      "presupposes": ')
    assert inserted.endswith(",")
    # It has to parse as the object member it claims to be.
    assert json.loads("{" + inserted.rstrip(",") + "}")["presupposes"][0]["premise"] == (
        "general_purpose_os"
    )


def test_an_already_inserted_key_is_recognised_so_a_re_run_replaces_it() -> None:
    assert holds_key(key_line(PRETTY_ID, fragment(PREMISES)))
    assert not holds_key(PRETTY_ID)
    assert not holds_key('      "framework": "NIS2",')


def test_a_pretty_printed_control_survives_the_merge_as_valid_json() -> None:
    """The whole object, edited the way the script edits it, still parses."""
    entry = [
        "    {",
        PRETTY_ID,
        '      "framework": "NIS2",',
        '      "official_id": "Art. 21(2)(j)",',
        '      "type": "legal"',
        "    }",
    ]
    entry.insert(2, key_line(PRETTY_ID, fragment(PREMISES)))
    control = json.loads("\n".join(entry))

    assert control["id"] == "CTL-NIS2-A21J"
    assert control["framework"] == "NIS2"
    assert control["presupposes"][0]["premise"] == "general_purpose_os"
