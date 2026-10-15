# BigQuery Cost Report

**Know what your Google BigQuery bill is actually made of.**

A small, **read-only** tool that turns your BigQuery job metadata into a
plain-English report: who is spending the most, on which datasets and tables, and
which queries cost the most — as a clean **PDF** plus machine-readable **JSON**.

Self-hosted. You run it with **your own** service account key, on **your own**
machine. It reads BigQuery **metadata** only — how much each job scanned and who ran
it. **No table data is ever read, and nothing leaves your machine.**

📄 **[See a real (anonymised) report →](sample-report.pdf)**

---

## The problem it solves

At the end of the month you get one number: a total. You do not get the story.

By the time the invoice lands, the query that caused it ran three weeks ago and
nobody remembers whose dashboard triggered it. This tool answers four questions:

- **Who** spent it — which person, team or service account drove the increase
- **Where** it went — the datasets and tables that actually cost the most
- **Which queries** — the individual queries responsible, grouped, with literals
  and comments stripped out
- **What's next** — the patterns that tend to blow up

---

## What it does

It scans `INFORMATION_SCHEMA.JOBS_BY_PROJECT` over a lookback window and reports:

- **Total** jobs, bytes billed, and estimated on-demand query cost (the flat
  **$6.25/TiB** scanned rate — same in the US, the EU and every region).
- **Top query spenders** (people) and **top service accounts**.
- **Top datasets/tables** by cost, and who drives each one.
- **Top queries** by cost (grouped, with comments/literals removed).
- How much the scan itself cost — tiny, usually within the 1 TiB/month free tier.

It is **read-only by design**: a safety layer rejects any statement that is not a
plain `SELECT`/`WITH`, and a per-query byte ceiling protects against mistakes. See
`src/safety.py` for the enforcement.

---

## Quickstart

You need:

- **Docker** (or Python 3.11+ if running from source).
- A **Google service account** that can **read** your BigQuery project
  (`roles/bigquery.metadataViewer` — read-only; the tool never writes).

### Fastest — the one-click script

The convenience script does the build and run for you: it creates the
`secrets`/`output` folders, builds the image, mounts them and runs the scan. If you
don't pass a project id it **asks you** at the prompt, so you can also just
double-click it.

**Windows:**

```bat
run-me.bat YOUR_PROJECT_ID YOUR_DATASET   # or just: run-me.bat  (it asks for both)
```

**macOS / Linux:**

```bash
chmod +x run-me.sh
./run-me.sh YOUR_PROJECT_ID YOUR_DATASET  # or just: ./run-me.sh  (it asks for both)
```

Before running, drop your read-only service-account key at `secrets/key.json`.

> **One dataset per run.** The community edition scans a **single dataset** you
> choose. Whole-project and multi-dataset scanning are part of the full edition.

### Option A — Docker (manual)

```bash
# 1) build
docker build -t bq-cost-report-community .

# 2) put your service-account JSON key at ./secrets/key.json, then:
mkdir -p secrets output
docker run --rm \
  -v "$(pwd)/secrets:/app/secrets" \
  -v "$(pwd)/output:/app/output" \
  bq-cost-report-community --project YOUR_PROJECT_ID --datasets YOUR_DATASET
```

The report PDF and JSON land in `./output/<project_id>/`.

### Option B — from source

```bash
pip install -r requirements.txt
python src/app.py --project YOUR_PROJECT_ID --datasets YOUR_DATASET --key secrets/key.json
```

### Dry run (reads nothing)

```bash
python src/app.py --project YOUR_PROJECT_ID --dry-run
```

### Common flags

| Flag | Meaning |
|------|---------|
| `--project ID` | BigQuery project to analyse |
| `--datasets D` | the **one** dataset to analyse (**required** for a real scan) |
| `--key FILE` | path to the service-account JSON key |
| `--days N` | lookback window (default 30) |
| `--human-only` | hide service accounts from the people view |
| `--dry-run` | plan only; reads nothing |

---

## Cost & safety

- **Analysis cost:** billed at the flat on-demand rate of **$6.25/TiB** scanned.
  Your scan reads only metadata, so it costs fractions of a cent — usually inside
  the 1 TiB/month free tier.
- **Safety:** the tool can only `SELECT`/`WITH` from `INFORMATION_SCHEMA`. It never
  inserts, updates, deletes or creates anything. It binds to your own machine and
  never uploads data anywhere.

---

## Why not just use something else?

**Google's own cost tooling** shows project-level totals and lets you explore jobs.
It does not turn that into a report that names the people, tables and queries
responsible, or tie spend back to a dbt model. That translation layer is the whole
product.

**Vantage, CloudZero, Finout, DoiT** are cloud-wide FinOps platforms, scoped and
priced for finance and platform teams, and they generally need your billing data
continuously exported to a third party. This is the opposite: narrow, cheap, on your
machine, and pointed at BigQuery specifically.

**Why is this safe to give a service-account key?** Because it needs two metadata
permissions that grant no access to table contents, it never writes anything, and
the read-only constraint is enforced in code rather than promised in a README.

> **On BigQuery Editions / committed slots.** The on-demand view — bytes scanned at
> the published per-TiB rate — is fully covered today. Under slot-based or committed
> pricing, per-query cost attribution means something different, and that is the next
> thing being built. If you are on slots, open an issue and describe your setup.

---

## Full edition

The community edition deliberately stops at "who spends what". The **full edition**
adds the analysis that tells you *why your bill spiked* and *what could surprise you
next*:

| Feature | Community (free) | Full edition |
|---|---|---|
| Cost by user / dataset / query | ✅ | ✅ |
| Read-only guarantee | ✅ | ✅ |
| PDF + JSON report | ✅ | ✅ |
| Self-hosted, nothing leaves your machine | ✅ | ✅ |
| **Scan scope** | **one dataset per run** | whole project, or any datasets you pick |
| **Surprise-bill risk flags** (`SELECT *`, no `LIMIT`, missing partition filters, cross-region joins, repeated queries, zombie tables) | — | ✅ |
| **Storage cost analysis** (monthly, logical vs physical) | — | ✅ |
| **dbt model attribution** (which models cost the most) | — | ✅ |
| **Daily trends & spike detection** (who caused the jump) | — | ✅ |
| **Local dashboard** (browse the same data in the browser) | — | ✅ |

**One-time licence, one BigQuery project, instant download. No subscription.**

👉 **[Get the full edition](https://bigquery-cost-report.lemonsqueezy.com/checkout/buy/01660205-f913-4d17-8938-6ba242595b3c)**

Same read-only, self-hosted, nothing-leaves-your-machine guarantees.

---

## Contact

Open an issue here for anything about the community edition.

For the full edition, invoicing, or larger/enterprise purchases:
**alex.vinter24@gmail.com**

---

## License

MIT — see [LICENSE](LICENSE).

This licence covers the **community edition only**. The full (paid) edition is a
separate commercial product under its own terms, and none of its code is covered by
this licence.
