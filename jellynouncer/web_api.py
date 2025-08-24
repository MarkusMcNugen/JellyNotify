#!/usr/bin/env python3
"""
Jellynouncer Web Interface API Server

This module provides a comprehensive web interface for managing and monitoring
the Jellynouncer service. It runs on a separate port (1985) from the main webhook
service and provides REST API endpoints for the React frontend.

Architecture:
    - FastAPI backend with async support
    - JWT-based authentication with refresh tokens
    - Separate SQLite database for web-specific data
    - Real-time statistics from the main Jellynouncer database
    - Template management with file system operations
    - Log streaming and filtering capabilities

Security Features:
    - Bcrypt password hashing
    - JWT tokens with expiration
    - CORS configuration for production
    - Rate limiting on authentication endpoints
    - Secure session management

Author: Mark Newton
Project: Jellynouncer Web Interface
Version: 1.0.0
License: MIT
"""

import os
import json
import secrets
import asyncio
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List
from contextlib import asynccontextmanager

# Third-party imports
from fastapi import FastAPI, HTTPException, Depends, Security, status, Request, File, Form, UploadFile
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
import uvicorn
from pydantic import BaseModel, Field, field_validator
import aiosqlite
import jwt
from passlib.context import CryptContext
import bcrypt

# Import Jellynouncer modules
from jellynouncer.config_models import ConfigurationValidator
from jellynouncer.utils import get_web_logger, setup_web_logging, setup_logging, get_logger
from jellynouncer.webhook_service import WebhookService
from jellynouncer.ssl_manager import SSLManager, setup_ssl_routes
from jellynouncer.security_middleware import setup_security_middleware

# Constants
WEB_DB_PATH = "data/web_interface.db"
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", secrets.token_urlsafe(32))
JWT_ALGORITHM = "HS256"
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 30
JWT_REFRESH_TOKEN_EXPIRE_DAYS = 7

# Determine log directory - use relative path for flexibility
# Works both in Docker (/app/logs) and outside (./logs)
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
if not os.path.exists(LOG_DIR):
    # Fallback to current directory logs if parent doesn't exist
    LOG_DIR = "logs"

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT token handler
security = HTTPBearer()

# Logger setup with extensive debug logging - uses separate web log file
logger = get_web_logger("jellynouncer.web_api")


# ==================== Pydantic Models ====================

class UserCreate(BaseModel):
    """Model for user creation request"""
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8)
    email: Optional[str] = None
    
    @field_validator('username')
    @classmethod
    def username_alphanumeric(cls, v):
        if not v.replace('_', '').replace('-', '').isalnum():
            raise ValueError('Username must be alphanumeric with optional _ or -')
        return v


class UserLogin(BaseModel):
    """Model for user login request"""
    username: str
    password: str


class TokenResponse(BaseModel):
    """Model for JWT token response"""
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int


class ConfigUpdate(BaseModel):
    """Model for configuration updates"""
    section: str
    key: str
    value: Any
    
    
class TemplateUpdate(BaseModel):
    """Model for template updates"""
    name: str
    content: str
    

class LogQuery(BaseModel):
    """Model for log query parameters"""
    file: str = "jellynouncer.log"
    lines: int = Field(100, le=1000)
    level: Optional[str] = None
    component: Optional[str] = None
    search: Optional[str] = None


class ClientLogEntry(BaseModel):
    """Model for individual client log entry"""
    timestamp: str
    level: str
    sessionId: str
    url: str
    message: str
    metadata: Optional[Dict[str, Any]] = {}
    userAgent: Optional[str] = None


class ClientLogBatch(BaseModel):
    """Model for batch of client logs"""
    logs: List[ClientLogEntry]
    sessionId: str
    timestamp: str


class OverviewStats(BaseModel):
    """Model for overview statistics"""
    total_items: int
    items_today: int
    items_week: int
    discord_webhooks: Dict[str, Dict[str, Any]]
    recent_notifications: List[Dict[str, Any]]
    queue_stats: Dict[str, int]
    system_health: Dict[str, Any]


# ==================== Database Manager ====================

