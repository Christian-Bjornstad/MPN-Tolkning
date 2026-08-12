# MPN Tolkning — Application Design

**Status:** Approved for implementation

**Date:** 2026-08-12

**Repository:** `Christian-Bjornstad/MPN-Tolkning`

**Application package:** `mpn_tolkning`

## 1. Purpose

MPN Tolkning is a standalone Windows desktop workstation for reviewing Archer
Analysis TSV exports from a focused myeloproliferative neoplasm panel. It carries
forward the proven operational workflow of VPM Tolkning while adding dedicated
support for the classical MPN driver genes JAK2, CALR, and MPL.

The application connects local variant review, controlled database research,
verified screenshots, resumable audit records, and per-patient Excel reports. It
is an interpretation-support tool for qualified laboratory personnel. It does
not issue diagnoses or final clinical classifications.

## 2. Product decisions

- Build a new application and repository rather than renaming or forking the
  existing VPM Tolkning product in place.
- Reuse proven architectural patterns selectively, with no runtime dependency on
  the HTS repository.
- Retain all variants and original TSV columns. JAK2, CALR, and MPL receive
  specialized driver context; unexpected genes remain visible and reviewable.
- Preserve the full review-first workflow: TSV import, workbook review, selected
  evidence searches, resumable capture, and patient reports.
- Keep patient and sample identifiers local. External sites receive variant-only
  queries; MTBP receives application-generated pseudonyms.
- Prefer exact, verified evidence over broad or unverified search results.
- Fail closed on identity mismatches and incomplete required captures.

## 3. Scope

### 3.1 Included

- Archer TSV validation and normalization.
- MPN-specific driver and hotspot context for JAK2, CALR, and MPL.
- Configurable, MPN-relevant artifact rules.
- Review workbook export and reload with skip selections.
- Evidence collection from MTBP, Franklin, ClinVar, OncoKB, COSMIC, and
  CALR-ETdb.
- ClinGen Allele Registry identity support.
- Optional supplementary CIViC and VICC MetaKB lookups.
- Persistent, isolated Microsoft Edge profiles for browser providers.
- Verified screenshot capture and local evidence audit data.
- Pause, stop, resume, retry, and incomplete-search recovery.
- Per-patient Excel reports and final workbook reconciliation.
- Original application icon, polished README, CI, and GitHub Pages site.

### 3.2 Not included

- Automatic diagnosis, treatment recommendation, or final clinical
  classification.
- Sending patient names, DIT identifiers, or sample identifiers to public
  evidence providers.
- Silently discarding genes outside JAK2, CALR, and MPL.
- Reusing the unrelated broad HTS artifact list.
- Making live third-party browser tests mandatory in CI.
- Storing provider passwords in plain-text configuration files.

## 4. Technical architecture

The application uses Python 3.11 or newer, PyQt6, pandas, openpyxl, requests,
Pillow, reportlab, keyring, and direct Microsoft Edge control through the local
Chrome DevTools Protocol. The package is organized into small, testable units:

```text
src/mpn_tolkning/
├── core/        Variant models, stable identity, driver context, artifact rules
├── io/          Archer TSV validation and normalized import
├── gui/         PyQt6 shell, pages, workers, progress, and accessibility
├── providers/   One adapter per external database plus shared result contracts
├── services/    Queueing, browser control, audit persistence, settings, resume
├── reports/     Review workbook and patient workbook generation
└── assets/      Source SVG, PNG sizes, and Windows ICO
```

### 4.1 Import and normalized identity

The TSV reader validates a small required semantic schema while supporting
documented header aliases. At minimum it must resolve:

- sample or patient/run identifier;
- gene symbol;
- transcript-level HGVSc;
- allele frequency or VAF.

HGVSp, chromosome, position, reference, alternate, depth, COSMIC identifier, and
all remaining fields are retained when present. The reader preserves the exact
original row and creates a normalized `VariantRecord` for application logic.

Each variant receives a stable key built from the best exact identity available:

1. GRCh37 chromosome, position, reference, and alternate;
2. otherwise transcript accession plus normalized HGVSc;
3. otherwise gene plus HGVSc, with an explicit reduced-confidence warning.

Stable keys power review selections, evidence merging, resume behavior, and
report reconciliation. Sample identity is added only when a per-patient key is
required; it is never embedded in screenshot filenames.

