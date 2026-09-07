"""HZZO drug-list parser: header-based column mapping.

HZZO does not keep column positions stable between list publications. The
July 2026 files inserted "DDD i mjerna jed. za DDD" at index 3 in DLL-1. dio,
which shifted Doplata/R-RS by one under the old index-based parser — it read
packaging text as the co-pay (116 chars into varchar(20) → StringDataRightTruncationError,
sync failing silently weekly on prod since July). These tests pin the
header-name resolution across all real layouts HZZO ships: OLL classic,
DLL with the DDD column, DLL classic, and the magistralni pripravci sheets.
"""

from __future__ import annotations

import io

import openpyxl
import pytest

from app.services.halmed_sync_service import (
    _parse_drug_row,
    _parse_xlsx,
    _sheet_column_map,
)

# Real header rows from the July 2026 publications (17_07 OLL / 11_07 DLL)
OLL_HEADERS = (
    "ATK šifra", "Oznaka ograničenja primjene ", "Nezaštićeni naziv lijeka",
    "Način primjene", "Nositelj odobrenja", "Zaštićeni naziv lijeka",
    "Oblik, jačina i pakiranje", "R/RS", "PSL",
    "Oznaka indikacije s kriterijima za  primjenu", "Oznaka smjernice s kriterijima za propisivanje", "Stopa PDV-a",
)
DLL_WITH_DDD_HEADERS = (
    "ATK šifra", "Oznaka ograničenja primjene", "Nezaštićeni naziv lijeka",
    "DDD i mjerna jed. za DDD", "Način primjene", "Nositelj odobrenja",
    "Zaštićeni naziv lijeka", "Oblik, jačina i pakiranje",
    "Doplata za orig. pakiranje", "R/RS",
    "Oznaka indikacije s kriterijima za primjenu", "Oznaka smjernice s kriterijima za propisivanje", "Stopa PDV-a",
)
DLL_CLASSIC_HEADERS = (
    "ATK šifra", "Oznaka ograničenja primjene", "Nezaštićeni naziv lijeka",
    "Način primjene", "Nositelj odobrenja", "Zaštićeni naziv lijeka",
    "Oblik, jačina i pakiranje", "Doplata za orig. pakiranje", "R/RS",
    "Oznaka indikacije s kriterijima za bolničku primjenu", "Stopa PDV-a",
)
MAGISTRALNI_HEADERS = (
    "ATK šifra", "Oznaka ograničenja primjene", "Naziv pripravka",
    "R/RS", "Oznaka smjernice s kriterijima za propisivanje", "Stopa PDV-a",
)


def test_column_map_oll_classic():
    m = _sheet_column_map(OLL_HEADERS)
    assert m["atk"] == 0
    assert m["inn"] == 2
    assert m["nacin_primjene"] == 3
    assert m["nositelj_odobrenja"] == 4
    assert m["brand"] == 5
    assert m["oblik"] == 6
    assert m["r_rs"] == 7
    assert "doplata" not in m


def test_column_map_dll_with_ddd():
    m = _sheet_column_map(DLL_WITH_DDD_HEADERS)
    assert m["inn"] == 2
    assert m["nacin_primjene"] == 4  # DDD sits at 3 — everything shifts
    assert m["nositelj_odobrenja"] == 5
    assert m["brand"] == 6
    assert m["oblik"] == 7
    assert m["doplata"] == 8
    assert m["r_rs"] == 9


def test_column_map_dll_classic():
    m = _sheet_column_map(DLL_CLASSIC_HEADERS)
    assert m["doplata"] == 7
    assert m["r_rs"] == 8


def test_column_map_magistralni():
    m = _sheet_column_map(MAGISTRALNI_HEADERS)
    assert m["atk"] == 0
    assert m["naziv_pripravka"] == 2
    assert m["r_rs"] == 3
    assert "inn" not in m and "oblik" not in m and "doplata" not in m


def test_parse_row_dll_with_ddd_extracts_correct_fields():
    row = (
        "A01AB09 211", None, "mikonazol", "1 g (0,4 g)", "L", "Belupo d.d.",
        "Rojazol", "gel oral. 2%, 1x40 g", "0.92", "R", None, None, "5%",
    )
    drug = _parse_drug_row(row, _sheet_column_map(DLL_WITH_DDD_HEADERS))
    assert drug["atk"] == "A01AB09"
    assert drug["hzzo_sifra"] == "211"
    assert drug["naziv"] == "Rojazol"
    assert drug["inn"] == "mikonazol"
    assert drug["nacin_primjene"] == "L"  # not the DDD text
    assert drug["oblik"] == "gel oral. 2%, 1x40 g"
    assert drug["doplata"] == "0.92"  # not the oblik text
    assert drug["r_rs"] == "R"


def test_parse_row_magistralni_uses_pripravak_name():
    row = ("V_08AB  ", "DS", "Rp. Aethili aminobenzoatis 5,0", "R", None, "5%")
    drug = _parse_drug_row(row, _sheet_column_map(MAGISTRALNI_HEADERS))
    assert drug["naziv"] == "Rp. Aethili aminobenzoatis 5,0"
    assert drug["r_rs"] == "R"
    assert drug["oblik"] == ""


def _xlsx_bytes(sheet_name: str, headers, rows) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_name
    ws.append(list(headers))
    for r in rows:
        ws.append(list(r))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_parse_xlsx_shifted_layout_end_to_end():
    data = _xlsx_bytes(
        "DLL-1. dio",
        DLL_WITH_DDD_HEADERS,
        [("A01AB09 211", None, "mikonazol", None, "L", "Belupo d.d.", "Rojazol",
          "gel oral. 2%, 1x40 g", "0.92", "R")],
    )
    drugs = _parse_xlsx(data, "DLL")
    assert len(drugs) == 1
    assert drugs[0]["doplata"] == "0.92"
    assert drugs[0]["hzzo_lista"] == "DLL"
    assert drugs[0]["r_rs"] == "R"


def test_parse_xlsx_unknown_layout_fails_loudly():
    """A sheet without an ATK column must raise, not silently misparse."""
    data = _xlsx_bytes(
        "DLL-9. dio",
        ("Napomena", "Samo tekst", "Bez lijekova"),
        [("x", "y", "z")],
    )
    with pytest.raises(ValueError, match="ATK"):
        _parse_xlsx(data, "DLL")


def test_parse_xlsx_no_name_column_fails_loudly():
    data = _xlsx_bytes(
        "DLL-9. dio",
        ("ATK šifra", "R/RS", "Stopa PDV-a"),
        [("A01AB09 211", "R", "5%")],
    )
    with pytest.raises(ValueError, match="drug-name"):
        _parse_xlsx(data, "DLL")