class WebDatabaseManager:
    """Manages the web interface SQLite database"""
    
    def __init__(self, db_path: str = WEB_DB_PATH):
        self.db_path = db_path
        self.logger = get_web_logger("jellynouncer.web_db")
        self.logger.debug(f"Initializing WebDatabaseManager with path: {db_path}")
        
    async def initialize(self):
        """Initialize the web database with required tables"""
        self.logger.debug(f"Starting database initialization at {self.db_path}")
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.logger.debug(f"Ensured parent directory exists for {self.db_path}")
        
        async with aiosqlite.connect(self.db_path) as db:
            # Enable WAL mode for better concurrency
            await db.execute("PRAGMA journal_mode=WAL")
            
            # Security settings table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS security_settings (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    auth_enabled BOOLEAN DEFAULT 0,
                    require_webhook_auth BOOLEAN DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CHECK (id = 1)
                )
            """)
            
            # Users table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    is_active BOOLEAN DEFAULT 1,
                    is_admin BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP
                )
            """)
            
            # Sessions table for refresh tokens
            await db.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    refresh_token TEXT UNIQUE NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """)
            
            # Audit log table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    action TEXT NOT NULL,
                    details TEXT,
                    ip_address TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """)
            
            # Create indexes
            await db.execute("CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(refresh_token)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp)")
            
            await db.commit()
            
            # Initialize security settings if not exists
            cursor = await db.execute("SELECT COUNT(*) FROM security_settings")
            count = (await cursor.fetchone())[0]
            self.logger.debug(f"Found {count} security settings records")
            
            if count == 0:
                await db.execute("INSERT INTO security_settings (auth_enabled, require_webhook_auth) VALUES (0, 0)")
                await db.commit()
                self.logger.info("Initialized security settings with authentication disabled")
            else:
                self.logger.debug("Security settings already initialized")
    
    async def get_security_settings(self) -> Dict[str, bool]:
        """Get current security settings"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM security_settings WHERE id = 1")
            settings = await cursor.fetchone()
            
            if settings:
                return {
                    "auth_enabled": bool(settings["auth_enabled"]),
                    "require_webhook_auth": bool(settings["require_webhook_auth"])
                }
            return {"auth_enabled": False, "require_webhook_auth": False}
    
    async def update_security_settings(self, auth_enabled: bool, require_webhook_auth: bool):
        """Update security settings"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """UPDATE security_settings 
                   SET auth_enabled = ?, require_webhook_auth = ?, updated_at = CURRENT_TIMESTAMP 
                   WHERE id = 1""",
                (auth_enabled, require_webhook_auth)
            )
            await db.commit()
    
    @staticmethod
    def _generate_salt() -> str:
        """Generate a random salt for password hashing"""
        return secrets.token_hex(32)
    
    @staticmethod
    def _hash_password_with_salt(password: str, salt: str) -> str:
        """Hash password with salt using bcrypt"""
        # Combine password and salt, then hash with bcrypt
        salted_password = f"{password}{salt}".encode('utf-8')
        return bcrypt.hashpw(salted_password, bcrypt.gensalt()).decode('utf-8')
    
    @staticmethod
    def _verify_password_with_salt(password: str, salt: str, password_hash: str) -> bool:
        """Verify password against hash with salt"""
        salted_password = f"{password}{salt}".encode('utf-8')
        return bcrypt.checkpw(salted_password, password_hash.encode('utf-8'))
    
    async def create_user(self, username: str, password: str, email: Optional[str] = None, is_admin: bool = False) -> int:
        """Create a new user with salt and hash"""
        salt = self._generate_salt()
        hashed_password = self._hash_password_with_salt(password, salt)
        
        async with aiosqlite.connect(self.db_path) as db:
            try:
                cursor = await db.execute(
                    "INSERT INTO users (username, email, password_hash, salt, is_admin) VALUES (?, ?, ?, ?, ?)",
                    (username, email, hashed_password, salt, is_admin)
                )
                await db.commit()
                return cursor.lastrowid
            except aiosqlite.IntegrityError:
                raise ValueError(f"Username {username} already exists")
    
    async def verify_user(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """Verify user credentials with salt"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM users WHERE username = ? AND is_active = 1",
                (username,)
            )
            user = await cursor.fetchone()
            
            if user and self._verify_password_with_salt(password, user["salt"], user["password_hash"]):
                # Update last login
                await db.execute(
                    "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?",
                    (user["id"],)
                )
                await db.commit()
                return dict(user)
            
            return None
    
    async def update_user_password(self, user_id: int, new_password: str):
        """Update user password with new salt"""
        salt = self._generate_salt()
        hashed_password = self._hash_password_with_salt(new_password, salt)
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE users SET password_hash = ?, salt = ? WHERE id = ?",
                (hashed_password, salt, user_id)
            )
            await db.commit()
    
    async def save_refresh_token(self, user_id: int, token: str, expires_at: datetime):
        """Save refresh token to database"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO sessions (user_id, refresh_token, expires_at) VALUES (?, ?, ?)",
                (user_id, token, expires_at.isoformat())
            )
            await db.commit()
    
    async def verify_refresh_token(self, token: str) -> Optional[int]:
        """Verify refresh token and return user_id if valid"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT user_id, expires_at FROM sessions WHERE refresh_token = ?",
                (token,)
            )
            row = await cursor.fetchone()
            
            if row:
                user_id, expires_at = row
                if datetime.fromisoformat(expires_at) > datetime.now(timezone.utc):
                    return user_id
                else:
                    # Clean up expired token
                    await db.execute("DELETE FROM sessions WHERE refresh_token = ?", (token,))
                    await db.commit()
            
            return None
    
    async def log_audit(self, user_id: Optional[int], action: str, details: Optional[str], ip: Optional[str]):
        """Log an audit event"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO audit_log (user_id, action, details, ip_address) VALUES (?, ?, ?, ?)",
                (user_id, action, details, ip)
            )
            await db.commit()


# ==================== Authentication ====================

def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire.timestamp(), "type": "access"})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: Dict[str, Any]) -> str:
    """Create a JWT refresh token"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire.timestamp(), "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt


async def get_current_user_optional(credentials: Optional[HTTPAuthorizationCredentials] = Security(security)) -> Optional[Dict[str, Any]]:
    """Validate JWT token if provided, return user or None"""
    if not credentials:
        return None
        
    token = credentials.credentials
    
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        
        if payload.get("type") != "access":
            return None
        
        return payload
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


async def check_auth_required(user: Optional[Dict[str, Any]] = Depends(get_current_user_optional)) -> Optional[Dict[str, Any]]:
    """Check if authentication is required and validate user"""
    # Check if auth is enabled
    web_db = WebDatabaseManager()
    settings = await web_db.get_security_settings()
    
    if settings["auth_enabled"]:
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user
    
    # Auth not required, return None or user if provided
    return user


# ==================== Service Manager ====================

