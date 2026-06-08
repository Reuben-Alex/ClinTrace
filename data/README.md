# ClinTrace data

## NHAMCS Emergency Department (primary — verification + UI lab)

**Real, public-use U.S. ED visits** from the CDC National Hospital Ambulatory Medical Care Survey.

- Documentation: https://www.cdc.gov/nchs/nhamcs/documentation/index.html
- Public-use Stata files: 2018–2022 ED releases

### Download

```bash
make download-nhamcs
# or multiple years:
. .venv/bin/activate && python scripts/download_nhamcs.py --years 2018,2019,2020,2021,2022
```

Files land in `data/nhamcs/ed{year}-stata.dta` (large; gitignored).

### RVC codebook

Reason-for-visit codes (`RFV13D`, etc.) are decoded via Stata value labels:

```bash
make build-rvc-codebook
```

Committed artifact: `data/nhamcs/rvc_codebook.csv` (~1.3k labels).

### What the agent sees vs eval only

| Field | Agent input | Evaluation |
|-------|-------------|------------|
| Decoded RVC complaint | Yes | — |
| Vitals (temp, HR, RR, BP, SpO2, pain) | Yes | — |
| Demographics / arrival | Yes | — |
| `IMMEDR` (nurse triage immediacy 1–5) | **No** | Ground truth vs predicted ESI |
| `DIAG1`–`DIAG5` (ICD-10-CM) | **No** | Post-hoc diagnosis consistency (`--run-diag-eval`) |

**IMMEDR** is mapped 1:1 to ESI-style levels for metrics. Document as NHAMCS *immediacy*, not trademark ESI.

### Row filtering

Incomplete rows are dropped when:

- `IMMEDR` not in 1–5
- Invalid/missing primary RFV (`RFV13D` ≤ 0)
- Fewer than 2 vitals among temp, pulse, RR, BP, SpO2

Roughly ~60–65% of 2022 PU rows remain after filtering.

### Verification commands

```bash
make verify              # 50 cases, quality eval + Phoenix
make verify-full         # 200 cases + diagnosis consistency eval
make stress-test         # 100-case stress pass
```

```bash
python -m verification.run_verification --n_samples 50 --run-diag-eval
```

Key safety metric: **critical under-triage** (IMMEDR 1–2 predicted as ESI 3+).

### BigQuery

Cleaned NHAMCS rows load into `black-tenure-439907-v8:clinictrace.ed_triage`:

```bash
make prep-bq      # data/bq_ready/combined.ndjson
make reload-bq    # replace table from NDJSON + schema.json
```

The **NHAMCS Test Lab** UI samples cases from this table (sub-second). Without BigQuery credentials it falls back to local Stata (~15s first load).

`esi_level` and `ground_truth_immedr` are nurse immediacy (1–5). `diagnosis_codes` is post-hoc eval only (comma-separated ICD-10-CM).
