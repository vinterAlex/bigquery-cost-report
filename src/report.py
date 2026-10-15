"""Build the PDF and JSON report from scan results.

The PDF is the deliverable users share with their manager: a clean,
styled report of cost attribution. The JSON files are machine-readable
and stored for re-running / auditing.

The community edition's PDF covers the core cost-attribution buckets.
Surprise-bill risk analysis, storage cost, dbt model attribution and
daily trends are part of the full edition; a closing page points the
reader at what the full edition adds.

Nothing here is a savings estimate. We report what is spent; the
numbers are derived from bytes billed times the resolved region price.
"""

import json
from datetime import datetime
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

GRID = colors.HexColor("#D5D8DC")
HEADER_BG = colors.HexColor("#EEF1F3")
ACCENT = colors.HexColor("#1A5276")


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "CTitle", parent=base["Title"], textColor=ACCENT, fontSize=22,
            spaceAfter=6,
        ),
        "subtitle": ParagraphStyle(
            "CSub", parent=base["Normal"], textColor=colors.HexColor("#7F8C8D"),
            fontSize=10, alignment=TA_CENTER, spaceAfter=12,
        ),
        "h2": ParagraphStyle(
            "CH2", parent=base["Heading2"], textColor=ACCENT, fontSize=13,
            spaceBefore=10, spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "CBody", parent=base["Normal"], fontSize=9.5, leading=13,
        ),
        "small": ParagraphStyle(
            "CSmall", parent=base["Normal"], fontSize=8,
            textColor=colors.HexColor("#5D6D7E"),
        ),
    }


def _money(value):
    if value is None:
        return "n/a (capacity pricing)"
    return f"${value:,.2f}"


def _gb(value):
    return f"{value:,.2f} GB"


# Usable width inside the A4 page margins (18 mm each side).
_PAGE_WIDTH = A4[0] - 36 * mm

_CELL_STYLE = ParagraphStyle(
    "CCell", fontSize=8, leading=10, wordWrap="CJK",
)


def _cell(text):
    return Paragraph(escape(str(text)), _CELL_STYLE)


