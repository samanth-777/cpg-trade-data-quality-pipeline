# Process improvements

Five changes that would make this monitoring loop harder to fool and easier to run every week.

1. Stop treating a blank price as a pass. `state_bottle_cost` and `state_bottle_retail` are null on all 5,230,532 lines, so the bottles-times-retail check has nothing to compare. Require those fields in the source contract, or mark the check "not run" until they arrive. A zero mismatch count is not evidence that dollars tie to price.

2. Reject unmapped item codes at ingest. D07 and D08 put 3% of rows on codes that are not in `sku_crosswalk`. Those rows still land in `stg_feeds` and become 59,873 flagged reconciliation lines tagged Unmapped Code. A shared crosswalk, refreshed before the file is accepted, should quarantine the code the way a bad date is quarantined today. The distributor then fixes a reject file instead of a variance report.

3. Replace the file drop with a contract that carries its own clock. Two formats, three date styles, and a cases-versus-liters switch are all configuration today, which is why mixed dates and case conversion have to be rediscovered in reconciliation. An API or a single CSV contract, plus a received timestamp from the transfer rather than a manifest we write ourselves, would make the late-file check independent of the simulator.

4. Tag a uniform week shift on the line, not only in the detection report. Validation caught 745 of 749 injected events and missed all 4 volume distortions, because an 8 to 15 percent move on every line in a week still looks like a normal SKU. Reconciliation-stage detection now catches those 4 distributor weeks when the absolute week variance is over 5%. The line-level root cause is still Unknown on 9,040 flagged lines. Open one exception for the week and tag those lines, so the shift is not left unexplained.

5. Publish the scorecard on a schedule and retire the manual workbook pass for the first look. The Excel file is the right tool for a reviewer who wants SUMIFS and a 5,000 row sample. It is the wrong tool for the Monday check. Run `python run_all.py` on a schedule, post `dq_scorecard` and the high-severity exceptions, and open the workbook only when a distributor is outside the threshold. Pair that with the escalation clock in `docs/escalation_SOP.md` so a late file or a missing week has an owner the same day.