### 4.2 MPN context engine

The context engine adds transparent, non-diagnostic annotations:

- **JAK2:** recognizes established driver/hotspot presentations such as V617F
  and exon 12 variants when the imported identity supports the match.
- **CALR:** identifies exon 9 frameshift candidates and displays CALR-ETdb type,
  class, category, mutation type, protein notation, and aliases after a verified
  database match.
- **MPL:** recognizes established hotspot presentations such as W515 variants
  when the imported identity supports the match.

The engine labels findings as context such as `driver`, `hotspot`,
`CALR type 1-like`, or `needs review`. It never converts context into a final AMP,
ACMG, WHO, or diagnostic conclusion.

Unexpected or weakly identified variants receive a visible warning rather than
being filtered automatically.

### 4.3 Artifact rules

The new application starts with only MPN-relevant, explicitly reviewed artifact
rules. Relevant JAK2 rules already used by the laboratory workflow may be ported,
including the known configurable intronic homopolymer observations, but the
unrelated HTS artifact catalogue is excluded.

Rules are editable in Settings and contain gene, HGVSc, optional maximum VAF, and
reason. Artifact status takes visual priority over driver highlighting. Every
rule application remains visible in the review table and workbook.

## 5. Provider design

All providers implement a shared contract that returns:

- provider name and query;
- normalized status;
- compact human-readable summary;
- source URL when safe to retain;
- expected and observed variant identity;
- identity-verification outcome;
- screenshot paths and capture validation;
- timestamp, diagnostics, and retryability;
- provider-specific structured metadata.

Provider errors remain isolated. A failure in one provider does not discard
completed evidence from other providers.

### 5.1 Required full providers

| Provider | Use | Identity and capture behavior |
| --- | --- | --- |
| CALR-ETdb | CALR subtype, class, category, mutation type, COSMIC ID, pathology, references | CALR only. Submit the `c.…` suffix of HGVSc. Verify returned nucleotide/protein identity and record known literature aliases. Capture the focused result/description. |
| MTBP | Pseudonymous one-variant interpretation report | Preserve the proven pseudonymized, one-variant workflow. Do not export personal report URLs. |
| Franklin | Somatic interpretation overview and evidence | Explicit somatic mode and hg19/GRCh37. Verify transcript or genomic identity before capture. |
| ClinVar | Variant record and submitted classifications | Require exact assembly and allele identity. Keep germline and somatic assertions clearly separated. |
| OncoKB | Variant overview and mutation effect/context | Verify gene and alteration identity; capture only relevant evidence sections. |
| COSMIC | Somatic occurrence and mutation context | Prefer the imported COSMIC/COSV identifier; resolve the canonical GRCh37 mutation page and respect licensing. |

CALR-ETdb accepts complete or partial cDNA notation. Some CALR variants have
multiple literature notations. For example, the database documents alternate
type 1 presentations. Such a result is accepted only when transcript/protein or
genomic evidence confirms equivalence; the alias is recorded explicitly.

### 5.2 Identity and supplementary sources

- **ClinGen Allele Registry** is an identity service, not a clinical evidence
  classifier. It supplies canonical allele identifiers and cross-transcript or
  cross-build representations when available.
- **CIViC** and **VICC MetaKB** are optional supplementary sources. They are
  disabled by default for screenshot reporting and included only when an exact,
  relevant cancer evidence match exists.
- Supplementary absence never overrides evidence from the required providers.

### 5.3 Search ordering

The queue runs serially by patient, then variant, then provider. For CALR report
presentation, the evidence order is:

1. CALR-ETdb
2. MTBP
3. Franklin
4. ClinVar
5. OncoKB
6. COSMIC

For JAK2, MPL, and other genes, the order is MTBP, Franklin, ClinVar, OncoKB,
and COSMIC. ClinGen, CIViC, and MetaKB appear as compact identity or supplementary
text/link evidence unless a focused screenshot adds material value.

## 6. Workflow and persistence

```mermaid
flowchart LR
    A["Archer TSV"] --> B["Validate and normalize"]
    B --> C["Add MPN driver context"]
    C --> D["Export review workbook"]
    D --> E["Human review and X selections"]
    E --> F["Reload reviewed workbook"]
    F --> G["Serial evidence queue"]
    G --> H["Persist each provider result"]
    H --> I["Update each patient report"]
    I --> J["Reconcile final workbook"]
```

