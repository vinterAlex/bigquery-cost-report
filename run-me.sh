#!/usr/bin/env bash
# One-click build & run helper (macOS / Linux).
#
# Convenience wrapper around the README commands. It does NOT need to
# be edited:
#
#   1) builds the Docker image,
#   2) makes the  secrets  and  output  folders next to this file,
#   3) runs the tool, mounting them into the container.
#
# Put your service-account JSON key file into the  secrets  folder.
# This script then asks for the project id, so you can also just run it
# without typing anything first:
#
#      ./run-me.sh
#      ./run-me.sh YOUR_PROJECT_ID     (skip the prompt)
#
# The community edition analyses ONE dataset per run, so you must also
# give a dataset (as a 2nd argument, or it asks):
#
#      ./run-me.sh YOUR_PROJECT_ID YOUR_DATASET
#
# The PDF + JSON report lands in the  output  folder.
#
# Make it executable once:
#      chmod +x run-me.sh
set -euo pipefail

# Work in the folder this script lives in.
cd "$(dirname "$0")"

# ---- 1) project id (argument, else ask) ------------------
PROJECT="${1:-}"
if [ -z "$PROJECT" ]; then
  read -r -p "Enter your BigQuery project id: " PROJECT
fi
if [ -z "$PROJECT" ]; then
  echo
  echo "No project id entered - nothing to run."
  exit 1
fi

# ---- 1b) dataset (community = one dataset) ---------------
DATASET="${2:-}"
if [ -z "$DATASET" ]; then
  read -r -p "Enter the ONE dataset to analyse in this run: " DATASET
fi
if [ -z "$DATASET" ]; then
  echo
  echo "This community edition needs one dataset. Pass  run-me.sh"
  echo "PROJECT DATASET  or answer the prompt above. Whole-project"
  echo "scanning is a full-edition feature."
  exit 1
fi

# ---- 2) folders ------------------------------------------
mkdir -p secrets output

if ! ls secrets/*.json >/dev/null 2>&1; then
  echo
  echo "NOTE: no .json key found in the  secrets  folder."
  echo "Put your read-only Google service-account key there before"
  echo "running, e.g.  $(pwd)/secrets/key.json"
  echo
  read -r -p "Press Enter to continue anyway..." _
fi

# ---- 3) build the image only if not already built --------
if docker image inspect bq-cost-report-community >/dev/null 2>&1; then
  echo "[1/3] Image already built - skipping build."
else
  echo "[1/3] Building the image..."
  docker build -t bq-cost-report-community .
fi

# ---- 4) run ----------------------------------------------
echo "[2/3] Running the scan on project  $PROJECT , dataset  $DATASET ..."
if ! docker run --rm \
    -v "$(pwd)/secrets:/app/secrets" \
    -v "$(pwd)/output:/app/output" \
    bq-cost-report-community --project "$PROJECT" --datasets "$DATASET"; then
  echo
  echo "ERROR: the scan did not complete."
  echo
  echo "Wrong project or dataset? Re-run the script with the correct"
  echo "values, e.g.:  ./run-me.sh YOUR_PROJECT_ID YOUR_DATASET"
  echo "The dataset must exist and be visible to this service account."
  exit 1
fi

# ---- 5) done ---------------------------------------------
echo "[3/3] Done. Your report is in:  $(pwd)/output/$PROJECT/"
