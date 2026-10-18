# MPN Tolkning

MPN Tolkning uses the Archer-prosess workstation, database workflow, and Excel
reports, with **CALR-ETdb added for CALR variants**. The running application is
based on Archer main commit `4fda67a43d8002fb2928d60211327b73943967fd`, checked
on 18 October 2026. It runs independently of any local Archer installation.

## Workflow

1. Import an Archer variant TSV and create the review workbook.
2. Review **With Artifacts** and mark unwanted searches with `X` in
   **Skip Database Search (X)**. **Artifacts Removed** provides the filtered view.
3. Reload the reviewed workbook and select evidence sources.
4. Run database searches. Pause, stop, resume incomplete work, and retry failed
   searches use the same workflow as the current Archer application.
5. Review patient Excel reports and embedded source screenshots. Locked files
   remain pending and can be saved later without repeating searches.

Browser sources are CALR-ETdb, COSMIC, OncoKB, Franklin, ClinVar, and MTBP.
Archer's bounded MTBP concurrency, exact ClinVar GRCh37 checks, COSMIC-ID-only
searches, focused Franklin captures, and Edge-announced debugging port are retained.

## CALR-ETdb

- Only CALR variants are sent to this source. Other genes are marked not applicable.
- The search submits only the `c.…` part of the imported variant's HGVS cDNA.
  Sample identifiers, full TSV rows, and transcript prefixes are not submitted.
- The current public search form supports nucleotide notation, protein notation,
  COSMIC ID and broad categories. It does **not expose genomic-position search**.
  Missing cDNA is therefore reported as an invalid query rather than guessed.
- The result must match the exact cDNA. The documented type-1 deletion alias
  requires a matching protein consequence.
- The result table and matching variant overview are captured in Edge. The detail
  page must display the verified cDNA as a complete token before its capture.
- Unreadable or missing images remain incomplete and can be recaptured. An
  unrecognized response or invalid notation is never treated as a negative result.
- Type and Class are database annotations, not automatic clinical classifications.

Source: [CALR-ETdb search](https://www.dsimb.inserm.fr/CALR-ET/php/search_page.php).
The public `c.1099_1150del` example was verified in Edge on 18 October 2026.

## Excel outputs

The review workbook has the same two-sheet layout, filters, frozen identifiers,
artifact colours, hidden technical columns, and compact evidence columns as Archer.
A **CALR-ETdb Evidence** column is added at the right.

Patient reports are named `<patient>_MPN_Tolkning_APP.xlsx` and contain **Oversikt**,
**Vedlegg**, **Data**, and one sheet per variant. CALR evidence and links appear in
Oversikt and the variant sheet. CALR screenshots follow the existing MTBP,
Franklin, ClinVar, OncoKB, and COSMIC image order. Manual patient comments,
variant comments, and HSMD text survive report regeneration.

Example workbooks use synthetic identifiers and a public CALR example; other
sources are shown as not searched.

## Installation and startup

Requires Windows, Python 3.12+, Microsoft Edge with local remote debugging
permitted, and organizational access to the selected databases.

```powershell
python -m pip install -r requirements-dev.lock
python -m pip install -e . --no-deps
mpn-tolkning
# or
python -m mpn_tolkning
```

Settings and isolated browser profiles remain under `%USERPROFILE%\.mpn-tolkning`.
Original MPN output-folder, selected-provider and delay settings are migrated when
loaded. Existing Windows Credential Manager entries remain readable. Passwords
are not stored in the JSON settings file.

Processed workbooks created by this version can be reopened with their evidence
and screenshot audits. Older MPN workbooks using the **All Variants** layout must
be recreated from their source TSV for the new Archer review layout.

## Development

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q
```

The active workstation is in `src/mpn_tolkning/workstation`; the earlier MPN
modules remain for compatibility. Upstream tests are retained in `tests/workstation`.
See [Archer synchronization notes](docs/archer-sync.md) for provenance and local changes.

This is an interpretation-support and research tool. Qualified laboratory personnel
must review identity matches, evidence captures, and reports before clinical use.
