# Escalation SOP

Use this when `exceptions` or `reconciliation` flags a distributor week. The path is always the same: detect, contact the distributor, then escalate inside the company if the file is not corrected.

## Severity

Severity is set by the validation check. Reconciliation flags use the same tiers when the root cause matches.

| Severity | Checks and root causes | What it means |
| --- | --- | --- |
| High | Duplicates, missing weeks, unmapped SKU, unmapped account, negative volume, parse failure. Root causes Duplicate, Missing Week, Unmapped Code. | The week cannot be trusted. Volume is missing, doubled, or sitting on a code the internal book does not know. |
| Medium | Outlier volume, late file. Root cause Unit/Format Issue when rejected rows explain at least half the liter gap. Timing when a file arrives after the SLA and the week is otherwise unexplained. | The file arrived or parsed, but the unit, the clock, or a single line is outside the rule. |
| Low | Zero volume. | A zero line is present. Review it in the weekly batch unless the same account repeats. |

On this run the high checks are the ones that moved the scorecard: D02 completeness 95.24 (five missing weeks), D05 completeness 97.14 (three missing weeks), D01, D03, and D06 uniqueness 98.04 (2% extra rows), D07 and D08 validity near 96.3 (3% unmapped codes), D03 validity 95.32 (23,887 date rejects). D02 and D07 timeliness are 0 because those two files were late.

## Clock

The timeliness SLA in `config.yaml` is 10 days after the latest week start in the file. This run's latest week start is 2024-12-30. On-time files were marked received on 2025-01-03. Late files were marked received on 2025-01-20.

| Severity | Contact the distributor | Escalate internally if there is no corrected file |
| --- | --- | --- |
| High | 1 business day from detection | 3 business days after the contact |
| Medium | 3 business days from detection | 5 business days after the contact |
| Low | No contact. Include it in the weekly review. | Only if the same check repeats for three weeks. |

Business days exclude weekends. The clock starts when the row lands in `exceptions` or when a reconciliation line is flagged, whichever is earlier.

## Steps

1. Detection. `src/validate.py` writes `exceptions` and `dq_scorecard`. `src/reconcile.py` writes flagged lines and a root cause. Read `docs/detection_results.md` and `docs/reconciliation_results.md` before writing to anyone.
2. Confirm the file. Use `ingestion_log` and `file_manifest` for the file name, rows read, rows rejected, and received date. Do not ask a distributor to fix a week that was rejected for a date parse until you quote the reject reason.
3. Distributor contact. Send the template below to the distributor's data contact. One message per distributor per week. Attach the exception rows for that distributor, not the full extract.
4. Wait for the corrected file. Log the new received date. Rerun ingest, validate, and reconcile. Close the item only when the check is gone or the remaining variance is under 5% and the root cause is blank.
5. Internal escalation. If the SLA expires, notify Sales and Trade Finance with the same facts plus the days outstanding. IT joins only when the failure is a parser or a mapping table, not a missing week the distributor still owes.

Unknown root causes, including the four volume-shift weeks on this run, go to Sales as Medium. Do not tell the distributor the shift was injected. Tell them the week is outside 5% and ask for a resend of that week.

## Message template

Subject: Weekly sales file needs a correction, [distributor_id], week of [week]

Hello,

We loaded [file_name], received [received_date]. [row_count] rows failed check [check_name] ([severity]).

Week: [week]
Issue: [issue_description]
Root cause on the reconciliation, if flagged: [root_cause]

Please resend that week with one row per account and SKU, an ISO or agreed date, liters (or cases if your contract says cases), and item codes from the shared crosswalk. Reply within the SLA for this severity.

Thank you
