"""
Live Power Query (M) verification — the run-verify half of the validation loop for phase 2.

Unlike DAX, M has no standalone queryable endpoint: you cannot send an M expression to the engine and get
a result the way `EVALUATE` runs DAX. So the only faithful run-verification is a **refresh round-trip**:
write the candidate M to a temporary table, ask the Tabular engine to refresh it (which runs the real
Mashup engine against the real data source), and read back the result — proven viable by the M0 spike.

Mechanism (validated on a live model):
- A raw M (import) partition added via TOM has NO inferred columns, so a naked `EVALUATE` fails. Instead
  the probe returns `Table.Schema(candidate)`, whose output shape is FIXED (Name/TypeName/Kind/...). We
  declare those fixed columns up front, so after refresh `EVALUATE` returns the *candidate's output schema*
  as data rows.
- A broken candidate makes `Model.SaveChanges()` (after `RequestRefresh`) throw, carrying the Mashup
  engine's own error (e.g. `[Expression.Error] 找不到表的"X"列`) — exactly what the repair loop consumes.

Either way `run_verified=True`, so the product never presents unexecuted M as if it had run. The temporary
table is uniquely named and always removed (including on error), so it never touches the user's real tables.
"""

from __future__ import annotations

import re
from typing import Any

from ..context.live_source import _LiveSession, find_adomd_dll, find_instances
from ..context.live_writer import _disconnect, _t, _tom
from ..core.artifact import ValidationResult

_PROBE_TABLE = "__pbi_ai_mq_probe"
# Table.Schema output columns we read back (M column name -> TOM DataType enum name). Fixed + known.
_SCHEMA_COLS = [("Name", "String"), ("TypeName", "String"), ("Kind", "String")]


def _clean_m_error(exc: Exception) -> str:
    """Extract the meaningful part of a refresh failure. The engine wraps the real cause like:
    "Failed to save modifications... Error returned: 'OLE DB or ODBC error: [Expression.Error] <msg>.'"
    so we surface the [Expression.Error]/[DataFormat.Error] core when present, else the first line."""
    text = str(exc).strip()
    m = re.search(r"\[(?:Expression|DataFormat|DataSource)\.Error\][^\r\n]*", text)
    if m:
        return m.group(0).strip().rstrip(" .。")[:300]
    m = re.search(r"Error returned:\s*'?([^\r\n]+)", text)
    if m:
        return m.group(1).strip().rstrip(" '.。")[:300]
    return text.splitlines()[0][:300] if text else type(exc).__name__


def _probe_m(expression: str) -> str:
    """Wrap the candidate M so the probe table returns its output SCHEMA (fixed shape we can read back)."""
    return (
        "let\n"
        f"    __Candidate = (\n{expression}\n    ),\n"
        "    __Schema = Table.Schema(__Candidate)\n"
        "in\n"
        "    __Schema"
    )


