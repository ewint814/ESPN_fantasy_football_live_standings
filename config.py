"""
Configuration management for Fantasy Football Tracker
"""
import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class Config:
    """Application configuration."""
    
    # ESPN API credentials
    espn_league_id: Optional[str] = None
    espn_s2: Optional[str] = None
    espn_swid: Optional[str] = None
    
    # Server configuration
    host: str = "0.0.0.0"
    port: int = 5000
    debug: bool = False
    
    # Update intervals (seconds)
    update_interval_active: int = 120  # 2 minutes during games
    update_interval_off_hours: int = 300  # 5 minutes off hours
    update_interval_no_games: int = 600  # 10 minutes when no games
    
    # API timeouts
    api_timeout: int = 10
    
    @classmethod
    def from_env(cls) -> 'Config':
        """Load configuration from environment variables."""
        return cls(
            espn_league_id=os.getenv('ESPN_LEAGUE_ID'),
            espn_s2=os.getenv('ESPN_S2'),
            espn_swid=os.getenv('ESPN_SWID'),
            port=int(os.getenv('PORT', 5000)),
            debug=os.getenv('DEBUG', 'false').lower() == 'true'
        )
    
    def validate(self) -> tuple[bool, Optional[str]]:
        """
        Validate configuration.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        missing = []
        
        if not self.espn_league_id:
            missing.append('ESPN_LEAGUE_ID')
        if not self.espn_s2:
            missing.append('ESPN_S2')
        if not self.espn_swid:
            missing.append('ESPN_SWID')
        
        if missing:
            return False, f"Missing required environment variables: {', '.join(missing)}"
        
        return True, None
