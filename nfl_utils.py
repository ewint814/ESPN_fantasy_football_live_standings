"""
NFL Season helper utilities
"""
from datetime import datetime


class NFLSeasonHelper:
    """Helper class to handle NFL season year detection and week calculations."""
    
    # NFL season start dates by year (approximate - first Thursday of September)
    SEASON_STARTS = {
        2024: datetime(2024, 9, 5),
        2025: datetime(2025, 9, 4),
        2026: datetime(2026, 9, 10),
        2027: datetime(2027, 9, 9),
        2028: datetime(2028, 9, 7),
    }
    
    @staticmethod
    def get_current_nfl_year() -> int:
        """
        Determine the current NFL season year.
        NFL season spans two calendar years (e.g., 2026 season runs Sep 2026 - Feb 2027).
        
        Returns:
            Current NFL season year
        """
        now = datetime.now()
        
        # NFL season typically starts in early September and ends in February
        # If we're in March-August, we're in the off-season before the next season
        # If we're in September-December, we're in that year's season
        # If we're in January-February, we're in the previous year's season
        
        if now.month >= 3 and now.month <= 8:
            # Off-season: upcoming season year
            return now.year
        elif now.month >= 9:
            # Regular season start: current year
            return now.year
        else:
            # January-February: previous year's season
            return now.year - 1
    
    @classmethod
    def get_season_start_date(cls, year: int) -> datetime:
        """
        Get the season start date for a given year.
        
        Args:
            year: NFL season year
            
        Returns:
            Season start datetime
        """
        if year in cls.SEASON_STARTS:
            return cls.SEASON_STARTS[year]
        
        # Fallback: approximate as first Thursday of September
        # Find the first Thursday
        first_day = datetime(year, 9, 1)
        days_until_thursday = (3 - first_day.weekday()) % 7
        if days_until_thursday == 0 and first_day.weekday() > 3:
            days_until_thursday = 7
        
        return datetime(year, 9, 1 + days_until_thursday)
    
    @classmethod
    def calculate_week_from_date(cls, year: int, current_date: datetime) -> int:
        """
        Calculate the NFL week based on the current date.
        
        Args:
            year: NFL season year
            current_date: Current datetime
            
        Returns:
            Week number (1-18)
        """
        season_start = cls.get_season_start_date(year)
        
        if current_date < season_start:
            return 1
        
        days_since_start = (current_date - season_start).days
        week = min(18, max(1, (days_since_start // 7) + 1))
        
        return week