class MQueryEvaluator:
    """Verifies a candidate M query against an open Power BI Desktop engine on `port` via a refresh round-trip.

    `evaluate_m` returns a `ValidationResult`: on success `ok=True, run_verified=True` and `sample` is a
    human-readable summary of the output columns + types; on failure `ok=False, run_verified=True` with the
    engine's error. `dll` is Power BI's bundled ADOMD client (for the schema read-back); refresh itself
    goes through TOM and needs no extra DLL.
    """

    def __init__(self, port: int, dll: str | None = None) -> None:
        self.port = port
        self.dll = dll or find_adomd_dll(find_instances())

    def evaluate_m(self, expression: str) -> ValidationResult:
        """Run-verify a candidate M via the refresh round-trip: ok + run_verified on success (with a column
        summary in `sample`); a verified failure carries the engine error; a connect/DLL failure is honestly
        NOT run_verified."""
        if not expression.strip():
            return ValidationResult(ok=False, errors=["未生成任何 M 代码"], run_verified=False)
        ok, run_verified, cols, msg = self._run_probe(expression)
        if not ok:
            return ValidationResult(ok=False, errors=[msg], run_verified=run_verified)
        summary = (f"{len(cols)} 列：" + "、".join(f"{n}（{k}）" for n, k in cols)) if cols else (msg or "刷新成功")
        return ValidationResult(ok=True, sample=summary, run_verified=True)

    def _run_probe(self, expression: str) -> tuple[bool, bool, list[tuple[str, str]], str]:
        """The refresh round-trip lifecycle, shared by evaluate_m and probe_columns. Returns
        (ok, run_verified, cols, message):
        - success:            (True, True, [(name, kind), ...], "")  — `message` holds a degraded note if the
                              refresh worked but the column read-back didn't (then `cols` is []);
        - refresh failed:     (False, True, [], engine_error);
        - connect/DLL failed: (False, False, [], reason)."""
        import System  # type: ignore[import-not-found]  # available after _tom() loads clr

        _tom()  # ensure assemblies loaded before touching System.Enum / TOM types
        try:
            server = System.Activator.CreateInstance(_t("Server"))
            server.Connect(f"Data Source=localhost:{self.port}")
        except Exception as e:  # noqa: BLE001 — DLL load / connect failure: cannot run, report honestly
            return (False, False, [], f"连接/加载 TOM 失败：{type(e).__name__}: {e}")

        created = False
        try:
            model = server.Databases[0].Model
            self._drop_if_present(model)  # clean any leftover from a previous run

            # build temp table with the schema-probe M + the fixed Table.Schema columns declared
            table = System.Activator.CreateInstance(_t("Table"))
            table.Name = _PROBE_TABLE
            partition = System.Activator.CreateInstance(_t("Partition"))
            partition.Name = _PROBE_TABLE
            msource = System.Activator.CreateInstance(_t("MPartitionSource"))
            msource.Expression = _probe_m(expression)
            partition.Source = msource
            table.Partitions.Add(partition)
            dtype_enum = _tom().GetType("Microsoft.AnalysisServices.Tabular.DataType")
            for col_name, dtype_name in _SCHEMA_COLS:
                col = System.Activator.CreateInstance(_t("DataColumn"))
                col.Name = col_name
                col.SourceColumn = col_name  # must match the M (Table.Schema) output column name
                col.DataType = System.Enum.Parse(dtype_enum, dtype_name)
                table.Columns.Add(col)
            model.Tables.Add(table)
            model.SaveChanges()
            created = True

            # the real test: refresh runs the Mashup engine against the real source
            reftype = _tom().GetType("Microsoft.AnalysisServices.Tabular.RefreshType")
            table.RequestRefresh(System.Enum.Parse(reftype, "Full"))
            try:
                model.SaveChanges()
            except Exception as exc:  # noqa: BLE001 — the engine's rejection IS the verified result
                return (False, True, [], _clean_m_error(exc))

            cols, note = self._read_cols()  # success: read back the candidate's output schema
            return (True, True, cols, note)
        except Exception as exc:  # noqa: BLE001
            return (False, True, [], _clean_m_error(exc))
        finally:
            if created:
                try:
                    self._drop_if_present(server.Databases[0].Model)
                except Exception:  # noqa: BLE001 — best-effort cleanup
                    pass
            _disconnect(server)

    def _drop_if_present(self, model: Any) -> None:
        leftover = next((t for t in model.Tables if t.Name == _PROBE_TABLE), None)
        if leftover is not None:
            model.Tables.Remove(leftover)
            model.SaveChanges()

    def _read_cols(self) -> tuple[list[tuple[str, str]], str]:
        """Read the probe table (the candidate's Table.Schema output) back via ADOMD EVALUATE → [(name,
        kind)]. On a degraded read (no DLL / query error) returns ([], note); the refresh already succeeded."""
        if not self.dll:
            return [], "刷新成功（未找到 ADOMD DLL，未能读回列结构）"
        try:
            with _LiveSession(self.port, self.dll) as s:
                rows = s.query(f"EVALUATE '{_PROBE_TABLE}'")
        except Exception as exc:  # noqa: BLE001
            return [], f"刷新成功（读回列结构失败：{_clean_m_error(exc)}）"
        cols: list[tuple[str, str]] = []
        for r in rows:
            name = r.get(f"{_PROBE_TABLE}[Name]")
            kind = r.get(f"{_PROBE_TABLE}[Kind]") or r.get(f"{_PROBE_TABLE}[TypeName]")
            if name is not None:
                cols.append((str(name), str(kind)))
        return cols, ""