- Invalid input stops before any external network request.
- Pause occurs at the next safe provider checkpoint.
- Stop retains all completed results and marks unfinished work resumable.
- Resume skips fully verified results and retries error, timeout, mismatch,
  partial-capture, and unverified legacy states.
- Audit JSON and screenshots are saved after every provider result.
- The patient workbook is updated after each patient completes.
- If Excel locks a workbook, the app retains evidence in memory, marks the save
  pending, and retries during reconciliation.
- Provider browser profiles are stored beneath
  `%USERPROFILE%\.mpn-tolkning\browser_profiles` and never committed.
- Non-secret settings are stored beneath `%USERPROFILE%\.mpn-tolkning`.
  Credentials use the operating-system credential store or authenticated browser
  sessions.

## 7. User interface

The approved direction is a guided, data-dense clinical workbench rather than a
visual clone of the HTS application.

### 7.1 Navigation

The persistent left navigation contains:

1. Import
2. Driver Review
3. Evidence
4. Reports
5. Settings

A four-stage progress strip keeps TSV validation, review, evidence, and reporting
visible. Provider readiness and sign-in state appear before a search begins.

### 7.2 Driver Review page

The primary table displays selection, sample, gene, HGVSc, protein/subtype, VAF,
and review state. Filtering supports sample, gene, HGVSc, protein change,
warnings, selected rows, and driver state.

Selecting a row opens a detail pane containing:

- exact transcript and genomic identity;
- protein change, VAF, depth, and driver context;
- the cDNA-only CALR query when relevant;
- identity warnings;
- per-provider readiness and completion state.

Driver context, human-review warnings, and excluded/artifact states use text and
icons in addition to color.

### 7.3 Visual system

- Primary dark surface: deep teal `#123C3C`.
- Interactive primary: teal `#0F766E`.
- Action/high-attention accent: warm amber `#D97706`.
- Main background: cool off-white `#F4F8F7`.
- Body typography: Segoe UI/system UI for offline Windows reliability.
- HGVS and exact identifiers: Consolas or another available system monospace.
- Motion is limited to 150–250 ms state transitions and is disabled or reduced
  when the operating system requests reduced motion.
- Controls provide visible focus states and at least WCAG AA text contrast.
- The supported desktop range starts at 1120×720 and is optimized for 1440×900;
  dense tables remain keyboard operable and do not depend on hover.

### 7.4 Icon

The approved Variant Lens mark contains a simplified DNA strand inside a white
magnifying lens on deep teal, with a warm amber handle. A source SVG generates
the required PNG sizes and multi-resolution Windows ICO. The mark must remain
recognizable at 16, 24, and 32 pixels.

## 8. Excel outputs

### 8.1 Review workbook

The workbook preserves all imported fields and adds compact application columns
for include/exclude decisions, artifact reasons, driver context, warnings,
database skip selection, and evidence summaries. It provides a full review sheet
and a corresponding filtered view without configured artifacts.

The application reloads user-edited `X` selections by stable run/variant identity
and detects ambiguous or stale matches instead of guessing.

### 8.2 Patient workbooks

Patient files are named `<DIT>_MPN_Tolkning.xlsx` and contain:

- **Oversikt:** JAK2/CALR/MPL findings, VAF, subtype or hotspot context, compact
  evidence summaries, and source links.
- **Vedlegg:** the local DIT identifier and space for manual additions.
- **One sheet per variant:** identity, compact linked evidence, plain captions,
  and verified screenshots in the defined provider order.

Sheet names follow the proven gene/protein/cDNA collision-safe naming scheme.
Reports state that evidence requires qualified human review.

## 9. Error handling and safeguards

| Condition | Required behavior |
| --- | --- |
| Missing required TSV semantics | Show the missing fields and stop before processing. |
| Reduced-confidence identity | Keep the row visible, warn the reviewer, and block providers that require unavailable exact identity. |
| Returned identity mismatch | Fail closed, show expected versus observed identity, and mark retryable. |
| Blank, truncated, or incomplete capture | Do not mark complete; retain diagnostics and queue recapture. |
| Provider unavailable or changed | Preserve the isolated error and continue other selected providers. |
| Authentication required | Mark the provider as needing sign-in and offer a visible manual sign-in session. |
| Search paused or stopped | Finish the safe checkpoint, persist progress, and expose resume state. |
| Workbook locked | Retain evidence, show a nonfatal warning, and retry the pending save. |
| Duplicate or ambiguous workbook identity | Stop reconciliation for the affected row and require human resolution. |

