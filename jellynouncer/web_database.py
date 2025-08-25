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