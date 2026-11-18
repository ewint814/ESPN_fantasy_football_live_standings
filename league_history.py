"""Final places from the league sheet.

The sheet is the record of who finished where. ESPN's default final
rankings do not match this league's losers' bracket, so they are not used.

The sheet left most middle places blank for 2012 through 2018. Those
come from replaying each year's playoff bracket with ESPN's scores, and
Eli checked them. The sheet had Bergel in both 1st and 10th for 2016; the
replay puts Yossi 10th. For 2014 the replay puts Jared 8th and Eli 10th,
which Eli confirmed. A Harry cell sits in the 2011
column with no place next to it, so it is not a finish.
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
    champion: str | None


@dataclass(frozen=True)
class Ring:
    """Championships counted from 1st place. Years are oldest first."""

    name: str
    count: int
    years: tuple[int, ...]


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
    Season(
        2018, ("Wechs", "Noach", "Henry", "Joe", "Eli", "Harry", "Noam", "Yossi", "Bergel", "Yoni")
    ),
    Season(
        2017, ("Joe", "Yossi", "Henry", "Harry", "Wechs", "Eli", "Yoni", "Noach", "Noam", "Bergel")
    ),
    Season(
        2016, ("Bergel", "Joe", "Henry", "Yoni", "Eli", "Noam", "Wechs", "Noach", "Harry", "Yossi")
    ),
    Season(
        2015,
        ("Eli", "Ezra", "Harry", "Yoni", "Yossi", "Noach", "Joe", "Henry", "Wechs", "Noam"),
        ("Yossi",),
    ),
    Season(2014, ("Noach", "Ezra", "Henry", "Harry", "Yoni", "Noam", "Wechs", "Jared", "Joe", "Eli")),
    Season(
        2013,
        ("Henry", "Yoni", "Wechs", "Ezra", "Jared", "Joe", "Harry", "Noach", "Noam", "Eli"),
        ("Jared",),
    ),
    Season(
        2012,
        ("Eli", "Joe", "Noach", "Harry", "Yoni", "Noam", "Ezra", "Wechs", "Henry", "Tuvia"),
        ("Wechs", "Henry", "Ezra"),
    ),
    Season(2011, ("Eli", "Austin", "Yoni", "Noam", "Joe", "Tuvia", "Noach", "Goggles")),
)


# Whole-word spellings ESPN uses for a sheet nickname.
# Eli confirmed these: Henry is jake h, Joe is Joseph Solomont,
# Noach is Noah Bressler, Yossi is Yosef Vaitsblit.
# Wechs is Ollie Wechsler. ESPN writes that account "avi wechsler".
# Goggles is the 2011 account that is not one of the other seven: jon avraham.
ALIASES: dict[str, tuple[str, ...]] = {
    "Joe": ("joseph solomont", "joseph solomon", "bsportsfan96"),
    "Henry": ("jake h", "nosoup4ya"),
    "Bergel": ("jake bergel", "jabthat2394"),
    "Noach": ("noah bressler", "noahrb9168341", "9rajonrondo"),
    "Wechs": ("avi wechsler", "avi110", "wechsler", "ollie wechsler", "ollie wexler", "wexler"),
    "Josh": ("josh goldstein", "jrsport69"),
    "Elisha": ("elisha galler", "egall16"),
    "Yossi": ("yosef vaitsblit", "yv23", "ye v", "y v"),
    "Austin": ("austin edelman", "yaust14"),
    "Ezra": ("ezra schwartz", "ezra1001"),
    "Goggles": ("jon avraham", "johnthe bomb"),
    "Jared": ("jared shein", "iamdude12"),
    "Tuvia": ("tuvia oxman", "tuvz"),
}


def _words(text: str) -> str:
    return " ".join(text.lower().replace("·", " ").split())


def _has_phrase(text: str, phrase: str) -> bool:
    return f" {phrase} " in f" {text} "


def sheet_name_for(owner: str) -> str | None:
    """Sheet nickname for an ESPN owner string, or None when it is not linked."""
    text = _words(owner)
    if not text:
        return None
    found: list[tuple[int, str]] = []
    for name, phrases in ALIASES.items():
        for phrase in phrases:
            if _has_phrase(text, phrase):
                found.append((len(phrase), name))
    if found:
        found.sort(reverse=True)
        return found[0][1]
    tokens = [part.strip(".,") for part in text.split() if part.strip(".,")]
    for name in SHEET_ORDER:
        if name.lower() in tokens:
            return name
    return None


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
    return tuple(
        SeasonView(
            season.year,
            _rows(season.places),
            season.joined,
            season.places[0] if season.places else None,
        )
        for season in SEASONS
    )


def ring_counts() -> tuple[Ring, ...]:
    """Championships, most rings first, then the sheet's career order."""
    counts: dict[str, int] = {}
    years: dict[str, list[int]] = {}
    for season in reversed(SEASONS):
        title = season.places[0] if season.places else None
        if not title:
            continue
        counts[title] = counts.get(title, 0) + 1
        years.setdefault(title, []).append(season.year)

    def sort_key(name: str) -> tuple[int, int]:
        try:
            sheet_index = SHEET_ORDER.index(name)
        except ValueError:
            sheet_index = len(SHEET_ORDER)
        return (-counts[name], sheet_index)

    return tuple(
        Ring(name, counts[name], tuple(years[name])) for name in sorted(counts, key=sort_key)
    )


def champion(year: int) -> str | None:
    """1st place for a season, or None when that year is not on the sheet."""
    for season in SEASONS:
        if season.year == year and season.places:
            return season.places[0]
    return None