class WebInterfaceService:
    """Main service class for web interface operations"""
    
    def __init__(self, webhook_service: Optional[WebhookService] = None):
        self.webhook_service = webhook_service
        self.config = None
        self.web_db = WebDatabaseManager()
        self.ssl_manager = SSLManager(WEB_DB_PATH)
        self.logger = get_web_logger("jellynouncer.web_interface")
        self.logger.debug("Initializing WebInterfaceService")
        
        if webhook_service:
            self.logger.debug("WebhookService provided - will have access to main database")
        else:
            self.logger.debug("No WebhookService - running in standalone mode")
        
    async def initialize(self):
        """Initialize the web interface service"""
        self.logger.debug("Starting web interface service initialization")
        
        # Initialize database
        self.logger.debug("Initializing web database...")
        await self.web_db.initialize()
        self.logger.debug("Web database initialized successfully")
        
        # Initialize SSL manager
        self.logger.debug("Initializing SSL manager...")
        await self.ssl_manager.initialize()
        self.logger.debug("SSL manager initialized successfully")
        
        # Load configuration
        self.logger.debug("Loading configuration...")
        try:
            config_validator = ConfigurationValidator()
            self.config = config_validator.load_and_validate_config()
            self.logger.debug(f"Configuration loaded successfully from {config_validator.config_path if hasattr(config_validator, 'config_path') else 'default path'}")
            
            # Initialize SSL manager with config
            self.logger.debug("Initializing SSL manager with config...")
            ssl_config_obj = self.config.ssl if hasattr(self.config, 'ssl') else None
            self.ssl_manager = SSLManager(ssl_config=ssl_config_obj, db_path=WEB_DB_PATH)
            await self.ssl_manager.initialize()
            self.logger.debug("SSL manager initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to load configuration: {e}", exc_info=True)
            raise
        
        # Start periodic stats refresh task
        asyncio.create_task(self._periodic_stats_refresh())
        self.logger.info("Started periodic Jellyfin stats refresh task")
    
    async def _periodic_stats_refresh(self):
        """Periodically refresh Jellyfin stats"""
        while True:
            try:
                # Wait 30 minutes between refreshes
                await asyncio.sleep(1800)
                
                # Refresh stats
                self.logger.debug("Refreshing Jellyfin stats...")
                await self.refresh_jellyfin_stats()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in periodic stats refresh: {e}")
                # Wait 5 minutes before retry on error
                await asyncio.sleep(300)
    
    async def refresh_jellyfin_stats(self) -> Dict[str, Any]:
        """
        Refresh Jellyfin server statistics and store in database.
        
        Returns:
            Latest statistics dictionary
        """
        try:
            # Get Jellyfin stats if webhook service is available
            if self.webhook_service and self.webhook_service.jellyfin:
                stats = await self.webhook_service.jellyfin.get_server_stats()
                
                # Save to database
                if self.webhook_service.db:
                    await self.webhook_service.db.save_jellyfin_stats(stats)
                
                return stats
            else:
                # Try to get from database
                if self.webhook_service and self.webhook_service.db:
                    return await self.webhook_service.db.get_latest_jellyfin_stats()
                
            return {}
        except Exception as e:
            self.logger.error(f"Failed to refresh Jellyfin stats: {e}")
            return {}
    
    async def get_overview_stats(self) -> OverviewStats:
        """Get statistics for the overview page"""
        import psutil
        from datetime import datetime, timezone
        
        stats = {
            "total_items": 0,
            "items_today": 0,
            "items_week": 0,
            "discord_webhooks": {},
            "recent_notifications": [],
            "queue_stats": {
                "pending": 0,
                "processing": 0,
                "completed": 0,
                "failed": 0,
                "processing_rate": 0
            },
            "system_health": {
                "webhook_service": "running" if self.webhook_service else "stopped",
                "database": "connected",
                "last_sync": None,
                "database_size_mb": 0,
                "uptime_hours": 0,
                "uptime_percentage": 100,
                "cpu_usage": 0,
                "memory_usage": 0,
                "disk_usage": 0
            },
            "jellyfin_stats": None  # Will be populated from database
        }
        
        # System metrics
        try:
            # CPU and Memory
            stats["system_health"]["cpu_usage"] = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            stats["system_health"]["memory_usage"] = memory.percent
            
            # Disk usage for data directory
            data_dir = Path("data")
            if data_dir.exists():
                disk = psutil.disk_usage(str(data_dir))
                stats["system_health"]["disk_usage"] = disk.percent
                
                # Database size
                db_path = data_dir / "jellynouncer.db"
                if db_path.exists():
                    stats["system_health"]["database_size_mb"] = round(db_path.stat().st_size / (1024 * 1024), 2)
            
            # Uptime (simplified - would need proper tracking)
            stats["system_health"]["uptime_hours"] = 24  # Placeholder
            stats["system_health"]["uptime_percentage"] = 99.9  # Placeholder
            
        except Exception as e:
            self.logger.warning(f"Could not get system metrics: {e}")
        
        # Get Jellyfin stats from database
        try:
            if self.webhook_service and self.webhook_service.db:
                jellyfin_stats = await self.webhook_service.db.get_latest_jellyfin_stats()
                if jellyfin_stats:
                    # Check if stats are stale (older than 1 hour)
                    if 'last_check' in jellyfin_stats:
                        last_check = datetime.fromisoformat(jellyfin_stats['last_check'])
                        if (datetime.now(timezone.utc) - last_check).total_seconds() > 3600:
                            # Refresh stats in background
                            asyncio.create_task(self.refresh_jellyfin_stats())
                    
                    stats["jellyfin_stats"] = jellyfin_stats
                else:
                    # No stats in database, trigger refresh
                    asyncio.create_task(self.refresh_jellyfin_stats())
        except Exception as e:
            self.logger.warning(f"Could not get Jellyfin stats: {e}")
        
        # Get statistics from main database if webhook service is available
        if self.webhook_service and self.webhook_service.db:
            try:
                db_stats = await self.webhook_service.db.get_statistics()
                stats["total_items"] = db_stats.get("total_items", 0)
                stats["items_today"] = db_stats.get("items_added_today", 0)
                stats["items_week"] = db_stats.get("items_added_week", 0)
                
                # Get recent notifications
                recent = await self.webhook_service.db.get_recent_changes(limit=10)
                stats["recent_notifications"] = [
                    {
                        "id": item.get("id"),
                        "name": item.get("name", "Unknown"),
                        "type": item.get("media_type"),
                        "event": item.get("last_event"),
                        "timestamp": item.get("last_updated")
                    }
                    for item in recent
                ]
                
                # Discord webhook status
                if self.webhook_service.discord:
                    for webhook_name, webhook_url in self.webhook_service.discord.webhooks.items():
                        stats["discord_webhooks"][webhook_name] = {
                            "configured": bool(webhook_url),
                            "last_used": None,  # Would need to track this
                            "messages_sent": 0   # Would need to track this
                        }
                
            except Exception as e:
                self.logger.error(f"Failed to get database statistics: {e}")
                stats["system_health"]["database"] = "error"
        
        return OverviewStats(**stats)
    
    async def get_config(self, include_sensitive: bool = False) -> Dict[str, Any]:
        """Get current configuration"""
        if not self.config:
            validator = ConfigurationValidator()
            self.config = validator.load_and_validate_config()
        
        config_dict = self.config.model_dump()
        
        # Remove sensitive information unless requested
        if not include_sensitive:
            # Remove API keys and webhook URLs
            if "jellyfin" in config_dict:
                config_dict["jellyfin"]["api_key"] = "***HIDDEN***"
                
            if "discord" in config_dict:
                for key in config_dict["discord"]:
                    if "webhook_url" in key:
                        config_dict["discord"][key] = "***HIDDEN***" if config_dict["discord"][key] else None
            
            if "metadata_services" in config_dict:
                for service in ["omdb", "tmdb", "tvdb"]:
                    if service in config_dict["metadata_services"]:
                        if "api_key" in config_dict["metadata_services"][service]:
                            config_dict["metadata_services"][service]["api_key"] = "***HIDDEN***"
        
        return config_dict
    
    async def update_config(self, section: str, key: str, value: Any) -> bool:
        """Update configuration value"""
        config_path = Path("config/config.json")
        
        try:
            # Load current config
            with open(config_path, 'r') as f:
                config_data = json.load(f)
            
            # Update the value
            if section not in config_data:
                config_data[section] = {}
            
            config_data[section][key] = value
            
            # Validate the new configuration using Pydantic model
            from jellynouncer.config_models import AppConfig
            validated_config = AppConfig(**config_data)
            
            # Save the updated config
            with open(config_path, 'w') as f:
                json.dump(config_data, f, indent=2)
            
            # Update in-memory config
            self.config = validated_config
            
            self.logger.info(f"Updated config: {section}.{key}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to update config: {e}")
            raise ValueError(f"Configuration update failed: {str(e)}")
    
    @staticmethod
    async def get_templates() -> List[Dict[str, Any]]:
        """Get list of available templates"""
        templates_dir = Path("templates")
        templates = []
        
        for template_file in templates_dir.glob("*.j2"):
            # Read template metadata from first line comment if available
            with open(template_file, 'r') as f:
                _ = f.read()  # Read to check file is accessible but content not needed here
                
            templates.append({
                "name": template_file.stem,
                "filename": template_file.name,
                "size": template_file.stat().st_size,
                "modified": template_file.stat().st_mtime,
                "is_default": not template_file.stem.startswith("custom_")
            })
        
        return sorted(templates, key=lambda x: x["name"])
    
    @staticmethod
    async def get_template_content(name: str) -> str:
        """Get template content"""
        template_path = Path(f"templates/{name}.j2")
        
        if not template_path.exists():
            raise ValueError(f"Template {name} not found")
        
        with open(template_path, 'r') as f:
            return f.read()
    
    async def save_template(self, name: str, content: str) -> bool:
        """Save template content"""
        # Ensure custom templates are prefixed
        if not name.startswith("custom_") and not Path(f"templates/{name}.j2").exists():
            name = f"custom_{name}"
        
        template_path = Path(f"templates/{name}.j2")
        
        try:
            # Validate Jinja2 syntax
            from jinja2 import Environment, TemplateSyntaxError
            env = Environment()
            try:
                env.parse(content)
            except TemplateSyntaxError as e:
                raise ValueError(f"Invalid Jinja2 syntax: {str(e)}")
            
            # Save the template
            with open(template_path, 'w') as f:
                f.write(content)
            
            self.logger.info(f"Saved template: {name}")
            return True
            
        except ValueError:
            raise  # Re-raise validation errors
        except Exception as e:
            self.logger.error(f"Failed to save template: {e}")
            raise
    
    async def restore_default_template(self, name: str) -> bool:
        """Restore a template to its default content"""
        # This would need the original templates stored somewhere
        # For now, we'll just indicate this needs implementation
        raise NotImplementedError("Default template restoration not yet implemented")
    
    async def get_logs(self, query: LogQuery) -> List[Dict[str, Any]]:
        """Get log entries based on query parameters"""
        # Use the configured log directory
        log_path = Path(LOG_DIR) / query.file
        self.logger.debug(f"Attempting to read log file: {log_path}")
        
        if not log_path.exists():
            self.logger.warning(f"Log file not found: {log_path}")
            # Try alternative paths
            alt_paths = [
                Path("logs") / query.file,
                Path("/app/logs") / query.file,
                Path("../logs") / query.file
            ]
            for alt_path in alt_paths:
                self.logger.debug(f"Trying alternative path: {alt_path}")
                if alt_path.exists():
                    log_path = alt_path
                    self.logger.debug(f"Found log file at: {log_path}")
                    break
            else:
                raise ValueError(f"Log file {query.file} not found in any standard location")
        
        logs = []
        
        try:
            with open(log_path, 'r') as f:
                # Read last N lines
                lines = f.readlines()[-query.lines:]
                
                for line in lines:
                    # Parse log line (format: timestamp - level - component - message)
                    parts = line.strip().split(' - ', 3)
                    
                    if len(parts) >= 4:
                        log_entry = {
                            "timestamp": parts[0],
                            "level": parts[1],
                            "component": parts[2],
                            "message": parts[3]
                        }
                        
                        # Apply filters
                        if query.level and log_entry["level"] != query.level:
                            continue
                        if query.component and query.component not in log_entry["component"]:
                            continue
                        if query.search and query.search.lower() not in line.lower():
                            continue
                        
                        logs.append(log_entry)
                
        except Exception as e:
            self.logger.error(f"Failed to read logs: {e}")
            raise
        
        return logs


