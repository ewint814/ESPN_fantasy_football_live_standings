"""
Core utilities for the Fantasy Football tracker.

This package hosts shared logic so the Flask app and the scheduled
fetcher script can reuse the same ESPN integration and projection rules.
"""

from .score_fetcher import ScoreFetcher

__all__ = ["ScoreFetcher"]
