#!/usr/bin/env python3
"""
Security Middleware for Jellynouncer

This module provides security enhancements including:
- Security headers (CSP, HSTS, X-Frame-Options, etc.)
- Rate limiting with exemptions for webhook endpoints
- Fail2ban-like functionality for authentication attempts
- IP-based blocking for suspicious activity

Author: Mark Newton
Project: Jellynouncer
Version: 1.0.0
License: MIT
"""

import time
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set
from collections import defaultdict, deque
from pathlib import Path
import json
import aiosqlite
from fastapi import Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import logging

logger = logging.getLogger("jellynouncer.security")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses"""
    
    def __init__(self, app: ASGIApp, 
                 enable_hsts: bool = True,
                 enable_csp: bool = True,
                 csp_policy: Optional[str] = None):
        super().__init__(app)
        self.enable_hsts = enable_hsts
        self.enable_csp = enable_csp
        self.csp_policy = csp_policy or self._default_csp_policy()
    
    def _default_csp_policy(self) -> str:
        """Generate default Content Security Policy"""
        return (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' data: https://fonts.gstatic.com; "
            "img-src 'self' data: https: blob:; "
            "connect-src 'self' ws: wss: https:; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
    
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(), "
            "payment=(), usb=(), magnetometer=(), "
            "accelerometer=(), gyroscope=()"
        )
        
        # HSTS (only for HTTPS)
        if self.enable_hsts and request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains; preload"
            )
        
        # Content Security Policy
        if self.enable_csp:
            response.headers["Content-Security-Policy"] = self.csp_policy
        
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware with configurable limits per endpoint.
    Exempts webhook endpoints from rate limiting.
    """
    
    def __init__(self, app: ASGIApp,
                 default_limit: int = 60,
                 window_seconds: int = 60,
                 exempt_paths: Optional[List[str]] = None):
        super().__init__(app)
        self.default_limit = default_limit
        self.window_seconds = window_seconds
        self.exempt_paths = exempt_paths or ["/webhook", "/health", "/api/health"]
        self.requests: Dict[str, deque] = defaultdict(deque)
        
        # Endpoint-specific limits (per minute)
        self.endpoint_limits = {
            "/api/auth/login": 10,  # 10 login attempts per minute (still restrictive for security)
            "/api/auth/register": 5,  # 5 registrations per minute
            "/api/auth/refresh": 30,  # 30 refreshes per minute
            # Removed /api/config limit - it's now exempt and uses the general limit
        }
        
        # Start cleanup task
        asyncio.create_task(self._cleanup_old_requests())
    
    async def _cleanup_old_requests(self):
        """Periodically clean up old request records"""
        while True:
            await asyncio.sleep(60)  # Run every minute
            current_time = time.time()
            for ip in list(self.requests.keys()):
                # Remove timestamps older than window
                while self.requests[ip] and self.requests[ip][0] < current_time - self.window_seconds:
                    self.requests[ip].popleft()
                # Remove empty deques
                if not self.requests[ip]:
                    del self.requests[ip]
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP, considering proxy headers"""
        # Check for proxy headers
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take the first IP in the chain
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        # Fallback to direct connection
        if request.client:
            return request.client.host
        
        return "unknown"
    
    def _is_exempt(self, path: str) -> bool:
        """Check if path is exempt from rate limiting"""
        return any(path.startswith(exempt) for exempt in self.exempt_paths)
    
    def _get_limit_for_path(self, path: str) -> int:
        """Get rate limit for specific path"""
        for endpoint, limit in self.endpoint_limits.items():
            if path.startswith(endpoint):
                return limit
        return self.default_limit
    
    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for exempt paths
        if self._is_exempt(request.url.path):
            return await call_next(request)
        
        client_ip = self._get_client_ip(request)
        current_time = time.time()
        
        # Get limit for this endpoint
        limit = self._get_limit_for_path(request.url.path)
        
        # Add current request timestamp
        self.requests[client_ip].append(current_time)
        
        # Count requests in current window
        window_start = current_time - self.window_seconds
        request_count = sum(1 for ts in self.requests[client_ip] if ts > window_start)
        
        # Check if limit exceeded
        if request_count > limit:
            logger.warning(f"Rate limit exceeded for {client_ip} on {request.url.path}")
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "detail": "Rate limit exceeded",
                    "retry_after": self.window_seconds
                },
                headers={
                    "Retry-After": str(self.window_seconds),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(current_time + self.window_seconds))
                }
            )
        
        # Process request
        response = await call_next(request)
        
        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(limit - request_count)
        response.headers["X-RateLimit-Reset"] = str(int(current_time + self.window_seconds))
        
        return response


class Fail2BanMiddleware(BaseHTTPMiddleware):
    """
    Fail2ban-like functionality for blocking IPs after failed authentication attempts.
    Automatically bans IPs that fail authentication too many times.
    """
    
    def __init__(self, app: ASGIApp,
                 max_attempts: int = 5,
                 ban_duration_minutes: int = 30,
                 db_path: str = "data/fail2ban.db"):
        super().__init__(app)
        self.max_attempts = max_attempts
        self.ban_duration = timedelta(minutes=ban_duration_minutes)
        self.db_path = db_path
        
        # In-memory cache for performance
        self.failed_attempts: Dict[str, List[datetime]] = defaultdict(list)
        self.banned_ips: Dict[str, datetime] = {}
        
        # Initialize database
        asyncio.create_task(self._init_db())
        
        # Start cleanup task
        asyncio.create_task(self._cleanup_bans())
    
    async def _init_db(self):
        """Initialize fail2ban database"""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS failed_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ip_address TEXT NOT NULL,
                    endpoint TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    user_agent TEXT,
                    username TEXT
                )
            """)
            
            await db.execute("""
                CREATE TABLE IF NOT EXISTS ip_bans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ip_address TEXT UNIQUE NOT NULL,
                    ban_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    ban_end TIMESTAMP NOT NULL,
                    reason TEXT,
                    attempt_count INTEGER
                )
            """)
            
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_failed_ip 
                ON failed_attempts(ip_address, timestamp)
            """)
            
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_ban_ip 
                ON ip_bans(ip_address, ban_end)
            """)
            
            await db.commit()
        
        # Load active bans into memory
        await self._load_active_bans()
    
    async def _load_active_bans(self):
        """Load active bans from database into memory"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT ip_address, ban_end FROM ip_bans WHERE ban_end > ?",
                (datetime.now(timezone.utc).isoformat(),)
            )
            
            async for row in cursor:
                ip, ban_end_str = row
                self.banned_ips[ip] = datetime.fromisoformat(ban_end_str)
    
    async def _cleanup_bans(self):
        """Periodically clean up expired bans"""
        while True:
            await asyncio.sleep(60)  # Check every minute
            
            current_time = datetime.now(timezone.utc)
            
            # Clean in-memory bans
            expired_ips = [
                ip for ip, ban_end in self.banned_ips.items()
                if ban_end < current_time
            ]
            for ip in expired_ips:
                del self.banned_ips[ip]
                logger.info(f"Ban expired for IP: {ip}")
            
            # Clean old failed attempts from memory
            for ip in list(self.failed_attempts.keys()):
                self.failed_attempts[ip] = [
                    attempt for attempt in self.failed_attempts[ip]
                    if current_time - attempt < timedelta(hours=1)
                ]
                if not self.failed_attempts[ip]:
                    del self.failed_attempts[ip]
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP, considering proxy headers"""
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        if request.client:
            return request.client.host
        
        return "unknown"
    
    async def record_failed_attempt(self, request: Request, username: Optional[str] = None):
        """Record a failed authentication attempt"""
        ip = self._get_client_ip(request)
        current_time = datetime.now(timezone.utc)
        
        # Add to in-memory tracking
        self.failed_attempts[ip].append(current_time)
        
        # Record in database
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO failed_attempts 
                   (ip_address, endpoint, user_agent, username) 
                   VALUES (?, ?, ?, ?)""",
                (ip, request.url.path, 
                 request.headers.get("User-Agent", ""),
                 username)
            )
            await db.commit()
        
        # Check if should ban
        recent_attempts = [
            attempt for attempt in self.failed_attempts[ip]
            if current_time - attempt < timedelta(minutes=10)
        ]
        
        if len(recent_attempts) >= self.max_attempts:
            await self._ban_ip(ip, len(recent_attempts))
    
    async def _ban_ip(self, ip: str, attempt_count: int):
        """Ban an IP address"""
        ban_end = datetime.now(timezone.utc) + self.ban_duration
        
        # Add to in-memory cache
        self.banned_ips[ip] = ban_end
        
        # Add to database
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT OR REPLACE INTO ip_bans 
                   (ip_address, ban_end, reason, attempt_count) 
                   VALUES (?, ?, ?, ?)""",
                (ip, ban_end.isoformat(), 
                 f"Too many failed authentication attempts",
                 attempt_count)
            )
            await db.commit()
        
        logger.warning(f"IP {ip} banned until {ban_end} after {attempt_count} failed attempts")
    
    async def dispatch(self, request: Request, call_next):
        ip = self._get_client_ip(request)
        
        # Check if IP is banned
        if ip in self.banned_ips:
            ban_end = self.banned_ips[ip]
            if ban_end > datetime.now(timezone.utc):
                remaining_seconds = int((ban_end - datetime.now(timezone.utc)).total_seconds())
                logger.warning(f"Blocked request from banned IP: {ip}")
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={
                        "detail": "IP address is temporarily banned",
                        "retry_after": remaining_seconds
                    },
                    headers={
                        "Retry-After": str(remaining_seconds)
                    }
                )
            else:
                # Ban expired, remove it
                del self.banned_ips[ip]
        
        # Process request
        response = await call_next(request)
        
        # Record failed authentication attempts
        if request.url.path.startswith("/api/auth/") and response.status_code == 401:
            # Extract username from request body if available
            username = None
            if request.method == "POST":
                try:
                    # Note: Request body can only be read once, so this might not work
                    # in all cases. Consider implementing at the endpoint level instead.
                    pass
                except:
                    pass
            
            await self.record_failed_attempt(request, username)
        
        return response


