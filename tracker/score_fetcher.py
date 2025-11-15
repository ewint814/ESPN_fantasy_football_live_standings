import logging
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import requests
from espn_api.football import League
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


@dataclass
class TeamScore:
    team_name: str
    live_score: float
    projected_score: float
    currently_playing: List[str]
    yet_to_play: List[str]
    finished_playing: List[str]
    players_playing_count: int
    players_remaining_count: int
    players_finished_count: int
    total_starters: int
    rank: Optional[int] = None
    is_current_top6: bool = False
    projected_rank: Optional[int] = None
    is_projected_top6: bool = False

    def as_dict(self) -> Dict:
        return asdict(self)


class ScoreFetcher:
    """Shared service that pulls ESPN data and prepares league standings."""

    SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
    FINISHED_STATUSES = {"final", "final overtime", "post"}
    ACTIVE_STATUSES = {"in", "live", "halftime", "end of period", "delayed"}

    def __init__(self):
        self.league: Optional[League] = None
        self.current_week: int = 1
        self.game_clocks: Dict[str, Dict] = {}
        self.api_error: Optional[str] = None
        self.games_today_cache: Optional[bool] = None
        self.games_check_date: Optional[datetime.date] = None

        self._connect_to_espn()
        self.current_week = self._get_current_week()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def build_snapshot(self) -> Dict:
        """Return the latest scores plus metadata for consumers."""
        scores = self._get_live_scores()
        timestamp = datetime.now(timezone.utc)

        return {
            "scores": scores,
            "last_update": timestamp.isoformat(),
            "week": self.current_week,
            "api_error": self.api_error,
        }

    # ------------------------------------------------------------------ #
    # ESPN Connectivity & Metadata
    # ------------------------------------------------------------------ #
    def _connect_to_espn(self):
        """Connect to the user's ESPN league."""
        try:
            league_id = os.getenv("ESPN_LEAGUE_ID")
            espn_s2 = os.getenv("ESPN_S2")
            swid = os.getenv("ESPN_SWID")
            year = self._resolve_target_year()

            if not all([league_id, espn_s2, swid]):
                raise ValueError(
                    "Missing required environment variables: ESPN_LEAGUE_ID, ESPN_S2, ESPN_SWID"
                )

            self.league = League(
                league_id=int(league_id),
                year=year,
                espn_s2=espn_s2,
                swid=swid,
            )
        except Exception as exc:
            logger.exception("Failed to connect to ESPN: %s", exc)
            self.league = None
            self.api_error = "Unable to connect to ESPN. Check credentials."

    def _resolve_target_year(self) -> int:
        configured = os.getenv("ESPN_YEAR")
        if configured:
            try:
                return int(configured)
            except ValueError:
                pass

        today = datetime.now()
        if today.month >= 7:
            return today.year
        return today.year - 1

    def _get_current_week(self) -> int:
        """Get current NFL week from the scoreboard API."""
        try:
            response = requests.get(self.SCOREBOARD_URL, timeout=10)
            if response.status_code == 200:
                data = response.json()
                week = data.get("week", {}).get("number")
                if isinstance(week, int):
                    return week

            if self.league and hasattr(self.league, "current_week"):
                return self.league.current_week
        except Exception as exc:
            logger.warning("Falling back for current week: %s", exc)

        return 1

    # ------------------------------------------------------------------ #
    # Score & Projection Calculations
    # ------------------------------------------------------------------ #
    def _get_live_scores(self) -> List[Dict]:
        if not self.league:
            logger.warning("No league connection available.")
            return []

        try:
            self.game_clocks = self._get_nfl_game_clocks()
            box_scores = self.league.box_scores(week=self.current_week)
            teams: List[TeamScore] = []

            for matchup in box_scores:
                teams.extend(
                    self._build_team_data(
                        team=matchup.home_team,
                        lineup=matchup.home_lineup,
                        score=matchup.home_score,
                    )
                )
                teams.extend(
                    self._build_team_data(
                        team=matchup.away_team,
                        lineup=matchup.away_lineup,
                        score=matchup.away_score,
                    )
                )

            sorted_teams = self._sort_and_rank_teams(teams)
            self.api_error = None
            return [team.as_dict() for team in sorted_teams]

        except Exception as exc:
            logger.exception("Failed to fetch live scores: %s", exc)
            self.api_error = str(exc)
            raise

    def _build_team_data(self, team, lineup, score) -> List[TeamScore]:
        team_name = getattr(team, "team_name", "Unknown Team")
        currently_playing: List[str] = []
        yet_to_play: List[str] = []
        finished_playing: List[str] = []
        projected_total = 0.0
        total_starters = 0

        for player in lineup:
            if player.slot_position == "BE":
                continue

            total_starters += 1
            player_name = getattr(player, "name", "Unknown")
            player_points = float(getattr(player, "points", 0.0) or 0.0)
            pre_game_projection = float(getattr(player, "projected_points", 0.0) or 0.0)
            pro_team = getattr(player, "proTeam", "")
            game_played = getattr(player, "game_played", None)

            clock_data = self.game_clocks.get(pro_team, {})
            minutes_played = clock_data.get("minutes_played", 0)
            game_status = clock_data.get("status", "").lower()

            live_projection = self._calculate_live_projection(
                pre_game_projection,
                player_points,
                minutes_played,
                game_played,
                game_status,
            )

            if game_played == 0:
                yet_to_play.append(f"{player_name} (proj: {pre_game_projection:.1f})")
            elif game_played in (1,):
                currently_playing.append(f"{player_name} ({player_points:.1f})")
            elif game_played in (100, 2):
                finished_playing.append(f"{player_name} ({player_points:.1f})")
            else:
                if game_status in self.FINISHED_STATUSES:
                    finished_playing.append(f"{player_name} ({player_points:.1f})")
                elif game_status in self.ACTIVE_STATUSES:
                    currently_playing.append(f"{player_name} ({player_points:.1f})")
                else:
                    yet_to_play.append(f"{player_name} (proj: {pre_game_projection:.1f})")

            projected_total += live_projection

        team_score = TeamScore(
            team_name=team_name,
            live_score=float(score) if score else 0.0,
            projected_score=round(projected_total, 2),
            currently_playing=currently_playing,
            yet_to_play=yet_to_play,
            finished_playing=finished_playing,
            players_playing_count=len(currently_playing),
            players_remaining_count=len(yet_to_play),
            players_finished_count=len(finished_playing),
            total_starters=total_starters,
        )

        return [team_score]

    def _sort_and_rank_teams(self, teams: List[TeamScore]) -> List[TeamScore]:
        teams.sort(key=lambda team: team.live_score, reverse=True)

        for idx, team in enumerate(teams):
            team.rank = idx + 1
            team.is_current_top6 = idx < 6

        projected_sorted = sorted(teams, key=lambda t: t.projected_score, reverse=True)
        for idx, team in enumerate(projected_sorted):
            team.projected_rank = idx + 1
            team.is_projected_top6 = idx < 6

        teams.sort(key=lambda team: team.live_score, reverse=True)
        return teams

    def _calculate_live_projection(
        self,
        pre_game_projection: float,
        current_points: float,
        minutes_played: float,
        game_played: Optional[int],
        game_status: str,
    ) -> float:
        """Blend pre-game projection with actual performance and game progress."""
        if game_played in (100, 2) or game_status in self.FINISHED_STATUSES or minutes_played >= 60:
            return current_points

        if game_played == 0:
            return pre_game_projection

        progress = max(0.0, min(1.0, minutes_played / 60.0))
        baseline = max(pre_game_projection, 0.0)
        actual = max(current_points, 0.0)
        remaining_projection = max(baseline - actual, 0.0)

        projected = actual + remaining_projection * (1 - progress)

        if actual > baseline:
            bonus = (actual - baseline) * (1 - progress * 0.5)
            projected = actual + bonus

        return round(projected, 2)

    # ------------------------------------------------------------------ #
    # NFL Scoreboard Helpers
    # ------------------------------------------------------------------ #
    def _get_nfl_game_clocks(self) -> Dict[str, Dict]:
        try:
            response = requests.get(self.SCOREBOARD_URL, timeout=10)
            response.raise_for_status()
            data = response.json()
            games = data.get("events", [])
            game_clocks: Dict[str, Dict] = {}

            for game in games:
                competitors = game.get("competitions", [{}])[0].get("competitors", [])
                if len(competitors) < 2:
                    continue

                team1 = competitors[0].get("team", {}).get("abbreviation", "")
                team2 = competitors[1].get("team", {}).get("abbreviation", "")

                status = game.get("status", {})
                clock = status.get("displayClock", "0:00")
                period = status.get("period", 1)
                game_status = status.get("type", {}).get("name", "unknown")

                minutes_played = self._calculate_minutes_played(clock, period, game_status)

                for team_abbr in (team1, team2):
                    if not team_abbr:
                        continue
                    game_clocks[team_abbr] = {
                        "clock": clock,
                        "period": period,
                        "status": game_status.lower(),
                        "minutes_played": minutes_played,
                        "game_progress": min(minutes_played / 60.0, 1.0),
                    }

            return game_clocks

        except Exception as exc:
            logger.warning("Unable to fetch NFL scoreboard: %s", exc)
            return {}

    def _calculate_minutes_played(self, clock: str, period: int, status: str) -> float:
        try:
            status_lower = (status or "").lower()
            if any(word in status_lower for word in self.FINISHED_STATUSES):
                return 60.0
            if any(word in status_lower for word in ["scheduled", "pre", "upcoming"]):
                return 0.0

            minutes = 0
            seconds = 0
            if ":" in clock:
                parts = clock.split(":")
                if len(parts) == 2:
                    minutes = int(parts[0])
                    seconds = int(parts[1])

            remaining_in_quarter = minutes + seconds / 60.0
            completed_quarters = max(0, period - 1)
            minutes_in_current_quarter = 15 - remaining_in_quarter
            total_minutes = completed_quarters * 15 + minutes_in_current_quarter
            return min(max(total_minutes, 0.0), 60.0)
        except Exception:
            return 30.0

    # ------------------------------------------------------------------ #
    # Game-day cadence helpers
    # ------------------------------------------------------------------ #
    def has_games_today(self) -> bool:
        now = datetime.now()
        today = now.date()
        if self.games_check_date != today:
            self.games_today_cache = self._check_if_games_today_or_tonight()
            self.games_check_date = today
        return bool(self.games_today_cache)

    def _check_if_games_today_or_tonight(self) -> bool:
        try:
            response = requests.get(self.SCOREBOARD_URL, timeout=10)
            response.raise_for_status()
            data = response.json()
            games = data.get("events", [])

            now = datetime.now(timezone.utc)
            today = now.date()

            for game in games:
                game_date_str = game.get("date", "")
                if not game_date_str:
                    continue

                game_datetime = datetime.fromisoformat(game_date_str.replace("Z", "+00:00"))
                game_date = game_datetime.date()

                if game_date == today:
                    return True

                if game_date == today - timedelta(days=1):
                    status = game.get("status", {})
                    name = status.get("type", {}).get("name", "").lower()
                    state = status.get("type", {}).get("state", "").lower()
                    if name in self.ACTIVE_STATUSES or state in self.ACTIVE_STATUSES:
                        return True

            return False
        except Exception:
            return True
