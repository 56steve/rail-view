from app.services.platforms import PlatformEntry, resolve_platform

ANDHERI_WR = (
    PlatformEntry(numbers=("3",), corridor="slow", direction="DN", role="through", door="left", certain=True),
    PlatformEntry(numbers=("5",), corridor="slow", direction="UP", role="through", door="left", certain=True),
    PlatformEntry(numbers=("6",), corridor="fast", direction="DN", role="through", door="right", certain=True),
    PlatformEntry(numbers=("7",), corridor="fast", direction="UP", role="through", door="right", certain=True),
    PlatformEntry(numbers=("4",), corridor="slow", direction="UP", role="originating", door="right", certain=False),
    PlatformEntry(numbers=("8", "9"), corridor="fast", direction="UP", role="originating", door=None, certain=False),
)


def test_through_stop_on_its_corridor_is_certain() -> None:
    p = resolve_platform(ANDHERI_WR, corridor="slow", direction="DN", role="through")
    assert p is not None
    assert (p.numbers, p.door, p.certain) == (("3",), "left", True)


def test_role_specific_entries_win() -> None:
    p = resolve_platform(ANDHERI_WR, corridor="fast", direction="UP", role="originating")
    assert p is not None
    assert (p.numbers, p.door, p.certain) == (("8", "9"), None, False)


def test_missing_role_falls_back_to_through() -> None:
    p = resolve_platform(ANDHERI_WR, corridor="fast", direction="DN", role="terminating")
    assert p is not None and p.numbers == ("6",) and p.certain


def test_other_corridor_is_a_fallback_and_never_certain() -> None:
    only_slow = tuple(e for e in ANDHERI_WR if e.corridor == "slow" and e.role == "through")
    p = resolve_platform(only_slow, corridor="fast", direction="UP", role="through")
    assert p is not None and p.numbers == ("5",) and not p.certain


def test_any_corridor_matches_every_train() -> None:
    entries = (PlatformEntry(numbers=("1",), corridor="any", direction="DN", role="through", door="right", certain=True),)
    p = resolve_platform(entries, corridor="slow", direction="DN", role="through")
    assert p is not None and p.numbers == ("1",) and p.certain


def test_several_matches_union_and_lose_certainty() -> None:
    entries = (
        PlatformEntry(numbers=("2",), corridor="any", direction="UP", role="through", door="left", certain=True),
        PlatformEntry(numbers=("1",), corridor="any", direction="UP", role="through", door="left", certain=True),
    )
    p = resolve_platform(entries, corridor="any", direction="UP", role="through")
    assert p is not None
    assert (p.numbers, p.door, p.certain) == (("1", "2"), "left", False)


def test_no_entry_for_the_direction_is_none() -> None:
    entries = (PlatformEntry(numbers=("1",), corridor="any", direction="DN", role="through", door=None, certain=True),)
    assert resolve_platform(entries, corridor="any", direction="UP", role="through") is None
