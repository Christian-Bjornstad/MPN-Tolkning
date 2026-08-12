# MPN Tolkning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and publish a standalone Windows desktop workstation that turns Archer MPN TSV exports into a review-first, resumable JAK2/CALR/MPL evidence and patient-report workflow.

**Architecture:** A Python 3.11+ PyQt6 application separates normalized variant identity, MPN context, provider adapters, resumable audit state, reports, and UI workers behind explicit interfaces. Provider searches run serially and fail closed on identity or capture uncertainty; all patient identifiers and evidence artifacts remain local.

**Tech Stack:** Python 3.11+, PyQt6, pandas, openpyxl, requests, Beautiful Soup 4, websocket-client, Pillow, reportlab, keyring, pytest, pypdf, Microsoft Edge CDP, GitHub Actions, static GitHub Pages.

## Global Constraints

- Application package: `mpn_tolkning`; console entry point: `mpn-tolkning`.
- Initial version: `0.1.0`.
- Supported platform: Windows 10/11 with Microsoft Edge and Python 3.11 or newer.
- Default genomic context: GRCh37/hg19 where a provider exposes the choice.
- Required providers: CALR-ETdb, MTBP, Franklin, ClinVar, OncoKB, and COSMIC.
- Optional support sources: ClinGen Allele Registry, CIViC, and VICC MetaKB.
- Never send patient names, DIT identifiers, or sample identifiers to public providers.
- MTBP receives only application-generated pseudonyms.
- Never turn driver context into an automatic diagnosis or final clinical classification.
- Keep genes outside JAK2, CALR, and MPL visible.
- Use only MPN-relevant, explicitly reviewed artifact rules.
- Fail closed on returned-identity mismatch and incomplete required screenshots.
- Use synthetic/de-identified data in tests, screenshots, README, CI, and GitHub Pages.
- Every behavior change follows a red/green/refactor cycle and receives an atomic commit.

## File Map

```text
pyproject.toml                         Package metadata, dependencies, pytest config, CLI
README.md                              Installation, workflow, safeguards, screenshots
.github/workflows/test.yml             Deterministic Windows test job
.github/workflows/pages.yml            Static Pages deployment
site/index.html                        Public landing/documentation page
scripts/build_icons.py                 Deterministic SVG → PNG/ICO asset generation

src/mpn_tolkning/__init__.py           Version and package exports
src/mpn_tolkning/__main__.py           PyQt application entry point
src/mpn_tolkning/core/models.py        Domain records and normalized evidence types
src/mpn_tolkning/core/identity.py      HGVSc parsing and stable identity
src/mpn_tolkning/core/context.py       JAK2/CALR/MPL context annotations
src/mpn_tolkning/core/rules.py         Configurable MPN artifact rules
src/mpn_tolkning/io/tsv_reader.py      Archer validation and import
src/mpn_tolkning/services/settings.py  Non-secret settings persistence
src/mpn_tolkning/services/credentials.py OS credential-store access
src/mpn_tolkning/services/audit.py     Incremental evidence JSON persistence
src/mpn_tolkning/services/queue.py     Serial pause/stop/resume orchestration
src/mpn_tolkning/services/edge_cdp.py  Direct Edge DevTools transport
src/mpn_tolkning/services/capture.py   Required screenshot validation
src/mpn_tolkning/providers/base.py     Provider protocol and shared result contract
src/mpn_tolkning/providers/calr_et.py  CALR-ETdb cDNA lookup and result parsing
src/mpn_tolkning/providers/identity.py ClinGen/CIViC/MetaKB support lookups
src/mpn_tolkning/providers/browser.py  MTBP/Franklin/ClinVar/OncoKB/COSMIC browser flow
src/mpn_tolkning/reports/review.py     Review workbook export/reload
src/mpn_tolkning/reports/patient.py    Per-patient evidence workbook
src/mpn_tolkning/gui/workers.py        Background import/search/report workers
src/mpn_tolkning/gui/app.py            Guided workbench shell and pages
src/mpn_tolkning/assets/variant-lens.svg Approved source icon
src/mpn_tolkning/assets/*.png|*.ico     Generated application assets

tests/fixtures/sample_mpn_variants.tsv  Synthetic Archer-like input
tests/fixtures/calr_et_*.html            Synthetic provider responses
tests/test_*.py                         Unit and workflow regression tests
```

---

### Task 1: Package Foundation and Domain Contracts

**Files:**
- Create: `pyproject.toml`
- Create: `src/mpn_tolkning/__init__.py`
- Create: `src/mpn_tolkning/__main__.py`
- Create: `src/mpn_tolkning/core/__init__.py`
- Create: `src/mpn_tolkning/core/models.py`
- Create: `tests/test_models.py`
- Create: `tests/test_entrypoint.py`

**Interfaces:**
- Produces: `VariantRecord`, `DriverContext`, `EvidenceStatus`, `IdentityCheck`, `EvidenceResult`, and `ProcessingResult` dataclasses/enums.
- Produces: `mpn_tolkning.__version__ == "0.1.0"` and `mpn_tolkning.__main__.main()`.

- [ ] **Step 1: Write failing domain-contract tests**

```python
# tests/test_models.py
from mpn_tolkning.core.models import EvidenceResult, EvidenceStatus, VariantRecord


def test_variant_record_preserves_original_fields_and_exposes_vaf():
    row = {"Sample": "DIT-1001", "Gene": "CALR", "HGVSc": "NM_004343.4:c.1099_1150del", "AF": "41.2"}
    variant = VariantRecord(sample="DIT-1001", gene="CALR", hgvsc=row["HGVSc"], vaf=41.2, original=row)
    assert variant.original == row
    assert variant.vaf == 41.2


def test_evidence_result_marks_retryable_failure_explicitly():
    result = EvidenceResult(provider="CALR-ETdb", status=EvidenceStatus.IDENTITY_MISMATCH, summary="Returned another allele", retryable=True)
    assert result.is_complete is False
    assert result.retryable is True
```

```python
# tests/test_entrypoint.py
import mpn_tolkning


def test_package_version_starts_at_0_1_0():
    assert mpn_tolkning.__version__ == "0.1.0"
```

- [ ] **Step 2: Run the tests and confirm the package is missing**

Run: `py -3.11 -m pytest tests/test_models.py tests/test_entrypoint.py -v`

Expected: collection fails with `ModuleNotFoundError: No module named 'mpn_tolkning'`.

- [ ] **Step 3: Add package metadata and minimal domain types**

```toml
# pyproject.toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "mpn-tolkning"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "PyQt6>=6.7", "beautifulsoup4>=4.12", "keyring>=25.6",
  "openpyxl>=3.1", "pandas>=2.2", "Pillow>=10.0",
  "reportlab>=4.2", "requests>=2.32", "websocket-client>=1.8"
]

[project.optional-dependencies]
dev = ["pypdf>=5.0", "pytest>=8.2"]

[project.scripts]
mpn-tolkning = "mpn_tolkning.__main__:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
mpn_tolkning = ["assets/*.svg", "assets/*.png", "assets/*.ico"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

```python
# src/mpn_tolkning/core/models.py
from __future__ import annotations
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class EvidenceStatus(StrEnum):
    FOUND = "found"
    NOT_FOUND = "not_found"
    INVALID_QUERY = "invalid_query"
    IDENTITY_MISMATCH = "identity_mismatch"
    INCOMPLETE_CAPTURE = "incomplete_capture"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class VariantRecord:
    sample: str
    gene: str
    hgvsc: str
    vaf: float | None
    hgvsp: str = ""
    chromosome: str = ""
    position: int | None = None
    reference: str = ""
    alternate: str = ""
    depth: int | None = None
    cosmic_id: str = ""
    original: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DriverContext:
    label: str = ""
    detail: str = ""
    needs_review: bool = False


