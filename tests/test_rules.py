from mpn_tolkning.core.models import VariantRecord
from mpn_tolkning.core.rules import (
    ArtifactRule,
    configured_artifact_rules,
    default_artifact_rules,
    evaluate_artifact,
)


def test_mpn_artifact_rule_matches_gene_cdna_and_vaf_threshold():
    rules = [
        ArtifactRule(
            "JAK2",
            "c.3291+16dup",
            5.0,
            "Intronic homopolymer observation",
        )
    ]
    variant = VariantRecord("DIT-1", "JAK2", "NM_004972.4:c.3291+16dup", 2.0)

    assert evaluate_artifact(variant, rules) == "Intronic homopolymer observation"


def test_artifact_rule_does_not_match_above_vaf_ceiling():
    rule = ArtifactRule("JAK2", "c.3291+16dup", 5.0, "Known artifact")
    variant = VariantRecord("DIT-1", "JAK2", "NM_004972.4:c.3291+16dup", 8.0)

    assert evaluate_artifact(variant, [rule]) == ""


def test_default_rules_contain_only_explicit_mpn_relevant_jak2_entries():
    rules = default_artifact_rules()

    assert {rule.gene for rule in rules} == {"JAK2"}
    assert {rule.cdna for rule in rules} == {"c.3291+16dup", "c.3291+16del"}


def test_configured_artifact_rules_override_defaults():
    rules = configured_artifact_rules([
        {"gene": "CALR", "cdna": "c.1099_1150del", "max_vaf": 8, "reason": "local rule"}
    ])

    assert rules == [ArtifactRule("CALR", "c.1099_1150del", 8.0, "local rule")]


def test_invalid_configured_artifact_rules_fail_safe_to_defaults():
    assert configured_artifact_rules([{"gene": "CALR"}]) == default_artifact_rules()