# ==================== FastAPI Application ====================

# Global service instance
web_service = WebInterfaceService()

@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    """Manage application lifecycle"""
    # Initialize logging first (with colors)
    log_level = os.environ.get("LOG_LEVEL", "INFO")
    log_dir = os.environ.get("LOG_DIR", "/app/logs")
    if not os.path.exists('/.dockerenv'):
        log_dir = "logs"
    
    setup_logging(log_level, log_dir)
    
    # Re-get the logger to ensure it has the colored formatter
    global logger
    logger = get_logger("jellynouncer.web_api")
    
    # Startup
    logger.info("Starting Jellynouncer Web Interface...")
    logger.info(f"Web logs will be written to {log_dir}/jellynouncer-web.log")
    await web_service.initialize()
    
    # Setup SSL routes
    await setup_ssl_routes(app_instance, web_service.ssl_manager)
    
    # Try to connect to webhook service if available
    # This would be passed in from main.py when both services run together
    
    # Check SSL configuration
    ssl_settings = await web_service.ssl_manager.get_ssl_settings()
    if ssl_settings.get("ssl_enabled"):
        logger.info(f"SSL enabled on port {ssl_settings.get('port', 9000)}")
    else:
        logger.info("Web interface ready on port 1985 (HTTP)")
    
    yield
    
    # Shutdown
    logger.info("Shutting down web interface...")


