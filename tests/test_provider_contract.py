from mpn_tolkning.providers.base import SearchContext


def test_search_context_carries_exact_cdna_and_build():
    context = SearchContext(
        "grch37:19:13054615:AAG:A",
        "NM_004343.4",
        "c.1099_1150del",
    )

    assert context.cdna == "c.1099_1150del"
    assert context.build == "GRCh37"
