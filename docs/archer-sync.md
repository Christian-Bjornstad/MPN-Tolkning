# Archer baseline and MPN extension

Baseline repository: https://github.com/Christian-Bjornstad/Archer-prosess

Pinned main commit: `4fda67a43d8002fb2928d60211327b73943967fd` (18 October 2026).
The former local checkout was at `2b0a29d`; the source was fetched before import.

## Source structure

The upstream `src/archer_processor` tree is incorporated under
`src/mpn_tolkning/workstation`. Internal imports use that namespace. Visible
application/report branding and the configuration directory use MPN names.
The MPN entry point launches this workstation. No sibling repository or
unreleased remote branch is needed at runtime.

Upstream regression tests and synthetic fixtures are retained under
`tests/workstation`. Existing MPN modules and tests are preserved separately.
When updating the baseline, normalize imports/branding in upstream files first,
then review the following intentional extensions instead of silently replacing them.

## Intentional extensions

- `services/calr_et.py`: CALR-only browser form submission, exact result parsing,
  focused result/detail screenshots, image validation, cancellation, and audits.
- `services/browser_review.py`: CALR provider registration and dispatch.
- `services/settings.py`: CALR enabled by default and original MPN setting-name migration.
- `services/credentials.py`: separate MPN credential namespace with fallback to
  the original `mpn-tolkning:<provider>` credential names.
- `services/evidence_audit.py`: CALR identity and screenshot requirements on resume.
- `gui/app.py`: CALR source card, browser selection and public-access settings row.
- `reports/excel_report.py`: sixth evidence column in the Archer review layout.
- `reports/patient_excel.py`: CALR text/images and sixth source column in Oversikt.
- `reports/manual_fields.py`: patient comments survive both the upstream five-source
  and MPN six-source overview merge layouts.
- `reports/patient_pdf.py`: CALR image order for PDF consumers.
- Original `providers/calr_et.py`: shared CALR parser now selects the exact row,
  distinguishes unavailable pages from negative results, and recognizes rejected notation.

CALR annotations are kept as the source's Type/Class labels. Partial captures and
identity mismatches do not display those labels as completed evidence.

## Validation

The unmodified imported baseline passed all 255 upstream tests before extension.
Regression coverage includes cDNA-only submission, non-CALR exclusion, alias
verification, wrong/missing/blank captures, embedded workbook images, six-column
layout, manual comment retention, settings migration, audit restore, and
recapture when a saved screenshot disappears.

Live public-source verification used only a synthetic identifier and the public
CALR `c.1099_1150del` example. Edge returned `p.L367Tfs*46`, `Type 1-like`,
`Class A`, and `COSV57116546`. Both result and overview screenshots were validated
and embedded in an example patient workbook. The valid but absent
`c.1099_1151del` query was also checked in Edge and returned a captured negative
result. Its no-match page uses `#search` without `#tabl_result`, and both page
forms are covered by regression tests. A spreadsheet renderer was used to
inspect Oversikt, Vedlegg, Data and the CALR variant sheet. Other provider accounts
were not used for live submissions in this update; their imported regression tests run locally.

The CALR search form was inspected directly. It exposes cDNA/protein/COSMIC and
category fields, with no genomic-coordinate input. No genomic lookup was invented.

## Compatibility

The original MPN `All Variants` review layout is not loaded as a current Archer
review workbook. Reimport its source TSV to produce With Artifacts / Artifacts Removed.
Existing files are not overwritten by a migration. New-format review workbooks
restore selection, evidence, audits and screenshots through the Archer loader.
