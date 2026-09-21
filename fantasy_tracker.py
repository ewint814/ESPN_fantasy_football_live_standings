"""
Fantasy Football Tracker - Compatibility Entry Point
====================================================
This file exists for backward compatibility with existing Render deployments.
It simply imports and runs the real-time version.

The actual application code is in fantasy_tracker_realtime.py
"""

if __name__ == "__main__":
    # Import and run the real-time tracker
    from fantasy_tracker_realtime import FantasyTracker
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        tracker = FantasyTracker()
        tracker.run(debug=False)
    except KeyboardInterrupt:
        logger.info("\n👋 Shutting down Fantasy Tracker...")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