def _cost_table(rows, styles, name_header="Name"):
    """rows: list of (name, jobs, bytes_gb, cost)."""

    data = [[name_header, "Jobs", "Bytes", "Cost"]]
    for name, jobs, gb, cost in rows:
        data.append([_cell(name), str(jobs), _gb(gb), _money(cost)])

    table = Table(
        data, repeatRows=1,
        colWidths=[w * _PAGE_WIDTH for w in (0.60, 0.10, 0.15, 0.15)],
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, GRID),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#F8F9F9")]),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (2, 0), (3, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def build_report(paths, result):
    """Write a PDF report. `result` is the dict from run_scan."""

    styles = _styles()

    path = paths["report"]
    doc = SimpleDocTemplate(
        path, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
    )

    story = []

    story.append(Paragraph("BigQuery Cost Report", styles["title"]))
    story.append(Paragraph(
        f"Project: <b>{result['project_id']}</b> &nbsp;·&nbsp; "
        f"Generated {result['generated_at']}",
        styles["subtitle"],
    ))
    if result.get("per_tib") is None:
        pricing_line = (
            f"Pricing model: {result['pricing_origin']}. "
            "Query cost is shown as 'n/a' because capacity/Editions "
            "pricing is billed by slot-hours, not $/TiB. "
            "Read-only; no data leaves this machine."
        )
    else:
        pricing_line = (
            f"Pricing: {result['pricing_origin']} ({_money(result['per_tib'])} "
            "per TiB scanned, on-demand). "
            "Read-only; no data leaves this machine."
        )
    story.append(Paragraph(pricing_line, styles["small"]))

    scan_cost = result.get("scan_cost_usd")
    scan_queries = result.get("scan_queries", 0)
    if scan_cost is not None and result.get("per_tib") is not None:
        story.append(Paragraph(
            f"About this scan: this run processed metadata in {scan_queries} "
            f"read-only query/queries and itself billed {_money(scan_cost)} "
            "(typically fractions of a cent, often within the 1 TiB/month "
            "free tier). It never reads or changes your table data.",
            styles["small"],
        ))

    for warning in result.get("warnings") or []:
        story.append(Paragraph(
            f'<font color="#C0392B"><b>Note:</b></font> {escape(warning)}',
            styles["small"],
        ))

    story.append(Spacer(1, 6))

    # ---- Totals ----
    totals = result.get("totals", {})
    t = Table([
        ["Total jobs", "Total bytes billed", "Estimated query cost"],
        [str(totals.get("jobs", 0)),
         _gb((totals.get("bytes_billed") or 0) / 1024 ** 3),
         _money(totals.get("cost_usd"))],
    ])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, GRID),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
    ]))
    story.append(t)
    if totals.get("cost_usd") is not None:
        story.append(Paragraph(
            "Estimated query cost is before the 1 TiB/month free tier "
            "and excludes storage.",
            styles["small"],
        ))

    n_jobs = totals.get("jobs") or 0
    cache_jobs = totals.get("cache_hit_jobs")
    if cache_jobs is not None and n_jobs:
        story.append(Paragraph(
            f"Result cache: {cache_jobs:,} of {n_jobs:,} jobs "
            f"({cache_jobs / n_jobs * 100:.0f}%) were served from "
            "BigQuery's result cache and billed nothing.",
            styles["small"],
        ))
    err_jobs = totals.get("errored_jobs")
    if err_jobs:
        story.append(Paragraph(
            f"Errored jobs: {err_jobs:,} job(s) ended in an error but "
            f"still billed {_money(totals.get('errored_cost_usd'))} "
            f"({_gb((totals.get('errored_bytes') or 0) / 1024 ** 3)}). "
            "Failed queries are charged for what they scanned.",
            styles["small"],
        ))
    story.append(Spacer(1, 8))

    # ---- Attribution ----
    story.append(Paragraph("Cost attribution", styles["h2"]))

    story.append(Paragraph("Top query spenders (people)", styles["body"]))
    story.append(_cost_table([
        (r["name"], r["jobs"], r["bytes_billed"] / 1024 ** 3, r["cost_usd"])
        for r in result.get("humans", [])
    ], styles))
    story.append(Spacer(1, 6))

    if result.get("service_accounts"):
        story.append(Paragraph("Top service accounts", styles["body"]))
        story.append(_cost_table([
            (r["name"], r["jobs"], r["bytes_billed"] / 1024 ** 3, r["cost_usd"])
            for r in result.get("service_accounts", [])
        ], styles))
        story.append(Spacer(1, 6))

    story.append(Paragraph("Top datasets/tables", styles["body"]))
    story.append(_cost_table([
        (r["name"], r["jobs"], r["bytes_billed"] / 1024 ** 3, r["cost_usd"])
        for r in result.get("datasets", [])
    ], styles))
    story.append(Spacer(1, 6))

    # ---- Top queries ----
    top_queries = result.get("top_queries") or []
    if top_queries:
        story.append(Paragraph("Top queries (by cost)", styles["body"]))
        story.append(_cost_table([
            (
                " ".join((q.get("query") or "").split())[:120],
                q["jobs"], q["bytes_billed"] / 1024 ** 3, q["cost_usd"],
            )
            for q in top_queries
        ], styles, name_header="Query"))
        story.append(Paragraph(
            "Identical statements are grouped: other queries by their SQL "
            "with comments and literal values removed (shortened to fit).",
            styles["small"],
        ))
        story.append(Spacer(1, 6))

    # ---- Full edition callout ----
    story.append(PageBreak())
    story.append(Paragraph("Beyond this report - the full edition",
                           styles["h2"]))
    story.append(Paragraph(
        "This community edition shows who and what is driving your "
        "BigQuery bill. The full edition adds the analysis that turns "
        "that picture into action:",
        styles["body"],
    ))
    story.append(Spacer(1, 6))
    for item in [
        "Surprise-bill risk flags - eight checks covering SELECT * on "
        "large tables, queries without LIMIT, missing partition filters, "
        "cross-region joins, repeated queries, zombie tables, spend on "
        "jobs that failed anyway, and large unpartitioned tables being "
        "queried.",
        "Partitioning and clustering review - which tables are set up to "
        "let BigQuery skip data, and which are not.",
        "Storage cost analysis - what your data costs to store each "
        "month, and whether physical (compressed) billing is worth it.",
        "dbt model attribution - which models are the biggest spenders.",
        "Daily cost trends and spike detection - which day, and who, "
        "caused the jump.",
        "A no-CLI local web app - pick your project and run the scan "
        "from the browser.",
    ]:
        story.append(Paragraph(f"• {item}", styles["body"]))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "For the full edition, email <b>alex.vinter24@gmail.com</b>. "
        "Read-only, self-hosted, nothing leaves your machine.",
        styles["body"],
    ))

    doc.build(story)

    return path


def write_json(paths, result):
    with open(paths["cost"], "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)