# Create FastAPI app
app = FastAPI(
    title="Jellynouncer Web Interface",
    description="Web management interface for Jellynouncer",
    version="1.0.0",
    lifespan=lifespan
)

# Setup security middleware - must be done immediately after app creation
security_config = {
    "rate_limit": 60,
    "rate_window": 60,
    "max_auth_attempts": 5,
    "ban_duration": 30,
    "exempt_paths": ["/webhook", "/health", "/api/health", "/api/auth/status"],
    "enable_hsts": True,
    "enable_csp": True
}
setup_security_middleware(app, security_config)

# Request/Response logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all HTTP requests and responses with extensive debug information"""
    import time
    start_time = time.time()
    
    # Generate request ID for tracking
    request_id = secrets.token_hex(8)
    
    # Log incoming request with detailed information
    logger.debug(f"[{request_id}] Incoming request: {request.method} {request.url.path}")
    logger.debug(f"[{request_id}] Client: {request.client.host if request.client else 'unknown'}")
    logger.debug(f"[{request_id}] Headers: {dict(request.headers)}")
    logger.debug(f"[{request_id}] Query params: {dict(request.query_params)}")
    
    # Log request body for POST/PUT/PATCH (be careful with sensitive data)
    if request.method in ["POST", "PUT", "PATCH"]:
        # Don't log auth endpoints bodies (contains passwords)
        if "/auth/" not in request.url.path:
            try:
                body = await request.body()
                if body:
                    logger.debug(f"[{request_id}] Request body size: {len(body)} bytes")
                    # Only log small bodies to avoid cluttering logs
                    if len(body) < 1000:
                        try:
                            body_json = json.loads(body)
                            # Mask sensitive fields
                            if "password" in body_json:
                                body_json["password"] = "***MASKED***"
                            if "api_key" in body_json:
                                body_json["api_key"] = "***MASKED***"
                            logger.debug(f"[{request_id}] Request body: {json.dumps(body_json, indent=2)}")
                        except json.JSONDecodeError:
                            logger.debug(f"[{request_id}] Request body (non-JSON): {body[:200]}...")
                # Need to recreate the request body stream
                from starlette.datastructures import Headers
                from starlette.requests import Request as StarletteRequest
                request = StarletteRequest(request.scope, request.receive)
                request._body = body
            except Exception as e:
                logger.debug(f"[{request_id}] Could not read request body: {e}")
    
    # Process the request
    try:
        response = await call_next(request)
    except Exception as e:
        # Log any unhandled exceptions
        logger.error(f"[{request_id}] Unhandled exception: {e}", exc_info=True)
        raise
    
    # Calculate processing time
    process_time = time.time() - start_time
    
    # Log response
    logger.debug(f"[{request_id}] Response status: {response.status_code}")
    logger.debug(f"[{request_id}] Processing time: {process_time:.3f}s")
    
    # Add custom headers for debugging
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time"] = str(process_time)
    
    # Log response details based on status code
    if response.status_code >= 400:
        logger.warning(f"[{request_id}] Error response: {response.status_code} for {request.method} {request.url.path}")
    elif response.status_code >= 300:
        logger.debug(f"[{request_id}] Redirect response: {response.status_code}")
    else:
        logger.debug(f"[{request_id}] Success response: {response.status_code}")
    
    return response

# Configure CORS - Allow all origins by default for local/Docker deployments
# This avoids authentication issues when accessing from different IPs
# In production, you can restrict origins via environment variable
allowed_origins = ["*"]  # Allow all origins by default