# Export middleware instances for use in FastAPI app
def setup_security_middleware(app, config: Optional[Dict] = None):
    """Setup all security middleware for the application"""
    
    config = config or {}
    
    # Add security headers
    app.add_middleware(
        SecurityHeadersMiddleware,
        enable_hsts=config.get("enable_hsts", True),
        enable_csp=config.get("enable_csp", True),
        csp_policy=config.get("csp_policy")
    )
    
    # Add rate limiting
    app.add_middleware(
        RateLimitMiddleware,
        default_limit=config.get("rate_limit", 60),
        window_seconds=config.get("rate_window", 60),
        exempt_paths=config.get("exempt_paths", ["/webhook", "/health", "/api/health"])
    )
    
    # Add fail2ban
    app.add_middleware(
        Fail2BanMiddleware,
        max_attempts=config.get("max_auth_attempts", 5),
        ban_duration_minutes=config.get("ban_duration", 30),
        db_path=config.get("fail2ban_db", "data/fail2ban.db")
    )
    
    logger.info("Security middleware initialized")
    logger.info(f"Rate limiting: {config.get('rate_limit', 60)} requests per {config.get('rate_window', 60)} seconds")
    logger.info(f"Fail2ban: {config.get('max_auth_attempts', 5)} attempts before {config.get('ban_duration', 30)} minute ban")
    logger.info(f"Exempt paths: {config.get('exempt_paths', ['/webhook', '/health', '/api/health'])}")