# BigQuery Cost Report — Community Edition

A small, **read-only** tool that tells you what is driving your Google
BigQuery bill: who is spending the most, on which datasets/tables, and
which queries cost the most — and puts it in a clean PDF report.

Self-hosted. You run it with **your** service account key, on your own
machine. It only reads BigQuery **metadata** (how much each thing
scanned and who ran what). **No table data is ever read, and nothing
leaves your machine.**

> This is the **community (open-source) edition**. It is the free entry
> point. The **full edition** adds the analysis that turns the picture
> into action — see [the comparison](#full-edition) at the end.
>
> **Scope:** the community edition analyses **one dataset per run**. You
> pick a single dataset with `--datasets` (or in the one-click scripts).
> Whole-project and multi-dataset scanning are features of the full
> edition — email alex.vinter24@gmail.com.

---

## What it does

It scans `INFORMATION_SCHEMA.JOBS_BY_PROJECT` over a lookback window and
reports, in a PDF + JSON:

- **Total** jobs, bytes billed, and estimated on-demand query cost
  (a flat **$6.25/TiB** scanned — same in the US and the EU and every
  region).
- **Top query spenders** (people) and **top service accounts**.
- **Top datasets/tables** by cost, and who drives each one.
- **Top queries** by cost (grouped, with comments/literals removed).
- How much the scan itself cost (tiny — metadata reads, often within
  the 1 TiB/month free tier).

It is **read-only by design** — a safety layer rejects any statement
that is not a plain `SELECT`/`WITH`, and a per-query byte ceiling
protects against mistakes. See `src/safety.py` for the enforcement.

---

## Quickstart

You need:

- **Docker** (or Python 3.11+ if running from source).
- A **Google service account** that can **read** your BigQuery project
  (`roles/bigquery.metadataViewer` — read-only; the tool never writes).

### Fastest — the one-click script

There is a convenience script that does the build + run for you (it
makes the `secrets`/`output` folders, builds the image, mounts them,
and runs the scan). If you don't pass a project id it **asks you for
it** at the prompt, so you can also just run/click it without typing
anything first.

**Windows** (double-click it, or run in a terminal):

```bat
run-me.bat YOUR_PROJECT_ID YOUR_DATASET   # or just: run-me.bat  (it asks for both)
```

**macOS / Linux** (make executable once, then run):

```bash
chmod +x run-me.sh
./run-me.sh YOUR_PROJECT_ID YOUR_DATASET  # or just: ./run-me.sh  (it asks for both)
```

Before running, drop your read-only service-account key at
`secrets/key.json`.

> **One dataset per run.** The community edition scans a **single
> dataset** you choose (`YOUR_DATASET` above). To cover the whole
> project or many datasets at once, see the [full edition](#full-edition).

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

> The community edition requires exactly **one** `--datasets` value per
> run. Omit it and the tool stops with a pointer to the full edition.

### Option B — from source

```bash
pip install -r requirements.txt
python src/app.py --project YOUR_PROJECT_ID --datasets YOUR_DATASET --key secrets/key.json
```

### Dry run (reads nothing)

A dry run only lists the project; it does not read anything, so it does
**not** need a dataset.

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

- **Analysis cost:** billed on the flat on-demand rate of **$6.25/TiB**
  scanned (US and EU and every region). Your scan reads only metadata,
  so it is fractions of a cent — usually under the 1 TiB/month free
  tier.
- **Safety:** the tool can only `SELECT`/`WITH` from `INFORMATION_SCHEMA`.
  It never inserts, updates, deletes or creates anything. It binds only
  to your own machine and never uploads data anywhere.

---

## Full edition <a name="full-edition"></a>

The community edition deliberately stops at "who spends what". The
**full edition** adds the analysis that tells you *why your bill spiked*
and *what could surprise you next*:

| Feature | Community (free) | Full edition |
|---|---|---|
| Cost by user / dataset / query | ✅ | ✅ |
| Read-only guarantee | ✅ | ✅ |
| PDF report | ✅ | ✅ |
| Self-hosted, nothing leaves your machine | ✅ | ✅ |
| **Scan scope** | **one dataset per run** | whole project, or any datasets you pick |
| **Surprise-bill risk flags** (SELECT *, no LIMIT, missing partition filters, cross-region joins, repeated queries, zombie tables) | — | ✅ |
| **Storage cost analysis** (monthly, logical vs physical) | — | ✅ |
| **dbt model attribution** (which models cost the most) | — | ✅ |
| **Daily trends & spike detection** (who caused the jump) | — | ✅ |
| **No-CLI local web app** (pick project, run from the browser) | — | ✅ |

For the full edition, email **alex.vinter24@gmail.com** — same
read-only, self-hosted, nothing-leaves-your-machine guarantees.

### Get the full edition — $199 one-time
### 🚨 Early-Bird Discount: Use code `LAUNCH25` for 25% off (First 10 buyers only) ⏳

[Buy BigQuery Cost Report — Full Edition](https://bigquery-cost-report.lemonsqueezy.com/checkout/buy/0d0889a9-4179-4b22-8c3f-5b4d6846ab04)

Same read-only, self-hosted, nothing-leaves-your-machine — plus
surprise-bill risk flags, storage cost, dbt attribution, daily trends
and the no-CLI local web app. One-time license, one BigQuery project,
instant download.

Example:
<img width="1536" height="1507" alt="cost_report" src="https://github.com/user-attachments/assets/755d480b-a515-47ff-9946-c72da3b69853" />


For larger or enterprise purchases (escrow, invoicing), email
**alex.vinter24@gmail.com**.

---

## Contact <a name="contact"></a>

**alex.vinter24@gmail.com**

Get the full edition: [Buy BigQuery Cost Report — Full Edition](https://bigquery-cost-report.lemonsqueezy.com/checkout/buy/0d0889a9-4179-4b22-8c3f-5b4d6846ab04)

The full edition is the same self-hosted, read-only, no-data-leaves tool
— with surprise-bill risk flags, storage cost, dbt attribution, daily
trends and the local web app added. No subscription. One-time license.

---

## License

MIT — see [LICENSE](LICENSE). This license covers the community edition
only; the full (paid) edition is a separate product under its own terms.
