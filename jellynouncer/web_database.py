"""
Web Database Manager - Shared module for database operations

This module provides database access for both web_api and webhook_api,
allowing webhook authentication to be checked without circular imports.
"""

import os
import sqlite3
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional
import logging

# Database path
DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
WEB_DB_PATH = DATA_DIR / "web_interface.db"

logger = logging.getLogger(__name__)


class WebDatabaseManager:
    """Manages the web interface database"""
    
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or WEB_DB_PATH
        self.initialized = False
        
    async def initialize(self):
        """Initialize database and create tables if needed"""
        if self.initialized:
            return
            
        # Ensure data directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Create tables if they don't exist
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS security_settings (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    auth_enabled BOOLEAN DEFAULT 0,
                    require_webhook_auth BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CHECK (id = 1)
                )
            """)
            
            # Insert default settings if not exists
            conn.execute("""
                INSERT OR IGNORE INTO security_settings (id, auth_enabled, require_webhook_auth) 
                VALUES (1, 0, 0)
            """)
            
            # Create notification statistics table for historical data
            conn.execute("""
                CREATE TABLE IF NOT EXISTS notification_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    hour_bucket TEXT,      -- For hourly aggregation (YYYY-MM-DD HH:00)
                    day_bucket TEXT,       -- For daily aggregation (YYYY-MM-DD)
                    notifications_sent INTEGER DEFAULT 0,
                    notifications_failed INTEGER DEFAULT 0,
                    new_items INTEGER DEFAULT 0,
                    upgraded_items INTEGER DEFAULT 0,
                    deleted_items INTEGER DEFAULT 0,
                    movies INTEGER DEFAULT 0,
                    tv_shows INTEGER DEFAULT 0,
                    episodes INTEGER DEFAULT 0,
                    music INTEGER DEFAULT 0,
                    library_scans INTEGER DEFAULT 0,
                    mass_renames_caught INTEGER DEFAULT 0,
                    avg_processing_time_ms REAL,
                    queue_size_max INTEGER DEFAULT 0
                )
            """)
            
            # Create indexes for efficient querying
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_notification_stats_hour 
                ON notification_stats(hour_bucket)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_notification_stats_day 
                ON notification_stats(day_bucket)
            """)
            
            conn.commit()
        
        self.initialized = True
        logger.info(f"Web database initialized at {self.db_path}")
    
    async def get_security_settings(self) -> Dict[str, Any]:
        """Get current security settings"""
        if not self.initialized:
            await self.initialize()
            
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM security_settings WHERE id = 1")
            settings = cursor.fetchone()
            
        if settings:
            return {
                "auth_enabled": bool(settings["auth_enabled"]),
                "require_webhook_auth": bool(settings["require_webhook_auth"])
            }
        
        return {"auth_enabled": False, "require_webhook_auth": False}
    
    async def update_security_settings(self, auth_enabled: bool, require_webhook_auth: bool):
        """Update security settings"""
        if not self.initialized:
            await self.initialize()
            
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE security_settings 
                SET auth_enabled = ?, require_webhook_auth = ?, updated_at = CURRENT_TIMESTAMP 
                WHERE id = 1
            """, (auth_enabled, require_webhook_auth))
            conn.commit()
        
        logger.info(f"Security settings updated: auth_enabled={auth_enabled}, require_webhook_auth={require_webhook_auth}")
    
    async def get_notification_stats(self, hours: int = 24) -> Dict[str, Any]:
        """Get notification statistics for the specified time period"""
        from datetime import datetime, timedelta
        
        if not self.initialized:
            await self.initialize()
        
        # Calculate time boundary
        cutoff_time = datetime.now() - timedelta(hours=hours)
        cutoff_str = cutoff_time.strftime('%Y-%m-%d %H:00')
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            # Get hourly aggregated data
            cursor = conn.execute("""
                SELECT 
                    hour_bucket,
                    SUM(notifications_sent) as sent,
                    SUM(notifications_failed) as failed,
                    SUM(new_items) as new,
                    SUM(upgraded_items) as upgraded,
                    SUM(deleted_items) as deleted,
                    SUM(movies) as movies,
                    SUM(tv_shows) as tv_shows,
                    SUM(episodes) as episodes,
                    SUM(music) as music
                FROM notification_stats
                WHERE hour_bucket >= ?
                GROUP BY hour_bucket
                ORDER BY hour_bucket DESC
                LIMIT 24
            """, (cutoff_str,))
            
            hourly_data = []
            for row in cursor.fetchall():
                hourly_data.append({
                    "hour": row["hour_bucket"],
                    "sent": row["sent"] or 0,
                    "failed": row["failed"] or 0,
                    "new": row["new"] or 0,
                    "upgraded": row["upgraded"] or 0,
                    "deleted": row["deleted"] or 0,
                    "movies": row["movies"] or 0,
                    "tv_shows": row["tv_shows"] or 0,
                    "episodes": row["episodes"] or 0,
                    "music": row["music"] or 0
                })
            
            # Get totals for the period
            cursor = conn.execute("""
                SELECT 
                    SUM(notifications_sent) as total_sent,
                    SUM(notifications_failed) as total_failed,
                    SUM(new_items) as total_new,
                    SUM(upgraded_items) as total_upgraded,
                    SUM(deleted_items) as total_deleted,
                    SUM(movies) as total_movies,
                    SUM(tv_shows) as total_tv_shows,
                    SUM(episodes) as total_episodes,
                    SUM(music) as total_music
                FROM notification_stats
                WHERE timestamp >= ?
            """, (cutoff_time,))
            
            totals_row = cursor.fetchone()
            totals = {
                "total_sent": totals_row["total_sent"] or 0 if totals_row else 0,
                "total_failed": totals_row["total_failed"] or 0 if totals_row else 0,
                "total_new": totals_row["total_new"] or 0 if totals_row else 0,
                "total_upgraded": totals_row["total_upgraded"] or 0 if totals_row else 0,
                "total_deleted": totals_row["total_deleted"] or 0 if totals_row else 0,
                "total_movies": totals_row["total_movies"] or 0 if totals_row else 0,
                "total_tv_shows": totals_row["total_tv_shows"] or 0 if totals_row else 0,
                "total_episodes": totals_row["total_episodes"] or 0 if totals_row else 0,
                "total_music": totals_row["total_music"] or 0 if totals_row else 0
            }
        
        return {
            "hourly": hourly_data,
            "totals": totals,
            "period_hours": hours
        }
    
    async def record_notification_event(self, event_type: str, item_type: str = None, success: bool = True):
        """Record a notification event for statistics"""
        from datetime import datetime
        
        if not self.initialized:
            await self.initialize()
        
        now = datetime.now()
        hour_bucket = now.strftime('%Y-%m-%d %H:00')
        day_bucket = now.strftime('%Y-%m-%d')
        
        # Determine which columns to update
        updates = {
            "hour_bucket": hour_bucket,
            "day_bucket": day_bucket,
            "notifications_sent": 1 if success else 0,
            "notifications_failed": 0 if success else 1
        }
        
        # Update type-specific counters
        if event_type == "new":
            updates["new_items"] = 1
        elif event_type == "upgraded":
            updates["upgraded_items"] = 1
        elif event_type == "deleted":
            updates["deleted_items"] = 1
        
        # Update content type counters
        if item_type:
            item_type_lower = item_type.lower()
            if "movie" in item_type_lower:
                updates["movies"] = 1
            elif "episode" in item_type_lower:
                updates["episodes"] = 1
            elif "series" in item_type_lower or "show" in item_type_lower:
                updates["tv_shows"] = 1
            elif "music" in item_type_lower or "audio" in item_type_lower:
                updates["music"] = 1
        
        # Insert or update the hourly bucket
        with sqlite3.connect(self.db_path) as conn:
            # Try to update existing record first
            cursor = conn.execute("""
                UPDATE notification_stats
                SET notifications_sent = notifications_sent + ?,
                    notifications_failed = notifications_failed + ?,
                    new_items = new_items + ?,
                    upgraded_items = upgraded_items + ?,
                    deleted_items = deleted_items + ?,
                    movies = movies + ?,
                    tv_shows = tv_shows + ?,
                    episodes = episodes + ?,
                    music = music + ?
                WHERE hour_bucket = ?
            """, (
                updates.get("notifications_sent", 0),
                updates.get("notifications_failed", 0),
                updates.get("new_items", 0),
                updates.get("upgraded_items", 0),
                updates.get("deleted_items", 0),
                updates.get("movies", 0),
                updates.get("tv_shows", 0),
                updates.get("episodes", 0),
                updates.get("music", 0),
                hour_bucket
            ))
            
            # If no rows were updated, insert a new record
            if cursor.rowcount == 0:
                conn.execute("""
                    INSERT INTO notification_stats (
                        hour_bucket, day_bucket, notifications_sent, notifications_failed,
                        new_items, upgraded_items, deleted_items,
                        movies, tv_shows, episodes, music
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    hour_bucket, day_bucket,
                    updates.get("notifications_sent", 0),
                    updates.get("notifications_failed", 0),
                    updates.get("new_items", 0),
                    updates.get("upgraded_items", 0),
                    updates.get("deleted_items", 0),
                    updates.get("movies", 0),
                    updates.get("tv_shows", 0),
                    updates.get("episodes", 0),
                    updates.get("music", 0)
                ))
            
            conn.commit()