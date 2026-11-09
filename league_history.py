"""Final places from the league sheet.

The sheet is the record of who finished where. ESPN's default final
rankings do not match this league's losers' bracket, so this page does
not derive places from ESPN.

2012 through 2018 leave most middle places blank. 2016 lists Bergel in
1st and in 10th, and that is how the sheet reads. A Harry cell sits in
the 2011 column with no place next to it, so it is not a finish.
"""

from dataclasses import dataclass

# Career-table order on the Stats tab. Rings are sorted by count, then this.
SHEET_ORDER: tuple[str, ...] = (
    "Eli",
    "Joe",
    "Henry",
    "Yoni",
    "Bergel",
    "Noach",
    "Wechs",
    "Harry",
    "Josh",
    "Elisha",
    "Noam",
    "Yossi",
    "Austin",
    "Ezra",
    "Goggles",
    "Jared",
    "Tuvia",
)


@dataclass(frozen=True)
class Season:
    """One column of the Finishes tab."""

    year: int
    places: tuple[str | None, ...]
    joined: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlaceRow:
    """One line on a season card. A gap covers places the sheet left blank."""

    label: str
    name: str | None
    champion: bool
    gap: bool


@dataclass(frozen=True)
class SeasonView:
    """A season ready for the history page."""

    year: int
    rows: tuple[PlaceRow, ...]
    joined: tuple[str, ...]


@dataclass(frozen=True)
class Ring:
    """Championships counted from 1st place."""

    name: str
    count: int


# Newest season first. None is a place the sheet left empty.
SEASONS: tuple[Season, ...] = (
    Season(
        2025,
        (
            "Bergel",
            "Henry",
            "Yossi",
            "Noach",
            "Yoni",
            "Elisha",
            "Noam",
            "Harry",
            "Eli",
            "Josh",
            "Joe",
            "Wechs",
        ),
    ),
    Season(
        2024,
        (
            "Yoni",
            "Noach",
            "Eli",
            "Elisha",
            "Henry",
            "Yossi",
            "Harry",
            "Noam",
            "Bergel",
            "Josh",
            "Wechs",
            "Joe",
        ),
    ),
    Season(
        2023,
        (
            "Eli",
            "Wechs",
            "Josh",
            "Bergel",
            "Yoni",
            "Noam",
            "Elisha",
            "Harry",
            "Yossi",
            "Noach",
            "Joe",
            "Henry",
        ),
    ),
    Season(
        2022,
        (
            "Henry",
            "Eli",
            "Bergel",
            "Noach",
            "Joe",
            "Josh",
            "Noam",
            "Yossi",
            "Wechs",
            "Yoni",
            "Elisha",
            "Harry",
        ),
    ),
    Season(
        2021,
        (
            "Yoni",
            "Eli",
            "Wechs",
            "Henry",
            "Noach",
            "Joe",
            "Elisha",
            "Noam",
            "Bergel",
            "Yossi",
            "Harry",
            "Josh",
        ),
    ),
    Season(
        2020, ("Eli", "Noam", "Noach", "Yossi", "Joe", "Bergel", "Henry", "Yoni", "Wechs", "Harry")
    ),
    Season(
        2019, ("Joe", "Eli", "Noach", "Noam", "Yoni", "Henry", "Harry", "Wechs", "Bergel", "Yossi")
    ),
    Season(2018, ("Wechs", "Noach", "Henry", "Joe", None, None, None, None, None, "Yoni")),
    Season(2017, ("Joe", "Yossi", "Henry", "Harry", None, None, None, None, None, "Bergel")),
    Season(2016, ("Bergel", "Joe", "Henry", "Yoni", None, None, None, None, None, "Bergel")),
    Season(
        2015, ("Eli", "Ezra", "Harry", "Yoni", None, None, None, None, None, "Noam"), ("Yossi",)
    ),
    Season(2014, ("Noach", "Ezra", "Henry", "Harry", None, None, None, None, None, "Jared")),
    Season(
        2013, ("Henry", "Yoni", "Wechs", "Ezra", None, None, None, None, None, "Eli"), ("Jared",)
    ),
    Season(
        2012,
        ("Eli", "Joe", "Noach", "Harry", None, None, None, None, None, "Tuvia"),
        ("Wechs", "Henry", "Ezra"),
    ),
    Season(2011, ("Eli", "Austin", "Yoni", "Noam", "Joe", "Tuvia", "Noach", "Goggles")),
)


def ordinal(place: int) -> str:
    """1st, 2nd, 3rd, 4th."""
    if 10 <= place % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(place % 10, "th")
    return f"{place}{suffix}"


def _rows(places: tuple[str | None, ...]) -> tuple[PlaceRow, ...]:
    """Collapse a run of blank places into one line. Drop blank places after the last name."""
    rows: list[PlaceRow] = []
    index = 0
    last = len(places)
    while index < last:
        if places[index] is not None:
            place = index + 1
            rows.append(PlaceRow(ordinal(place), places[index], place == 1, False))
            index += 1
            continue
        end = index
        while end < last and places[end] is None:
            end += 1
        if end == last:
            break
        start_place = index + 1
        end_place = end
        if start_place == end_place:
            label = ordinal(start_place)
        else:
            label = f"{ordinal(start_place)}–{ordinal(end_place)}"
        rows.append(PlaceRow(label, None, False, True))
        index = end
    return tuple(rows)


def season_views() -> tuple[SeasonView, ...]:
    """Season cards, newest first."""
    return tuple(SeasonView(season.year, _rows(season.places), season.joined) for season in SEASONS)


def ring_counts() -> tuple[Ring, ...]:
    """Championships, most rings first, then the sheet's career order."""
    counts: dict[str, int] = {}
    for season in SEASONS:
        champion = season.places[0] if season.places else None
        if champion:
            counts[champion] = counts.get(champion, 0) + 1

    def sort_key(name: str) -> tuple[int, int]:
        try:
            sheet_index = SHEET_ORDER.index(name)
        except ValueError:
            sheet_index = len(SHEET_ORDER)
        return (-counts[name], sheet_index)

    return tuple(Ring(name, counts[name]) for name in sorted(counts, key=sort_key))


def champion(year: int) -> str | None:
    """1st place for a season, or None when that year is not on the sheet."""
    for season in SEASONS:
        if season.year == year and season.places:
            return season.places[0]
    return None
