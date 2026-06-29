"""Weekly digest builder.

Composes a Commissioner-facing briefing from the most-recent
inference_audit rows over the chosen window. Output formats:

  * markdown — for direct email / Telegram / WhatsApp forwarding
  * json     — for downstream pipelines (Reports download)

Window tokens: 1h, 24h, 7d, 30d (reuses the audit store parser).
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from backend.inference import store


async def build_digest(
    *,
    window: str = "7d",
    limit: int = 500,
) -> dict:
    """Pull the audit rows in the window and assemble a digest.

    Returns both the raw shape (rows) and the rendered markdown so the
    router can serve either via a ``?format=`` query.
    """
    rows = await store.list_audit_rows(window=window, limit=limit)

    by_workstream: dict[str, list[dict]] = defaultdict(list)
    severity_counts: dict[str, int] = defaultdict(int)
    latest_per_workstream: dict[str, dict] = {}

    for r in rows:
        by_workstream[r["workstream"]].append(r)
        sev = r["severity"] or "UNKNOWN"
        severity_counts[sev] += 1
        if (
            r["workstream"] not in latest_per_workstream
            or (r["generated_at"] or "") > (latest_per_workstream[r["workstream"]]["generated_at"] or "")
        ):
            latest_per_workstream[r["workstream"]] = r

    summary = {
        "window": window,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "row_count": len(rows),
        "by_workstream": {ws: len(items) for ws, items in by_workstream.items()},
        "by_severity": dict(severity_counts),
        "latest_per_workstream": {
            ws: {
                "trace_id": row["trace_id"],
                "severity": row["severity"],
                "confidence": row["confidence"],
                "generated_at": row["generated_at"],
            }
            for ws, row in latest_per_workstream.items()
        },
    }
    return {
        "summary": summary,
        "rows": rows,
        "markdown": render_markdown(summary, rows),
    }


def render_markdown(summary: dict, rows: list[dict]) -> str:
    """Render the digest as a clean Markdown document."""
    lines: list[str] = []
    lines.append(f"# HMIS Inference Digest — {summary['window']}")
    lines.append("")
    lines.append(f"_Generated at {summary['generated_at']}_")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Rows considered: **{summary['row_count']}**")
    if summary["by_severity"]:
        sev_table = ", ".join(
            f"{k}: **{v}**" for k, v in sorted(summary["by_severity"].items())
        )
        lines.append(f"- Severity breakdown — {sev_table}")
    if summary["by_workstream"]:
        ws_table = ", ".join(
            f"{k}: **{v}**" for k, v in sorted(summary["by_workstream"].items())
        )
        lines.append(f"- Per workstream — {ws_table}")
    lines.append("")
    lines.append("## Latest per workstream")
    lines.append("")
    lines.append("| Workstream | Severity | Confidence | Generated |")
    lines.append("|------------|----------|------------|-----------|")
    for ws in sorted(summary["latest_per_workstream"]):
        lp = summary["latest_per_workstream"][ws]
        lines.append(
            "| {ws} | {sev} | {conf:.3f} | {dt} |".format(
                ws=ws,
                sev=lp["severity"] or "—",
                conf=float(lp["confidence"] or 0.0),
                dt=lp["generated_at"] or "—",
            )
        )
    lines.append("")

    # Top critical/high rows — first 20.
    indic = [r for r in rows if (r["severity"] or "") in ("CRITICAL", "HIGH")]
    if indic:
        lines.append(f"## Notable Signals ({len(indic)} shown, first 20)")
        lines.append("")
        lines.append("| When | Workstream | Severity | Trace | Headline |")
        lines.append("|------|------------|----------|-------|----------|")
        for r in indic[:20]:
            headline = _preview(r["response"] or {})
            lines.append(
                "| {dt} | {ws} | {sev} | `{trace}` | {hl} |".format(
                    dt=r["generated_at"] or "—",
                    ws=r["workstream"],
                    sev=r["severity"] or "—",
                    trace=r["trace_id"][:8],
                    hl=headline,
                )
            )
        lines.append("")

    lines.append("---")
    lines.append("_Auto-generated. Do not reply to this document._")
    return "\n".join(lines)


def _preview(response: dict) -> str:
    """Return one short line summarising a response payload."""
    if not response:
        return "—"
    rank = response.get("data", {}).get("ranked") or []
    if rank and isinstance(rank, list):
        return (rank[0].get("headline") or "—")[:120]
    signals = response.get("data", {}).get("signals") or []
    if signals and isinstance(signals, list):
        return (signals[0].get("one_liner") or "—")[:120]
    return (response.get("headline") or "—")[:120]