# Allow restricting origins via environment variable if needed
custom_origins = os.environ.get("JELLYNOUNCER_ALLOWED_ORIGINS", "")
if custom_origins and custom_origins != "*":
    # If specific origins are set, use them instead
    allowed_origins = [origin.strip() for origin in custom_origins.split(",")]
    logger.info(f"CORS restricted to origins: {allowed_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add trusted host middleware for security
if os.environ.get("JELLYNOUNCER_PRODUCTION"):
    allowed_hosts = os.environ.get("JELLYNOUNCER_ALLOWED_HOSTS", "").split(",")
    if allowed_hosts:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
        logger.info(f"Trusted host middleware enabled with hosts: {allowed_hosts}")
else:
    logger.debug("Running in development mode - trusted host middleware disabled")

# Prepare static file path for later mounting (after API routes)
web_dist_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web", "dist")


# ==================== API Endpoints ====================

@app.post("/api/auth/login", response_model=TokenResponse)
async def login(user_login: UserLogin, request: Request):
    """Authenticate user and return JWT tokens"""
    user = await web_service.web_db.verify_user(user_login.username, user_login.password)
    
    if not user:
        # Log failed attempt
        await web_service.web_db.log_audit(
            None, "login_failed", f"Username: {user_login.username}", 
            request.client.host
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )
    
    # Create tokens
    access_token = create_access_token({"user_id": user["id"], "username": user["username"]})
    user_refresh_token = create_refresh_token({"user_id": user["id"]})
    
    # Save refresh token
    expires_at = datetime.now(timezone.utc) + timedelta(days=JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    await web_service.web_db.save_refresh_token(user["id"], user_refresh_token, expires_at)
    
    # Log successful login
    await web_service.web_db.log_audit(
        user["id"], "login_success", None, request.client.host
    )
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=user_refresh_token,
        expires_in=JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@app.post("/api/auth/refresh", response_model=TokenResponse)
async def refresh_token(token_string: str):
    """Refresh access token using refresh token"""
    user_id = await web_service.web_db.verify_refresh_token(token_string)
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )
    
    # Get user details
    async with aiosqlite.connect(WEB_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT username FROM users WHERE id = ?", (user_id,))
        user = await cursor.fetchone()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    
    # Create new access token
    access_token = create_access_token({"user_id": user_id, "username": user["username"]})
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=token_string,  # Return same refresh token
        expires_in=JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@app.get("/api/auth/status")
async def get_auth_status():
    """Get authentication status (no auth required)"""
    logger.debug("Auth status check requested")
    settings = await web_service.web_db.get_security_settings()
    logger.debug(f"Returning auth status: auth_enabled={settings.get('auth_enabled', False)}")
    return settings


@app.post("/api/auth/setup")
async def setup_authentication(user_create: UserCreate):
    """Initial authentication setup - only works when no users exist"""
    # Check if any users exist
    async with aiosqlite.connect(WEB_DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM users")
        user_count = (await cursor.fetchone())[0]
    
    if user_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authentication already configured. Use login endpoint."
        )
    
    try:
        # Create the first admin user
        user_id = await web_service.web_db.create_user(
            user_create.username,
            user_create.password,
            user_create.email,
            is_admin=True
        )
        
        # Enable authentication
        await web_service.web_db.update_security_settings(auth_enabled=True, require_webhook_auth=False)
        
        # Create tokens for immediate login
        access_token = create_access_token({"user_id": user_id, "username": user_create.username})
        new_refresh_token = create_refresh_token({"user_id": user_id})
        
        # Save refresh token
        expires_at = datetime.now(timezone.utc) + timedelta(days=JWT_REFRESH_TOKEN_EXPIRE_DAYS)
        await web_service.web_db.save_refresh_token(user_id, new_refresh_token, expires_at)
        
        return {
            "message": "Authentication configured successfully",
            "access_token": access_token,
            "refresh_token": new_refresh_token,
            "expires_in": JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
        }
        
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.put("/api/auth/settings")
async def update_auth_settings(
    auth_enabled: bool,
    require_webhook_auth: bool,
    current_user: Optional[Dict] = Depends(check_auth_required)
):
    """Update authentication settings"""
    # If disabling auth, ensure user is authenticated
    settings = await web_service.web_db.get_security_settings()
    
    if settings["auth_enabled"] and not auth_enabled:
        # Trying to disable auth - must be authenticated
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Must be authenticated to disable authentication"
            )
    
    await web_service.web_db.update_security_settings(auth_enabled, require_webhook_auth)
    
    if current_user:
        await web_service.web_db.log_audit(
            current_user.get("user_id"),
            "auth_settings_updated",
            f"Auth enabled: {auth_enabled}, Webhook auth: {require_webhook_auth}",
            None
        )
    
    return {"message": "Security settings updated", "auth_enabled": auth_enabled, "require_webhook_auth": require_webhook_auth}


@app.post("/api/auth/register", status_code=status.HTTP_201_CREATED)
async def register(user_create: UserCreate, current_user: Optional[Dict] = Depends(check_auth_required)):
    """Register a new user (requires auth if enabled)"""
    # Check if auth is enabled
    settings = await web_service.web_db.get_security_settings()
    
    if settings["auth_enabled"] and not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required to create users"
        )
    
    try:
        user_id = await web_service.web_db.create_user(
            user_create.username, 
            user_create.password,
            user_create.email
        )
        
        if current_user:
            await web_service.web_db.log_audit(
                current_user.get("user_id"), 
                "user_created", 
                f"Created user: {user_create.username}",
                None
            )
        
        return {"message": "User created successfully", "user_id": user_id}
        
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/api/overview", response_model=OverviewStats)
async def get_overview(current_user: Optional[Dict] = Depends(check_auth_required)):
    """Get overview statistics"""
    return await web_service.get_overview_stats()