## 10. Testing strategy

Development follows test-first red/green/refactor cycles for logic and behavioral
changes.

### 10.1 Unit tests

- TSV header aliases, required semantics, duplicate headers, and malformed rows.
- HGVSc normalization, transcript/cDNA splitting, stable identity, and CALR alias
  handling.
- JAK2/CALR/MPL context rules and artifact precedence.
- Provider query construction and identity verification.
- Normalized evidence statuses, retryability, and screenshot validation.
- Settings, credential exclusion, and privacy-safe paths.
- Workbook formatting, export/reload identity, and patient sheet naming.

### 10.2 Integration and workflow tests

- Synthetic TSV → normalized variants → review workbook.
- Review workbook selections → deterministic evidence queue.
- Fake provider results → incremental audit and patient report updates.
- Pause, stop, resume, error retry, mismatch, and incomplete-capture recovery.
- Existing evidence merge without loss or accidental duplication.
- Workbook lock and final reconciliation behavior.

### 10.3 Provider and UI verification

- Saved provider HTML/JSON fixtures test selectors and parsing without live
  network dependency.
- Opt-in live smoke tests verify current provider behavior and never run by
  default in CI.
- Manual Windows QA covers Edge sign-in, Excel integration, keyboard navigation,
  visible focus, high-DPI icon rendering, 1120×720, and 1440×900.
- Synthetic demo data is used in screenshots, documentation, CI, and the public
  repository.

## 11. Repository and delivery

The public repository is `Christian-Bjornstad/MPN-Tolkning`, with `main` as the
default branch. It includes:

- source and tests;
- `pyproject.toml` with the `mpn-tolkning` console entry point;
- original Variant Lens SVG, PNG, and ICO assets;
- a polished README with synthetic screenshots and a clinical-use disclaimer;
- GitHub Actions on Windows for the deterministic test suite;
- a static GitHub Pages documentation/landing site;
- no real patient data, credentials, browser profiles, or evidence directories.

The first implementation target is version `0.1.0`. A release is created only
after the deterministic suite, UI verification, and provider smoke checklist are
complete.

## 12. Research basis

- [CALR-ETdb](https://www.dsimb.inserm.fr/CALR-ET/) is the dedicated CALR variant
  resource selected for this application. Its site documents cDNA notation,
  type 1-like/type 2-like grouping, classes A–E, mutation categories, COSMIC
  links, and literature references.
- The original CALR studies establish CALR as a major driver in JAK2/MPL-negative
  essential thrombocythemia and primary myelofibrosis:
  [Klampfl et al.](https://doi.org/10.1056/NEJMoa1311347) and
  [Nangalia et al.](https://doi.org/10.1056/NEJMoa1312542).
- [ClinGen Allele Registry](https://reg.genome.network/) supplies canonical
  allele identity and equivalent HGVS representations.
- [CIViC](https://civicdb.org/) and
  [VICC MetaKB](https://search.cancervariants.org/) provide optional harmonized
  cancer evidence context.
- [ClinVar](https://www.ncbi.nlm.nih.gov/clinvar/),
  [OncoKB](https://www.oncokb.org/), and
  [COSMIC](https://cancer.sanger.ac.uk/cosmic) remain supporting evidence sources
  subject to exact identity checks, provider terms, and qualified review.

## 13. Acceptance criteria

The first release is acceptable when:

1. A representative de-identified Archer MPN TSV imports without losing columns.
2. JAK2, CALR, and MPL variants receive transparent context and all other genes
   remain visible.
3. The review workbook round-trips selections by stable identity.
4. All six required providers can be selected and completed results resume
   without duplication.
5. CALR-ETdb receives only cDNA notation and accepts a result only after verified
   equivalence.
6. Patient identifiers remain local and screenshot names are privacy-safe.
7. Patient workbooks contain compact evidence, links, and verified captures in
   the defined order.
8. Provider failures, partial captures, and file locks remain recoverable.
9. The deterministic automated test suite passes on Windows.
10. Keyboard navigation, focus, contrast, supported window sizes, icon assets,
    README, CI, and GitHub Pages are verified before release.