@dataclass(frozen=True)
class EvidenceResult:
    provider: str
    status: EvidenceStatus
    summary: str
    url: str = ""
    retryable: bool = False
    expected_identity: str = ""
    observed_identity: str = ""
    screenshots: tuple[Path, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_complete(self) -> bool:
        return self.status in {EvidenceStatus.FOUND, EvidenceStatus.NOT_FOUND}


@dataclass(frozen=True)
class IdentityCheck:
    expected: str
    observed: str
    matched: bool
    reason: str = ""


@dataclass(frozen=True)
class ProcessingResult:
    variants: tuple[VariantRecord, ...]
    warnings: tuple[str, ...] = ()
```

- [ ] **Step 4: Run the focused tests**

Run: `py -3.11 -m pytest tests/test_models.py tests/test_entrypoint.py -v`

Expected: all tests pass.

- [ ] **Step 5: Install the editable development package and run the CLI import check**

Run: `py -3.11 -m pip install -e ".[dev]"`

Run: `py -3.11 -c "import mpn_tolkning; print(mpn_tolkning.__version__)"`

Expected: prints `0.1.0`.

- [ ] **Step 6: Commit the foundation**

```powershell
git add pyproject.toml src/mpn_tolkning tests/test_models.py tests/test_entrypoint.py
git commit -m "feat: establish MPN Tolkning domain contracts"
```

---

### Task 2: TSV Import and Exact Variant Identity

**Files:**
- Create: `src/mpn_tolkning/core/identity.py`
- Create: `src/mpn_tolkning/io/__init__.py`
- Create: `src/mpn_tolkning/io/tsv_reader.py`
- Create: `tests/fixtures/sample_mpn_variants.tsv`
- Create: `tests/conftest.py`
- Create: `tests/test_identity.py`
- Create: `tests/test_tsv_reader.py`

**Interfaces:**
- Consumes: `VariantRecord` from Task 1.
- Produces: `split_hgvsc(value: str) -> tuple[str, str]`, `stable_variant_key(variant: VariantRecord) -> str`, `ValidationResult`, and `ArcherTsvReader.read(path: Path) -> list[VariantRecord]`.

- [ ] **Step 1: Add synthetic TSV and failing identity/import tests**

```text
# tests/fixtures/sample_mpn_variants.tsv
Sample	Gene	HGVSc	HGVSp	AF	AO	DP	Chromosome	Position	Reference	Alternate	COSMICID
DIT-1001	CALR	NM_004343.4:c.1099_1150del	p.Lys367ArgfsTer51	41.2	759	1842	19	13054615	AAG...	A	COSV57165839
DIT-1002	JAK2	NM_004972.4:c.1849G>T	p.Val617Phe	18.6	212	1140	9	5073770	G	T	COSV67569040
DIT-1003	MPL	NM_005373.2:c.1544G>T	p.Trp515Leu	7.1	88	1239	1	43815009	G	T	""
```

```python
# tests/test_identity.py
from mpn_tolkning.core.identity import split_hgvsc, stable_variant_key
from mpn_tolkning.core.models import VariantRecord


def test_split_hgvsc_returns_transcript_and_cdna_only_query():
    assert split_hgvsc("NM_004343.4:c.1099_1150del") == ("NM_004343.4", "c.1099_1150del")


def test_stable_key_prefers_grch37_allele():
    variant = VariantRecord("DIT-1", "JAK2", "NM_004972.4:c.1849G>T", 18.6, chromosome="9", position=5073770, reference="G", alternate="T")
    assert stable_variant_key(variant) == "grch37:9:5073770:G:T"
```

```python
# tests/test_tsv_reader.py
from pathlib import Path
import pytest
from mpn_tolkning.io.tsv_reader import ArcherTsvReader, TsvValidationError


def test_reader_retains_all_original_columns():
    variants = ArcherTsvReader().read(Path("tests/fixtures/sample_mpn_variants.tsv"))
    assert [v.gene for v in variants] == ["CALR", "JAK2", "MPL"]
    assert variants[0].original["AO"] == 759


def test_reader_reports_missing_semantic_fields(tmp_path):
    path = tmp_path / "bad.tsv"
    path.write_text("Sample\tGene\nDIT-1\tCALR\n", encoding="utf-8")
    with pytest.raises(TsvValidationError, match="HGVSc.*AF/VAF"):
        ArcherTsvReader().read(path)
```

```python
# tests/conftest.py
from pathlib import Path
import pytest
from mpn_tolkning.io.tsv_reader import ArcherTsvReader


@pytest.fixture
def sample_variants():
    return ArcherTsvReader().read(Path("tests/fixtures/sample_mpn_variants.tsv"))


@pytest.fixture
def calr_variant(sample_variants):
    return next(variant for variant in sample_variants if variant.gene == "CALR")


@pytest.fixture
def jak2_variant(sample_variants):
    return next(variant for variant in sample_variants if variant.gene == "JAK2")


@pytest.fixture
def fixture_html():
    return lambda name: (Path("tests/fixtures") / name).read_text(encoding="utf-8")
```

- [ ] **Step 2: Verify the new tests fail for missing modules**

Run: `py -3.11 -m pytest tests/test_identity.py tests/test_tsv_reader.py -v`

Expected: collection fails because `identity.py` and `tsv_reader.py` do not exist.

- [ ] **Step 3: Implement normalization and alias-aware TSV reading**

```python
# src/mpn_tolkning/core/identity.py
def split_hgvsc(value: str) -> tuple[str, str]:
    cleaned = value.strip()
    if ":" not in cleaned:
        return "", cleaned
    transcript, cdna = cleaned.rsplit(":", 1)
    return transcript, cdna


def stable_variant_key(variant: VariantRecord) -> str:
    if variant.chromosome and variant.position and variant.reference and variant.alternate:
        chrom = variant.chromosome.removeprefix("chr")
        return f"grch37:{chrom}:{variant.position}:{variant.reference.upper()}:{variant.alternate.upper()}"
    transcript, cdna = split_hgvsc(variant.hgvsc)
    if transcript:
        return f"transcript:{transcript}:{cdna}"
    return f"reduced:{variant.gene.upper()}:{cdna}"
```

Implement `ArcherTsvReader` with semantic aliases:

```python
ALIASES = {
    "sample": ("Sample", "Sample ID", "DIT"),
    "gene": ("Gene", "Symbol", "GeneName"),
    "hgvsc": ("HGVSc", "HGVS.c", "Coding Change"),
    "vaf": ("AF", "VAF", "Allele Frequency"),
}
```

Use `pandas.read_csv(path, sep="\t")`, detect duplicate headers from the raw
header line before pandas renames them, resolve each required semantic field,
convert numeric blanks to `None`, uppercase gene/alleles, and pass every row from
`DataFrame.to_dict(orient="records")` into `VariantRecord.original`.

- [ ] **Step 4: Run focused tests and then all tests**

Run: `py -3.11 -m pytest tests/test_identity.py tests/test_tsv_reader.py -v`

Run: `py -3.11 -m pytest -q`

Expected: all tests pass.

- [ ] **Step 5: Commit import and identity**

```powershell
git add src/mpn_tolkning/core/identity.py src/mpn_tolkning/io tests/conftest.py tests/fixtures/sample_mpn_variants.tsv tests/test_identity.py tests/test_tsv_reader.py
git commit -m "feat: normalize Archer MPN variants"
```

---

### Task 3: MPN Driver Context and Artifact Rules

**Files:**
- Create: `src/mpn_tolkning/core/context.py`
- Create: `src/mpn_tolkning/core/rules.py`
- Create: `tests/test_context.py`
- Create: `tests/test_rules.py`

**Interfaces:**
- Consumes: `VariantRecord`, `DriverContext`, and `split_hgvsc`.
- Produces: `classify_driver_context(variant: VariantRecord) -> DriverContext`, `ArtifactRule`, and `evaluate_artifact(variant, rules) -> str`.

- [ ] **Step 1: Write failing driver-context tests**

```python
# tests/test_context.py
from mpn_tolkning.core.context import classify_driver_context
from mpn_tolkning.core.models import VariantRecord


def test_jak2_v617f_is_labeled_as_driver_context():
    context = classify_driver_context(VariantRecord("DIT-1", "JAK2", "NM_004972.4:c.1849G>T", 18.6, hgvsp="p.Val617Phe"))
    assert (context.label, context.needs_review) == ("JAK2 V617F driver", False)


def test_calr_exon9_frameshift_is_candidate_until_database_verification():
    context = classify_driver_context(VariantRecord("DIT-1", "CALR", "NM_004343.4:c.1099_1150del", 41.2, hgvsp="p.Lys367ArgfsTer51"))
    assert context.label == "CALR exon 9 frameshift candidate"
    assert context.needs_review is True


def test_non_triad_gene_remains_visible_without_driver_label():
    context = classify_driver_context(VariantRecord("DIT-1", "TET2", "NM_001127208.2:c.3954+1G>A", 12.0))
    assert context.label == ""
```

```python
# tests/test_rules.py
from mpn_tolkning.core.models import VariantRecord
from mpn_tolkning.core.rules import ArtifactRule, evaluate_artifact


def test_mpn_artifact_rule_matches_gene_cdna_and_vaf_threshold():
    rules = [ArtifactRule("JAK2", "c.3291+16dup", 5.0, "Intronic homopolymer observation")]
    variant = VariantRecord("DIT-1", "JAK2", "NM_004972.4:c.3291+16dup", 2.0)
    assert evaluate_artifact(variant, rules) == "Intronic homopolymer observation"
```

- [ ] **Step 2: Run tests and confirm missing modules**

Run: `py -3.11 -m pytest tests/test_context.py tests/test_rules.py -v`

Expected: collection fails for missing `context` and `rules` modules.

- [ ] **Step 3: Implement transparent context and exact artifact precedence**

Implement context matching on normalized gene plus exact HGVSc/HGVSp patterns.
Recognize JAK2 `c.1849G>T`/`p.Val617Phe`, CALR frameshift candidates, and MPL
codon 515 substitutions. Return `needs_review=True` for reduced identity and CALR
subtype candidates until CALR-ETdb confirms the result.

```python
def classify_driver_context(variant: VariantRecord) -> DriverContext:
    gene = variant.gene.upper()
    _, cdna = split_hgvsc(variant.hgvsc)
    protein = variant.hgvsp.replace("Ter", "*")
    if gene == "JAK2" and (cdna == "c.1849G>T" or protein in {"p.Val617Phe", "p.V617F"}):
        return DriverContext("JAK2 V617F driver")
    if gene == "CALR" and ("fs" in protein or "del" in cdna or "ins" in cdna):
        return DriverContext("CALR exon 9 frameshift candidate", needs_review=True)
    if gene == "MPL" and ("Trp515" in protein or "W515" in protein):
        return DriverContext("MPL W515 hotspot")
    return DriverContext()
```

```python
@dataclass(frozen=True)
class ArtifactRule:
    gene: str
    cdna: str
    max_vaf: float | None
    reason: str
```

`evaluate_artifact` must compare uppercase gene and cDNA-only notation and apply
the VAF ceiling only when one is defined. It returns an empty string when no rule
matches, keeping rule reasons visible rather than returning a boolean.

- [ ] **Step 4: Run context/rule and full tests**

Run: `py -3.11 -m pytest tests/test_context.py tests/test_rules.py -v`

Run: `py -3.11 -m pytest -q`

Expected: all tests pass.

- [ ] **Step 5: Commit MPN context**

```powershell
git add src/mpn_tolkning/core/context.py src/mpn_tolkning/core/rules.py tests/test_context.py tests/test_rules.py
git commit -m "feat: add transparent MPN driver context"
```

---

### Task 4: Settings and Credential Isolation

**Files:**
- Create: `src/mpn_tolkning/services/__init__.py`
- Create: `src/mpn_tolkning/services/settings.py`
- Create: `src/mpn_tolkning/services/credentials.py`
- Create: `tests/test_settings.py`
- Create: `tests/test_credentials.py`

**Interfaces:**
- Produces: `AppSettings.load(path: Path | None = None)`, `AppSettings.save(path=None)`, `CredentialStore.get(provider)`, and `CredentialStore.set(provider, username, password)`.

- [ ] **Step 1: Write failing privacy tests**

```python
# tests/test_settings.py
import json
from mpn_tolkning.services.settings import AppSettings


def test_settings_default_to_independent_mpn_directory(monkeypatch, tmp_path):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert AppSettings.default_path() == tmp_path / ".mpn-tolkning" / "config.json"


def test_saved_settings_never_contain_passwords(tmp_path):
    path = tmp_path / "config.json"
    settings = AppSettings(cosmic_email="lab@example.org")
    settings.save(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["cosmic_email"] == "lab@example.org"
    assert all("password" not in key.lower() for key in payload)
```

```python
# tests/test_credentials.py
from mpn_tolkning.services.credentials import CredentialStore


def test_credential_service_uses_provider_scoped_keyring(monkeypatch):
    calls = []
    monkeypatch.setattr("keyring.set_password", lambda service, user, password: calls.append((service, user, password)))
    CredentialStore().set("COSMIC", "lab@example.org", "secret-value")
    assert calls == [("mpn-tolkning:COSMIC", "lab@example.org", "secret-value")]
```

- [ ] **Step 2: Verify tests fail for missing services**

Run: `py -3.11 -m pytest tests/test_settings.py tests/test_credentials.py -v`

Expected: collection fails for missing modules.

- [ ] **Step 3: Implement typed JSON settings and keyring adapter**

Use a dataclass whose serialized fields contain provider usernames/emails,
timeouts, request-delay bounds, selected providers, browser-background mode,
artifact rules, output directory, and reference build. Exclude all attributes
whose name ends in `_password` and write JSON atomically through a sibling `.tmp`
file followed by `Path.replace`.

Implement `CredentialStore` with service names `mpn-tolkning:<PROVIDER>` and no
fallback plain-text storage.

```python
@dataclass
class AppSettings:
    selected_providers: list[str] = field(default_factory=lambda: ["CALR-ETdb", "MTBP", "Franklin", "ClinVar", "OncoKB", "COSMIC"])
    browser_background: bool = True
    request_delay_min_ms: int = 10_000
    request_delay_max_ms: int = 20_000
    cosmic_email: str = ""

    @staticmethod
    def default_path() -> Path:
        profile = Path(os.environ.get("USERPROFILE") or Path.home())
        return profile / ".mpn-tolkning" / "config.json"


class CredentialStore:
    def set(self, provider: str, username: str, password: str) -> None:
        keyring.set_password(f"mpn-tolkning:{provider}", username, password)
```

- [ ] **Step 4: Run privacy tests and full suite**

Run: `py -3.11 -m pytest tests/test_settings.py tests/test_credentials.py -v`

Run: `py -3.11 -m pytest -q`

Expected: all tests pass.

- [ ] **Step 5: Commit settings isolation**

```powershell
git add src/mpn_tolkning/services tests/test_settings.py tests/test_credentials.py
git commit -m "feat: isolate MPN settings and credentials"
```

---

### Task 5: Review Workbook Export and Round Trip

**Files:**
- Create: `src/mpn_tolkning/reports/__init__.py`
- Create: `src/mpn_tolkning/reports/review.py`
- Create: `tests/test_review_workbook.py`

**Interfaces:**
- Consumes: `VariantRecord`, driver context, artifact reason, and stable keys.
- Produces: `write_review_workbook(path, variants, contexts, artifact_reasons) -> Path` and `load_skip_keys(path) -> set[str]`.

- [ ] **Step 1: Write failing workbook round-trip tests**

```python
# tests/test_review_workbook.py
from openpyxl import load_workbook
from mpn_tolkning.reports.review import load_skip_keys, write_review_workbook


def test_review_workbook_preserves_rows_and_adds_skip_control(tmp_path, sample_variants):
    path = write_review_workbook(tmp_path / "review.xlsx", sample_variants, {}, {})
    workbook = load_workbook(path)
    assert workbook.sheetnames == ["All Variants", "Artifacts Removed"]
    headers = [cell.value for cell in workbook["All Variants"][1]]
    assert "Skip Database Search (X)" in headers
    assert "Stable Variant Key" in headers


def test_skip_selection_round_trips_by_sample_and_stable_key(tmp_path, sample_variants):
    path = write_review_workbook(tmp_path / "review.xlsx", sample_variants, {}, {})
    workbook = load_workbook(path)
    sheet = workbook["All Variants"]
    skip_col = next(cell.column for cell in sheet[1] if cell.value == "Skip Database Search (X)")
    sheet.cell(2, skip_col, "X")
    workbook.save(path)
    assert len(load_skip_keys(path)) == 1
```

- [ ] **Step 2: Run tests and confirm missing report module**

Run: `py -3.11 -m pytest tests/test_review_workbook.py -v`

Expected: collection fails for missing `reports.review`.

- [ ] **Step 3: Implement deterministic workbook layout**

Write `All Variants` and `Artifacts Removed`, freeze identifier columns, retain
all original headers, append application columns, hide `Stable Variant Key`, and
apply artifact > driver > warning fill precedence. `load_skip_keys` must require
sample, stable key, and skip headers; normalize `X` case-insensitively; and raise
`ReviewWorkbookError` for duplicate or ambiguous identities.

```python
APP_COLUMNS = (
    "Stable Variant Key", "Driver Context", "Artifact Reason", "Review Warning",
    "Skip Database Search (X)", "CALR-ETdb", "MTBP", "Franklin", "ClinVar", "OncoKB", "COSMIC",
)


def write_review_workbook(path: Path, variants: list[VariantRecord], contexts: dict[str, DriverContext], artifact_reasons: dict[str, str]) -> Path:
    workbook = Workbook()
    all_variants = workbook.active
    all_variants.title = "All Variants"
    artifacts_removed = workbook.create_sheet("Artifacts Removed")
    # Write retained original columns followed by APP_COLUMNS in stable order.
    return _save_atomically(workbook, path)
```

- [ ] **Step 4: Run workbook and full tests**

Run: `py -3.11 -m pytest tests/test_review_workbook.py -v`

Run: `py -3.11 -m pytest -q`

Expected: all tests pass.

- [ ] **Step 5: Commit review workflow**

```powershell
git add src/mpn_tolkning/reports tests/test_review_workbook.py
git commit -m "feat: add MPN review workbook round trip"
```

---

### Task 6: Provider Contract, Audit Store, and Resumable Queue

**Files:**
- Create: `src/mpn_tolkning/providers/__init__.py`
- Create: `src/mpn_tolkning/providers/base.py`
- Create: `src/mpn_tolkning/services/audit.py`
- Create: `src/mpn_tolkning/services/queue.py`
- Create: `tests/test_provider_contract.py`
- Create: `tests/test_audit.py`
- Create: `tests/test_queue.py`

**Interfaces:**
- Produces: `SearchContext`, `Provider.search(variant, context) -> EvidenceResult`, `AuditStore`, `PauseControl`, `EvidenceQueue.run(...)`, and `EvidenceQueue.resume_pending(...)`.

- [ ] **Step 1: Write failing persistence and queue tests**

```python
# tests/test_provider_contract.py
from mpn_tolkning.providers.base import SearchContext


def test_search_context_carries_exact_cdna_and_build():
    context = SearchContext("grch37:19:13054615:AA:A", "NM_004343.4", "c.1099_1150del")
    assert context.cdna == "c.1099_1150del"
    assert context.build == "GRCh37"
```

```python
# tests/test_queue.py
from mpn_tolkning.core.models import EvidenceResult, EvidenceStatus
from mpn_tolkning.services.queue import EvidenceQueue, PauseControl


class FakeProvider:
    name = "Fake"
    def search(self, variant, context):
        return EvidenceResult("Fake", EvidenceStatus.FOUND, f"found {variant.gene}")


def test_queue_runs_patient_variant_provider_order_and_saves_each_result(sample_variants, tmp_path):
    saved = []
    queue = EvidenceQueue([FakeProvider()], audit_callback=lambda key, result: saved.append((key, result.provider)))
    results = queue.run(sample_variants, skip_keys=set(), pause=PauseControl())
    assert len(results) == len(sample_variants)
    assert len(saved) == len(sample_variants)
```

```python
# tests/test_audit.py
from mpn_tolkning.core.models import EvidenceResult, EvidenceStatus
from mpn_tolkning.services.audit import AuditStore


def test_audit_filename_contains_hash_not_sample_identifier(tmp_path):
    store = AuditStore(tmp_path)
    path = store.save("DIT-1001|grch37:9:5073770:G:T", EvidenceResult("ClinVar", EvidenceStatus.FOUND, "match"))
    assert "DIT-1001" not in path.name
    assert path.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run tests and confirm missing provider/queue modules**

Run: `py -3.11 -m pytest tests/test_provider_contract.py tests/test_audit.py tests/test_queue.py -v`

Expected: collection fails for missing modules.

- [ ] **Step 3: Implement shared protocol and atomic audit storage**

```python
from dataclasses import dataclass
from typing import Protocol
from mpn_tolkning.core.models import EvidenceResult, VariantRecord


@dataclass(frozen=True)
class SearchContext:
    stable_key: str
    transcript: str
    cdna: str
    build: str = "GRCh37"


class Provider(Protocol):
    name: str
    def search(self, variant: VariantRecord, context: SearchContext) -> EvidenceResult: ...
```

Hash audit filenames with SHA-256 of the per-patient stable key, serialize enums
and paths explicitly, write atomically, and maintain an in-memory index loaded by
one directory scan. Treat `FOUND` and `NOT_FOUND` as complete; keep errors,
timeouts, mismatches, cancelled states, and incomplete captures pending.

`EvidenceQueue.resume_pending(variants, existing_results)` returns a merged result
collection containing both the prior complete results and the newly retried
results, with one final result per stable-key/provider pair.

`PauseControl` uses `threading.Event`: `request_pause`, `resume`, `request_stop`,
and `checkpoint`. `EvidenceQueue` groups by sample, processes providers in the
supplied order, checks pause/stop between providers, and calls the audit callback
immediately after every result.

- [ ] **Step 4: Run queue/audit tests and full suite**

Run: `py -3.11 -m pytest tests/test_provider_contract.py tests/test_audit.py tests/test_queue.py -v`

Run: `py -3.11 -m pytest -q`

Expected: all tests pass.

- [ ] **Step 5: Commit resumable orchestration**

```powershell
git add src/mpn_tolkning/providers src/mpn_tolkning/services/audit.py src/mpn_tolkning/services/queue.py tests/test_provider_contract.py tests/test_audit.py tests/test_queue.py
git commit -m "feat: add resumable evidence orchestration"
```

---

### Task 7: CALR-ETdb and Identity Support Providers

**Files:**
- Create: `src/mpn_tolkning/providers/calr_et.py`
- Create: `src/mpn_tolkning/providers/identity.py`
- Create: `tests/fixtures/calr_et_type1.html`
- Create: `tests/fixtures/calr_et_not_found.html`
- Create: `tests/test_calr_et.py`
- Create: `tests/test_identity_providers.py`

**Interfaces:**
- Consumes: provider contract, `VariantRecord`, `split_hgvsc`, and `EvidenceResult`.
- Produces: `CalrEtProvider`, `ClinGenIdentityProvider`, `CivicProvider`, and `MetaKbProvider`.

- [ ] **Step 1: Save synthetic fixtures and write failing CALR query tests**

```html
<!-- tests/fixtures/calr_et_type1.html -->
<table id="results">
  <tr><th>Nucleotide notation</th><th>Protein notation</th><th>Type</th><th>Class</th><th>Mutation</th><th>COSMIC</th></tr>
  <tr><td><a href="variant.php?id=type1">c.1099_1150del</a></td><td>p.K367Rfs*51</td><td>Type 1-like</td><td>Class A</td><td>Deletion</td><td>COSV57165839</td></tr>
</table>
<section id="description"><p>Category: Type 1</p><p>Pathology: Essential thrombocythemia</p><a href="https://pubmed.ncbi.nlm.nih.gov/24325356/">PMID 24325356</a></section>
```

```html
<!-- tests/fixtures/calr_et_not_found.html -->
<section id="results"><h2>Results no found</h2></section>
```

```python
# tests/test_calr_et.py
from mpn_tolkning.providers.calr_et import CalrEtProvider


def test_calr_provider_posts_cdna_without_transcript(monkeypatch, calr_variant, fixture_html):
    posted = {}
    provider = CalrEtProvider()
    monkeypatch.setattr(provider, "_csrf_token", lambda: "csrf")
    monkeypatch.setattr(provider, "_post", lambda data: posted.update(data) or fixture_html("calr_et_type1.html"))
    result = provider.search(calr_variant, context=None)
    assert posted["nucleotid"] == "c.1099_1150del"
    assert "NM_004343.4" not in posted["nucleotid"]
    assert result.metadata["type"] == "Type 1-like"


def test_calr_provider_skips_non_calr_gene(jak2_variant):
    result = CalrEtProvider().search(jak2_variant, context=None)
    assert result.status.value == "invalid_query"


def test_alias_requires_protein_or_genomic_equivalence(calr_variant, fixture_html):
    result = CalrEtProvider().parse_result(fixture_html("calr_et_type1.html"), calr_variant)
    assert result.metadata["submitted_cdna"] == "c.1099_1150del"
    assert result.metadata["alias_verified"] is True
```

```python
# tests/test_identity_providers.py
from mpn_tolkning.providers.identity import ClinGenIdentityProvider


def test_clingen_lookup_uses_transcript_hgvsc_and_returns_caid(monkeypatch, calr_variant):
    provider = ClinGenIdentityProvider()
    monkeypatch.setattr(provider, "_get_json", lambda hgvsc: {"@id": "http://reg.genome.network/allele/CA123", "hgvs": [hgvsc]})
    result = provider.search(calr_variant, context=None)
    assert result.metadata["caid"] == "CA123"
    assert result.expected_identity == calr_variant.hgvsc
```

- [ ] **Step 2: Run provider tests and confirm modules are missing**

Run: `py -3.11 -m pytest tests/test_calr_et.py tests/test_identity_providers.py -v`

Expected: collection fails for missing provider modules.

- [ ] **Step 3: Implement CALR-ET session/query/parser**

Use `requests.Session` to GET `php/search_page.php`, parse the hidden CSRF token,
and POST this exact form shape:

```python
{"csrf_token": token, "nucleotid": cdna, "envoie1": "Submit"}
```

Parse the result with Beautiful Soup into nucleotide notation, protein notation,
type, class, mutation type, category, COSV identifier, pathology, and references.
Return `NOT_FOUND` for the documented empty result. Accept exact cDNA immediately;
accept a documented alias only when protein or genomic identity confirms
equivalence; otherwise return `IDENTITY_MISMATCH`. Persist the CALR query and the
observed alias in metadata.

- [ ] **Step 4: Implement read-only identity/support clients**

ClinGen consumes transcript HGVSc and returns CAid/equivalent HGVS metadata.
CIViC and MetaKB return supplementary `FOUND` only for exact gene/alteration
matches and otherwise `NOT_FOUND`. Set these providers disabled by default in
settings. Use dependency-injected `requests.Session` so tests never call live
services.

```python
class ClinGenIdentityProvider:
    name = "ClinGen Allele Registry"
    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()
    def search(self, variant: VariantRecord, context: SearchContext | None) -> EvidenceResult:
        return _format_clingen_identity(variant, self._get_json(variant.hgvsc))


class CivicProvider:
    name = "CIViC"


class MetaKbProvider:
    name = "VICC MetaKB"
```

- [ ] **Step 5: Run focused and full tests**

Run: `py -3.11 -m pytest tests/test_calr_et.py tests/test_identity_providers.py -v`

Run: `py -3.11 -m pytest -q`

Expected: all tests pass.

- [ ] **Step 6: Commit MPN-specific providers**

```powershell
git add src/mpn_tolkning/providers/calr_et.py src/mpn_tolkning/providers/identity.py tests/fixtures/calr_et_*.html tests/test_calr_et.py tests/test_identity_providers.py
git commit -m "feat: add verified CALR-ET evidence lookup"
```

---

### Task 8: Edge CDP and the Five Existing Evidence Providers

**Files:**
- Create: `src/mpn_tolkning/services/edge_cdp.py`
- Create: `src/mpn_tolkning/services/capture.py`
- Create: `src/mpn_tolkning/providers/browser.py`
- Modify: `src/mpn_tolkning/providers/calr_et.py`
- Create: `tests/test_edge_cdp.py`
- Create: `tests/test_capture.py`
- Create: `tests/test_browser_providers.py`

**Interfaces:**
- Consumes: settings, provider contract, stable identity, queue pause callbacks.
- Produces: `EdgeCdpSession`, `validate_capture(path)`, and provider classes `MtbpProvider`, `FranklinProvider`, `ClinVarProvider`, `OncoKbProvider`, `CosmicProvider`.

- [ ] **Step 1: Port provider characterization tests before production code**

Adapt the proven tests from Archer-prosess commit `8bc69e7`:

```text
tests/test_edge_cdp.py          ← tests/test_edge_cdp.py
tests/test_capture.py           ← tests/test_capture_validation.py
tests/test_browser_providers.py ← relevant cases from tests/test_browser_review.py
```

Change imports from `archer_processor` to `mpn_tolkning`, remove broad VPM-only
cases, and retain tests for profile isolation, hidden/minimized Edge, provider
order, exact ClinVar GRCh37 allele matching, Franklin somatic/hg19 selection,
OncoKB overlay dismissal, COSMIC COSV resolution, MTBP pseudonyms, cooperative
pause/stop, CALR-ETdb focused result capture, and incomplete screenshot rejection.

Add this MPN-specific assertion:

```python
def test_required_browser_provider_order():
    assert REQUIRED_BROWSER_PROVIDERS == ("MTBP", "Franklin", "ClinVar", "OncoKB", "COSMIC")
```

- [ ] **Step 2: Run characterization tests and verify missing implementations**

Run: `py -3.11 -m pytest tests/test_edge_cdp.py tests/test_capture.py tests/test_browser_providers.py -v`

Expected: tests fail because the mapped production modules do not exist.

- [ ] **Step 3: Port and narrow the proven Edge transport**

Port the direct Edge DevTools transport from the same pinned commit into
`edge_cdp.py`. Change profile root to `.mpn-tolkning/browser_profiles`, retain
hidden-window startup, local WebSocket control, explicit timeout errors, and
process cleanup. Do not add Selenium, Playwright, Node, or an EdgeDriver binary.

```python
class EdgeCdpSession:
    def __init__(self, profile_root: Path, *, background: bool = True, timeout_ms: int = 45_000): ...
    def start(self, provider: str) -> None: ...
    def navigate(self, url: str) -> None: ...
    def evaluate(self, expression: str) -> object: ...
    def screenshot(self, path: Path, clip: dict | None = None) -> Path: ...
    def close(self) -> None: ...
```

- [ ] **Step 4: Port capture validation and provider flows behind separate classes**

Move shared screenshot checks into `capture.py`. Port provider behavior from the
pinned commit while mapping every outcome to `EvidenceResult`. Keep provider
classes separate even if they share DOM helpers. Required safeguards:

```text
MTBP     generated pseudonym, one variant/report, no personal report URL export
Franklin Somatic + hg19, transcript first, genomic fallback, verified identity
ClinVar exact chromosome/position/ref/alt plus GRCh37 before opening/capture
OncoKB  gene/alteration verification and cookie-overlay dismissal
COSMIC  imported COSV preferred and canonical GRCh37 page verification
```

Each provider accepts `stop_requested` and `pause_checkpoint` callbacks. Save
screenshots with hashes, never sample identifiers.

Extend `CalrEtProvider` with an injected Edge capture callback that repeats the
same cDNA-only form submission in its isolated profile and captures the verified
result table/description. A parsed HTTP result without its required valid capture
returns `INCOMPLETE_CAPTURE`, not `FOUND`.

```python
REQUIRED_BROWSER_PROVIDERS = ("MTBP", "Franklin", "ClinVar", "OncoKB", "COSMIC")


class FranklinProvider:
    name = "Franklin"
    def search(self, variant: VariantRecord, context: SearchContext) -> EvidenceResult:
        self.pause_checkpoint()
        return self._search_somatic_hg19_with_verified_identity(variant, context)


def screenshot_path(root: Path, stable_key: str, provider: str, index: int) -> Path:
    digest = hashlib.sha256(stable_key.encode("utf-8")).hexdigest()[:16]
    return root / f"{digest}_{provider.lower()}_{index:02d}.png"
```

- [ ] **Step 5: Run browser-provider regression tests**

Run: `py -3.11 -m pytest tests/test_edge_cdp.py tests/test_capture.py tests/test_browser_providers.py -v`

Expected: all fixture/unit tests pass with no live provider calls.

- [ ] **Step 6: Run the full deterministic suite**

Run: `py -3.11 -m pytest -q`

Expected: all tests pass.

- [ ] **Step 7: Commit browser providers**

```powershell
git add src/mpn_tolkning/services/edge_cdp.py src/mpn_tolkning/services/capture.py src/mpn_tolkning/providers/browser.py tests/test_edge_cdp.py tests/test_capture.py tests/test_browser_providers.py
git commit -m "feat: add verified Edge evidence providers"
```

---

### Task 9: Incremental Patient Reports

**Files:**
- Create: `src/mpn_tolkning/reports/patient.py`
- Create: `tests/test_patient_report.py`
- Create: `tests/test_report_coordinator.py`

**Interfaces:**
- Consumes: variants, driver context, evidence results, screenshots, and workbook path.
- Produces: `write_patient_report(path, sample, variants, evidence) -> Path`, `PatientReportCoordinator.update_patient(...)`, `PatientReportCoordinator.write_all(...)`, and `PatientReportCoordinator.reconcile()`.

- [ ] **Step 1: Write failing report structure/order tests**

```python
# tests/test_patient_report.py
from openpyxl import load_workbook
from mpn_tolkning.core.models import EvidenceResult, EvidenceStatus
from mpn_tolkning.reports.patient import write_patient_report


def test_calr_patient_report_uses_mpn_name_and_provider_order(tmp_path, calr_variant):
    evidence_set = [
        EvidenceResult(provider, EvidenceStatus.FOUND, f"{provider} match")
        for provider in ("CALR-ETdb", "MTBP", "Franklin", "ClinVar", "OncoKB", "COSMIC")
    ]
    path = write_patient_report(tmp_path, "DIT-1001", [calr_variant], evidence_set)
    assert path.name == "DIT-1001_MPN_Tolkning.xlsx"
    workbook = load_workbook(path)
    assert workbook.sheetnames[:2] == ["Oversikt", "Vedlegg"]
    sheet = workbook[workbook.sheetnames[2]]
    captions = [cell.value for row in sheet.iter_rows() for cell in row if isinstance(cell.value, str)]
    indexes = [captions.index(name) for name in ("CALR-ETdb", "MTBP", "Franklin", "ClinVar", "OncoKB", "COSMIC")]
    assert indexes == sorted(indexes)
```

```python
# tests/test_report_coordinator.py
from mpn_tolkning.reports.patient import PatientReportCoordinator


def test_coordinator_marks_locked_workbook_pending_and_retries(tmp_path, calr_variant, monkeypatch):
    coordinator = PatientReportCoordinator(tmp_path)
    original_save = coordinator._save
    calls = 0
    def flaky_save(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise PermissionError("workbook open")
        return original_save(*args, **kwargs)
    monkeypatch.setattr(coordinator, "_save", flaky_save)
    coordinator.update_patient("DIT-1001", [calr_variant], [])
    assert coordinator.pending_samples == {"DIT-1001"}
    coordinator.reconcile()
    assert coordinator.pending_samples == set()
```

- [ ] **Step 2: Run tests and confirm missing patient report module**

Run: `py -3.11 -m pytest tests/test_patient_report.py tests/test_report_coordinator.py -v`

Expected: collection fails for missing `reports.patient`.

- [ ] **Step 3: Implement workbook generation and lock recovery**

Create `Oversikt`, `Vedlegg`, and collision-safe per-variant sheets. Add compact
context/evidence rows, safe links, plain screenshot captions, scaled verified
images, and the research/qualified-review disclaimer. Use CALR-specific provider
order only for CALR variants. Catch `PermissionError`, retain the pending payload
in memory, and retry it from `reconcile` without losing completed evidence.

- [ ] **Step 4: Run report and full tests**

Run: `py -3.11 -m pytest tests/test_patient_report.py tests/test_report_coordinator.py -v`

Run: `py -3.11 -m pytest -q`

Expected: all tests pass.

- [ ] **Step 5: Commit patient reporting**

```powershell
git add src/mpn_tolkning/reports/patient.py tests/test_patient_report.py tests/test_report_coordinator.py
git commit -m "feat: generate incremental MPN patient reports"
```

---

### Task 10: Guided PyQt6 Workbench

**Files:**
- Create: `src/mpn_tolkning/gui/__init__.py`
- Create: `src/mpn_tolkning/gui/workers.py`
- Create: `src/mpn_tolkning/gui/app.py`
- Create: `tests/test_gui.py`
- Modify: `src/mpn_tolkning/__main__.py`

**Interfaces:**
- Consumes: reader, context/rules, review reports, providers, queue, audit, patient coordinator, settings.
- Produces: `MainWindow`, background Qt workers, and a working `mpn-tolkning` entry point.

- [ ] **Step 1: Write failing navigation and accessibility tests**

```python
# tests/test_gui.py
import pytest
from PyQt6.QtWidgets import QApplication
from mpn_tolkning.gui.app import MainWindow


@pytest.fixture
def qt_app():
    return QApplication.instance() or QApplication([])


def test_workbench_has_approved_navigation(qt_app):
    window = MainWindow()
    assert [button.text() for button in window.nav_buttons] == ["Import", "Driver Review", "Evidence", "Reports", "Settings"]


def test_driver_table_and_filter_have_accessible_names(qt_app):
    window = MainWindow()
    assert window.variant_table.accessibleName() == "MPN variant review table"
    assert window.review_filter.accessibleName() == "Filter MPN variants"


def test_window_respects_approved_minimum_size(qt_app):
    window = MainWindow()
    assert window.minimumWidth() == 1120
    assert window.minimumHeight() == 720
```

- [ ] **Step 2: Run GUI tests and confirm missing GUI module**

Run: `$env:QT_QPA_PLATFORM='offscreen'; py -3.11 -m pytest tests/test_gui.py -v`

Expected: collection fails for missing `gui.app`.

- [ ] **Step 3: Build the shell and five focused pages**

Implement a 190–226 px sidebar and stacked pages. Use the approved semantic
palette (`#123C3C`, `#0F766E`, `#D97706`, `#F4F8F7`), Segoe UI, Consolas for
HGVS, visible focus borders, text/icon status labels, 44 px primary action
targets, and no hover-only interactions. The Driver Review page contains summary
metrics, filter controls, a table, and selected-variant/provider detail pane.

```python
class Palette:
    DEEP_TEAL = "#123C3C"
    TEAL = "#0F766E"
    AMBER = "#D97706"
    BACKGROUND = "#F4F8F7"


class MainWindow(QMainWindow):
    PAGE_NAMES = ("Import", "Driver Review", "Evidence", "Reports", "Settings")
    def __init__(self):
        super().__init__()
        self.setMinimumSize(1120, 720)
        self.review_filter = QLineEdit()
        self.review_filter.setAccessibleName("Filter MPN variants")
        self.variant_table = QTableWidget()
        self.variant_table.setAccessibleName("MPN variant review table")
```

- [ ] **Step 4: Connect background workers and state transitions**

`ImportWorker` loads TSV and workbook data outside the UI thread. `SearchWorker`
runs `EvidenceQueue`, emits per-provider results/progress, and exposes pause,
resume, and stop slots. `ReportWorker` reconciles patient/review workbooks. All
worker exceptions emit structured user-facing messages without crashing Qt.

Update `__main__.py`:

```python
def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("MPN Tolkning")
    window = MainWindow()
    window.show()
    raise SystemExit(app.exec())
```

- [ ] **Step 5: Run GUI and full automated tests**

Run: `$env:QT_QPA_PLATFORM='offscreen'; py -3.11 -m pytest tests/test_gui.py -v`

Run: `$env:QT_QPA_PLATFORM='offscreen'; py -3.11 -m pytest -q`

Expected: all tests pass with no Qt warnings promoted to failures.

- [ ] **Step 6: Perform manual desktop checks**

Run: `mpn-tolkning`

Verify at 1120×720 and 1440×900: tab order, visible focus, table filtering,
selection/detail synchronization, provider readiness, pause/resume/stop controls,
and no clipped text or horizontal page scrolling.

- [ ] **Step 7: Commit the workbench**

```powershell
git add src/mpn_tolkning/gui src/mpn_tolkning/__main__.py tests/test_gui.py
git commit -m "feat: build guided MPN workbench"
```

---

### Task 11: Variant Lens Assets, Documentation, CI, and Pages

**Files:**
- Create: `src/mpn_tolkning/assets/variant-lens.svg`
- Create: `scripts/build_icons.py`
- Create: generated `src/mpn_tolkning/assets/variant-lens.png`
- Create: generated `src/mpn_tolkning/assets/variant-lens.ico`
- Create: `README.md`
- Create: `docs/assets/mpn-tolkning-workbench.png`
- Create: `.github/workflows/test.yml`
- Create: `.github/workflows/pages.yml`
- Create: `site/index.html`
- Create: `tests/test_assets.py`

**Interfaces:**
- Produces: deterministic branded assets, public documentation, Windows CI, and static Pages artifact.

- [ ] **Step 1: Write failing asset tests**

```python
# tests/test_assets.py
from pathlib import Path
from PIL import Image


def test_windows_icon_contains_small_and_large_sizes():
    path = Path("src/mpn_tolkning/assets/variant-lens.ico")
    with Image.open(path) as icon:
        assert {(16, 16), (32, 32), (256, 256)}.issubset(set(icon.info["sizes"]))


def test_public_docs_do_not_contain_fixture_patient_ids():
    public = Path("README.md").read_text(encoding="utf-8") + Path("site/index.html").read_text(encoding="utf-8")
    assert "DIT-1001" not in public
```

- [ ] **Step 2: Run asset tests and confirm files are missing**

Run: `py -3.11 -m pytest tests/test_assets.py -v`

Expected: failures because icon and documentation files do not exist.

- [ ] **Step 3: Create the approved Variant Lens source and generator**

The SVG uses a deep-teal rounded square, white lens, teal DNA strand, and amber
handle. `scripts/build_icons.py` renders PNG sizes 16, 24, 32, 48, 64, 128, and
256 with `PyQt6.QtSvg.QSvgRenderer`, then writes a multi-resolution ICO with
Pillow. Keep the SVG as the source of truth and make reruns byte-stable where
Pillow permits.

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <rect x="4" y="4" width="120" height="120" rx="28" fill="#123C3C"/>
  <circle cx="56" cy="54" r="29" fill="none" stroke="#ECF8F5" stroke-width="9"/>
  <path d="M77 76 102 101" stroke="#D97706" stroke-width="13" stroke-linecap="round"/>
  <path d="M43 34c20 12 4 28 24 39M65 33C45 45 62 59 42 73" stroke="#20A89D" stroke-width="6" fill="none"/>
</svg>
```

```python
def render_png(svg_path: Path, size: int, output: Path) -> None:
    renderer = QSvgRenderer(str(svg_path))
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()
    image.save(str(output), "PNG")
```

- [ ] **Step 4: Capture a synthetic UI screenshot and write public docs**

Populate the app with synthetic identifiers that are not copied from tests or
real cases, capture the approved workbench at 1440×900, and save it to
`docs/assets/mpn-tolkning-workbench.png`. The README and static site document the
workflow, six required providers, installation, Edge/Excel requirements,
privacy, recovery behavior, research-use disclaimer, and development commands.

```markdown
# MPN Tolkning

Windows workstation for review-first JAK2, CALR, and MPL evidence collection.

> MPN Tolkning is an interpretation-support tool. Qualified personnel must
> review all evidence and reports before clinical use.

## Workflow
## Evidence sources
## Privacy and operational safeguards
## Installation
## Development
```

- [ ] **Step 5: Add deterministic Windows CI and Pages deployment**

`test.yml` checks out code, installs Python 3.11, installs `.[dev]`, sets
`QT_QPA_PLATFORM=offscreen`, and runs `pytest -q`. `pages.yml` uploads `site/` as
the Pages artifact on pushes to `main` and deploys with official GitHub Pages
actions and `pages: write`/`id-token: write` permissions.

```yaml
# .github/workflows/test.yml
name: tests
on: [push, pull_request]
jobs:
  windows:
    runs-on: windows-latest
    env:
      QT_QPA_PLATFORM: offscreen
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.11"}
      - run: python -m pip install -e ".[dev]"
      - run: pytest -q
```

```yaml
# .github/workflows/pages.yml
name: pages
on:
  push: {branches: [main]}
  workflow_dispatch:
permissions: {contents: read, pages: write, id-token: write}
```

- [ ] **Step 6: Run asset, documentation, and full tests**

Run: `py -3.11 scripts/build_icons.py`

Run: `py -3.11 -m pytest tests/test_assets.py -v`

Run: `$env:QT_QPA_PLATFORM='offscreen'; py -3.11 -m pytest -q`

Expected: all tests pass.

- [ ] **Step 7: Commit branding and automation**

```powershell
git add src/mpn_tolkning/assets scripts/build_icons.py README.md docs/assets site .github tests/test_assets.py
git commit -m "docs: add MPN branding and public project site"
```

---

### Task 12: End-to-End Verification and GitHub Publication

**Files:**
- Create: `tests/test_end_to_end.py`
- Modify only if verification finds a defect: the smallest owning source/test file.

**Interfaces:**
- Consumes: the complete application.
- Produces: verified local release candidate and public GitHub repository/Pages deployment.

- [ ] **Step 1: Write the end-to-end synthetic workflow test**

```python
# tests/test_end_to_end.py
from pathlib import Path
from mpn_tolkning.core.context import classify_driver_context
from mpn_tolkning.core.identity import stable_variant_key
from mpn_tolkning.core.models import EvidenceResult, EvidenceStatus
from mpn_tolkning.io.tsv_reader import ArcherTsvReader
from mpn_tolkning.reports.patient import PatientReportCoordinator
from mpn_tolkning.reports.review import write_review_workbook
from mpn_tolkning.services.audit import AuditStore
from mpn_tolkning.services.queue import EvidenceQueue, PauseControl


class FakeProvider:
    def __init__(self, name):
        self.name = name
    def search(self, variant, context):
        return EvidenceResult(self.name, EvidenceStatus.FOUND, f"{self.name} synthetic match")


def test_synthetic_run_imports_reviews_searches_resumes_and_reports(tmp_path):
    variants = ArcherTsvReader().read(Path("tests/fixtures/sample_mpn_variants.tsv"))
    contexts = {stable_variant_key(variant): classify_driver_context(variant) for variant in variants}
    review = write_review_workbook(tmp_path / "review.xlsx", variants, contexts, {})
    fake_provider_set = [
        FakeProvider(name)
        for name in ("CALR-ETdb", "MTBP", "Franklin", "ClinVar", "OncoKB", "COSMIC")
    ]
    queue = EvidenceQueue(fake_provider_set, audit_callback=AuditStore(tmp_path / "evidence").save)
    first = queue.run(variants, skip_keys=set(), pause=PauseControl())
    resumed = queue.resume_pending(variants, first)
    reports = PatientReportCoordinator(tmp_path).write_all(variants, resumed)
    assert review.exists()
    assert len(reports) == 3
    assert all(path.exists() for path in reports)
```

- [ ] **Step 2: Run the end-to-end test and correct only real integration gaps**

Run: `$env:QT_QPA_PLATFORM='offscreen'; py -3.11 -m pytest tests/test_end_to_end.py -v`

Expected: pass after wiring existing interfaces; any failure receives a focused
regression test before the minimal fix.

- [ ] **Step 3: Run fresh release-candidate verification**

Run: `$env:QT_QPA_PLATFORM='offscreen'; py -3.11 -m pytest -q`

Run: `py -3.11 -m pip check`

Run: `git diff --check`

Run: `git status --short`

Expected: zero test failures, no dependency conflicts, no whitespace errors, and
only intentional release-candidate changes.

- [ ] **Step 4: Run opt-in provider smoke checklist**

Using synthetic variants and existing authenticated browser profiles, verify one
safe query per required provider. Record provider status and selector incidents
without including patient data. Confirm CALR-ETdb receives `c.…` only, MTBP uses
a generated pseudonym, Franklin is Somatic/hg19, ClinVar matches GRCh37 allele,
OncoKB matches gene/alteration, and COSMIC resolves the expected COSV page.

- [ ] **Step 5: Commit end-to-end verification**

```powershell
git add tests/test_end_to_end.py
git commit -m "test: verify complete MPN interpretation workflow"
```

- [ ] **Step 6: Create and push the public repository**

Run: `gh repo create Christian-Bjornstad/MPN-Tolkning --public --source . --remote origin --push --description "Windows workstation for JAK2, CALR, and MPL evidence review"`

Expected: repository created with `main` pushed and `origin` set to the new URL.

- [ ] **Step 7: Enable Pages and verify both public URLs**

Run: `gh workflow run pages.yml --repo Christian-Bjornstad/MPN-Tolkning`

Run: `gh run watch --repo Christian-Bjornstad/MPN-Tolkning --exit-status`

Expected: Pages workflow succeeds and the landing page is available at
`https://christian-bjornstad.github.io/MPN-Tolkning/`.

- [ ] **Step 8: Final public-state check**

Run: `gh repo view Christian-Bjornstad/MPN-Tolkning --web`

Verify the README image, disclaimer, Actions result, default branch, repository
visibility, and Pages link. Do not create a release tag until the live provider
smoke checklist and manual UI checks are recorded as passing.