@app.get("/api/config")
async def get_config(current_user: Optional[Dict] = Depends(check_auth_required)):
    """Get current configuration"""
    return await web_service.get_config(include_sensitive=False)


@app.put("/api/config")
async def update_config(
    config_update: ConfigUpdate, 
    current_user: Optional[Dict] = Depends(check_auth_required)
):
    """Update configuration value"""
    try:
        success = await web_service.update_config(
            config_update.section,
            config_update.key,
            config_update.value
        )
        
        if current_user:
            await web_service.web_db.log_audit(
                current_user.get("user_id"),
                "config_updated",
                f"Updated {config_update.section}.{config_update.key}",
                None
            )
        
        return {"success": success, "message": "Configuration updated"}
        
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/api/templates")
async def get_templates(current_user: Optional[Dict] = Depends(check_auth_required)):
    """Get list of available templates"""
    return await web_service.get_templates()


@app.get("/api/templates/{name}")
async def get_template(name: str, current_user: Optional[Dict] = Depends(check_auth_required)):
    """Get template content"""
    try:
        content = await web_service.get_template_content(name)
        return {"name": name, "content": content}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@app.put("/api/templates/{name}")
async def update_template(
    name: str,
    template_update: TemplateUpdate,
    current_user: Optional[Dict] = Depends(check_auth_required)
):
    """Update or create template"""
    try:
        success = await web_service.save_template(name, template_update.content)
        
        if current_user:
            await web_service.web_db.log_audit(
                current_user.get("user_id"),
                "template_updated",
                f"Updated template: {name}",
                None
            )
        
        return {"success": success, "message": "Template saved"}
        
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/api/templates/{name}/restore")
async def restore_template(name: str, current_user: Optional[Dict] = Depends(check_auth_required)):
    """Restore template to default"""
    try:
        success = await web_service.restore_default_template(name)
        
        if current_user:
            await web_service.web_db.log_audit(
                current_user.get("user_id"),
                "template_restored",
                f"Restored template: {name}",
                None
            )
        
        return {"success": success, "message": "Template restored"}
        
    except NotImplementedError as e:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/api/logs")
async def get_logs(log_query: LogQuery, current_user: Optional[Dict] = Depends(check_auth_required)):
    """Get log entries"""
    try:
        logs = await web_service.get_logs(log_query)
        return {"logs": logs, "count": len(logs)}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.post("/api/logs/client")
async def receive_client_logs(log_batch: ClientLogBatch):
    """
    Receive and process client-side logs from the React frontend.
    
    This endpoint accepts batched logs from the browser and writes them
    to the main jellynouncer.log file with proper formatting to distinguish
    them from server-side logs.
    
    Client logs are written with a [CLIENT] prefix and include session ID
    for correlation with user sessions.
    
    Note: This endpoint doesn't require authentication to ensure critical
    error logs can always be sent.
    """
    try:
        client_logger = get_web_logger("jellynouncer.web_client")
        
        # Process each log entry
        for log_entry in log_batch.logs:
            # Format the client log message with session context
            formatted_message = f"[CLIENT] [{log_entry.sessionId[:8]}] {log_entry.url} - {log_entry.message}"
            
            # Add metadata if present
            if log_entry.metadata:
                formatted_message += f" | Metadata: {json.dumps(log_entry.metadata)}"
            
            # Log at appropriate level
            level = log_entry.level.upper()
            if level == "DEBUG":
                client_logger.debug(formatted_message)
            elif level == "INFO":
                client_logger.info(formatted_message)
            elif level == "WARN" or level == "WARNING":
                client_logger.warning(formatted_message)
            elif level == "ERROR":
                client_logger.error(formatted_message)
            else:
                # Default to info for unknown levels
                client_logger.info(formatted_message)
        
        # Log batch summary at debug level
        client_logger.debug(f"Processed {len(log_batch.logs)} client logs from session {log_batch.sessionId[:8]}")
        
        return {
            "success": True,
            "processed": len(log_batch.logs),
            "sessionId": log_batch.sessionId
        }
        
    except Exception as e:
        logger.error(f"Failed to process client logs: {e}", exc_info=True)
        # Still return success to prevent client from retrying
        # We don't want logging failures to impact the client
        return {
            "success": False,
            "error": "Failed to process logs",
            "processed": 0
        }


@app.get("/api/health")
async def health_check():
    """Health check endpoint (no auth required)"""
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "Jellynouncer Web Interface"
    }


# ==================== SSL Certificate Management ====================

@app.post("/api/ssl/upload")
async def upload_ssl_file(
    file: UploadFile = File(...),
    type: str = Form(...),
    current_user: Optional[Dict] = Depends(check_auth_required)
):
    """Upload SSL certificate or key file"""
    try:
        from pathlib import Path
        
        # Validate file type
        if type not in ["cert", "key"]:
            raise HTTPException(status_code=400, detail="Invalid file type")
        
        # Create SSL directory if it doesn't exist
        ssl_dir = Path(web_service.config.server.data_dir) / "ssl"
        ssl_dir.mkdir(parents=True, exist_ok=True)
        
        # Determine file extension
        file_ext = ".crt" if type == "cert" else ".key"
        file_path = ssl_dir / f"{type}{file_ext}"
        
        # Save the file
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
        
        # Update configuration
        if type == "cert":
            await web_service.update_config("web_interface", "ssl_cert_path", str(file_path))
        else:
            await web_service.update_config("web_interface", "ssl_key_path", str(file_path))
        
        logger.info(f"SSL {type} file uploaded to {file_path}")
        
        return {"status": "success", "path": str(file_path)}
        
    except Exception as e:
        logger.error(f"Failed to upload SSL file: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/ssl/generate-csr")
async def generate_csr_endpoint(
    csr_data: Dict[str, Any],
    current_user: Optional[Dict] = Depends(check_auth_required)
):
    """Generate a Certificate Signing Request"""
    try:
        # Extract CSR parameters
        common_name = csr_data.get("commonName", "localhost")
        country = csr_data.get("country", "US")
        state = csr_data.get("state", "State")
        locality = csr_data.get("locality", "City")
        organization = csr_data.get("organization", "Organization")
        organizational_unit = csr_data.get("organizationalUnit", "IT")
        email = csr_data.get("email")
        san_list = csr_data.get("sanList", [])
        
        # Generate CSR using SSL manager
        result = await web_service.ssl_manager.create_csr_request(
            common_name=common_name,
            country=country,
            state=state,
            locality=locality,
            organization=organization,
            organizational_unit=organizational_unit,
            email=email,
            san_list=san_list if san_list else None
        )
        
        logger.info(f"Generated CSR for {common_name}")
        
        return {
            "status": "success",
            "csr": result["csr"],
            "private_key_path": result["private_key_path"]
        }
        
    except Exception as e:
        logger.error(f"Failed to generate CSR: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/ssl/generate-self-signed")
async def generate_self_signed_cert(
    cert_data: Dict[str, Any],
    current_user: Optional[Dict] = Depends(check_auth_required)
):
    """Generate a self-signed certificate"""
    try:
        from pathlib import Path
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from datetime import datetime, timedelta
        
        # Extract certificate parameters
        common_name = cert_data.get("commonName", "localhost")
        days = cert_data.get("days", 365)
        
        # Generate private key
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )
        
        # Generate certificate
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ])
        
        cert = x509.CertificateBuilder().subject_name(
            subject
        ).issuer_name(
            issuer
        ).public_key(
            private_key.public_key()
        ).serial_number(
            x509.random_serial_number()
        ).not_valid_before(
            datetime.now(timezone.utc)
        ).not_valid_after(
            datetime.now(timezone.utc) + timedelta(days=days)
        ).add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName(common_name),
                x509.DNSName("localhost"),
            ]),
            critical=False,
        ).sign(private_key, hashes.SHA256())
        
        # Save certificate and key
        ssl_dir = Path(web_service.config.server.data_dir) / "ssl"
        ssl_dir.mkdir(parents=True, exist_ok=True)
        
        cert_path = ssl_dir / "self_signed.crt"
        key_path = ssl_dir / "self_signed.key"
        
        # Write certificate
        with open(cert_path, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
        
        # Write private key
        with open(key_path, "wb") as f:
            f.write(private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            ))
        
        # Update configuration
        await web_service.update_config("web_interface", "ssl_cert_path", str(cert_path))
        await web_service.update_config("web_interface", "ssl_key_path", str(key_path))
        await web_service.update_config("web_interface", "ssl_enabled", True)
        
        logger.info(f"Generated self-signed certificate for {common_name}")
        
        return {
            "status": "success",
            "cert_path": str(cert_path),
            "key_path": str(key_path),
            "valid_days": days
        }
        
    except Exception as e:
        logger.error(f"Failed to generate self-signed certificate: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Mount static files AFTER all API routes to serve the React frontend
# This way API routes take precedence, and everything else serves the SPA
if os.path.exists(web_dist_path):
    logger.info(f"Serving static files from {web_dist_path}")
    # First mount the assets directory specifically to avoid MIME type issues
    assets_path = os.path.join(web_dist_path, "assets")
    if os.path.exists(assets_path):
        app.mount("/assets", StaticFiles(directory=assets_path), name="assets")
    # Then mount the root for HTML and other static files
    app.mount("/", StaticFiles(directory=web_dist_path, html=True), name="static")
else:
    logger.warning(f"Web interface build not found at {web_dist_path}")
    logger.warning("The React frontend needs to be built first. Run 'npm run build' in the web directory.")
    
    # Add a fallback route that returns instructions
    @app.get("/")
    async def web_ui_not_built():
        return JSONResponse(
            status_code=503,
            content={
                "error": "Web interface not built",
                "message": "The web interface needs to be built before it can be served.",
                "instructions": [
                    "1. Navigate to the 'web' directory",
                    "2. Run 'npm install' to install dependencies",
                    "3. Run 'npm run build' to build the production files",
                    "4. Restart the Jellynouncer service"
                ],
                "api_status": "The API endpoints are still available at /api/*"
            }
        )


# ==================== Main Entry Point ====================

async def get_ssl_config():
    """Get SSL configuration for server startup"""
    ssl_manager = SSLManager(WEB_DB_PATH)
    await ssl_manager.initialize()
    settings = await ssl_manager.get_ssl_settings()
    
    if settings.get("ssl_enabled"):
        context = ssl_manager.create_ssl_context(settings)
        if context:
            return {
                "ssl_keyfile": None,  # Handled by context
                "ssl_certfile": None,  # Handled by context
                "ssl_context": context,
                "port": settings.get("port", 9000)
            }
    
    return {"port": 1985}


if __name__ == "__main__":
    import asyncio
    
    # Get SSL configuration
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    ssl_config = loop.run_until_complete(get_ssl_config())
    
    # Run the web interface server
    uvicorn.run(
        "jellynouncer.web_api:app",
        host="0.0.0.0",
        port=ssl_config.get("port", 1985),
        ssl_keyfile=ssl_config.get("ssl_keyfile"),
        ssl_certfile=ssl_config.get("ssl_certfile"),
        reload=os.environ.get("JELLYNOUNCER_DEV_MODE") == "true" and not ssl_config.get("ssl_context")
    )