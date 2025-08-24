#!/usr/bin/env python3
"""
Jellynouncer Discord Webhook Service

This module provides a comprehensive intermediate webhook service that sits between Jellyfin
media server and Discord, enabling intelligent notifications for new media additions and
quality upgrades.

Architecture Overview:
    The service follows a modular, async-first design with clear separation of concerns:

    1. Configuration Layer (Pydantic Models):
       - Type-safe configuration with validation using Pydantic v2
       - Environment variable overrides for Docker deployments
       - Nested configuration structures for organized settings

    2. Data Layer (DatabaseManager):
       - SQLite with WAL mode for concurrent access (multiple readers, single writer)
       - Content hashing for change detection to avoid duplicate notifications
       - Batch operations for performance during library syncs

    3. Integration Layer (JellyfinAPI, DiscordNotifier):
       - Jellyfin API client with retry logic for network resilience
       - Discord webhook with rate limiting to respect Discord's API limits
       - Template-based message formatting using Jinja2 templates

    4. Logic Layer (ChangeDetector, WebhookService):
       - Intelligent change detection (resolution upgrades, codec improvements, audio enhancements, HDR)
       - Webhook routing based on content type (movies vs TV shows vs music)
       - Background sync and maintenance tasks using asyncio

    5. API Layer (FastAPI):
       - RESTful endpoints for webhook processing from Jellyfin
       - Health checks and diagnostics for monitoring
       - Debug endpoints for troubleshooting and development

Key Features:
    - Smart change detection (new vs. upgraded content)
    - Multi-webhook routing (separate channels for movies, TV, music)
    - Rate limiting and error recovery to handle network issues
    - Background library synchronization to catch missed webhooks
    - Template-based Discord embeds for rich media information
    - Comprehensive logging and monitoring for production deployment

Example Usage:
    This service is designed to run as a Docker container with environment variables
    for configuration:

    ```bash
    # Set required environment variables
    export JELLYFIN_SERVER_URL="http://jellyfin:8096"
    export JELLYFIN_API_KEY="your_api_key_here"
    export JELLYFIN_USER_ID="your_user_id_here"
    export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."

    # Run the service
    python main.py
    ```

Dependencies:
    - FastAPI: Modern async web framework for the API layer
    - aiohttp: Async HTTP client for Discord webhooks and external API calls
    - aiosqlite: Async SQLite database operations to avoid blocking the event loop
    - Pydantic: Data validation and configuration management with Python type hints
    - Jinja2: Template engine for Discord embed formatting
    - jellyfin-apiclient-python: Official Jellyfin API client

Author: Mark Newton
Project: Jellynouncer
Version: 2.0.0
License: MIT
"""

import os
import asyncio
import time
import json
import signal
import sys
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Dict, Any, Optional

# Third-party imports for async web framework and HTTP operations
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import uvicorn
from pydantic import ValidationError

# Import our custom modules
from jellynouncer.webhook_models import WebhookPayload
from jellynouncer.webhook_service import WebhookService
from jellynouncer.config_models import ConfigurationValidator
from jellynouncer.utils import setup_logging, get_logger
from jellynouncer.network_utils import log_jellynouncer_startup

# Global service instance - shared across the FastAPI application
# This pattern allows us to initialize the service once during startup
# and reuse it across all request handlers
webhook_service: Optional[WebhookService] = None


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    """
    Async context manager for FastAPI application lifespan management.

    This function handles the complete lifecycle of the Jellynouncer application,
    including startup initialization and graceful shutdown procedures. It uses
    Python's async context manager pattern to ensure proper resource management.

    The lifespan pattern is the modern FastAPI way to handle startup/shutdown,
    replacing the deprecated @app.on_event("startup") decorators.

    Args:
        app_instance: The FastAPI application instance

    Yields:
        None: Control is yielded back to FastAPI to handle requests

    Raises:
        SystemExit: If critical initialization fails, the application will exit

    Example:
        This function is automatically called by FastAPI when the application
        starts and stops:

        ```python
        app = FastAPI(lifespan=lifespan)
        # FastAPI automatically calls lifespan on startup/shutdown
        ```

    Note:
        All code before the `yield` statement runs during application startup.
        All code after the `yield` statement runs during application shutdown.
        This ensures proper resource cleanup even if the application crashes.
    """
    global webhook_service

    # Initialize logger early so it's available in exception handlers
    logger = None

    # === STARTUP PHASE ===
    # This code runs when the FastAPI application starts

    try:
        # Initialize logging first so we can log any errors during startup
        # The setup_logging function creates both console and file handlers

        # This ensures environment variables can override config file settings
        validator = ConfigurationValidator()
        app_config = None
        app_log_level = "INFO"  # Default fallback

        try:
            # Try to load full configuration
            app_config = validator.load_and_validate_config()
            app_log_level = app_config.server.log_level
        except Exception as config_error:
            # If config loading fails, fall back to environment variable or default
            app_log_level = os.getenv("LOG_LEVEL", app_config.server.log_level if app_config else "INFO")
            # Use print since logging isn't set up yet
            print(f"Warning: Could not load config for log level, using {app_log_level}: {config_error}")

        # Initialize logging with the determined log level
        # The setup_logging function creates both console and file handlers
        logger = setup_logging(
            log_level=app_log_level,
            log_dir=os.getenv("LOG_DIR", app_config.server.log_dir if app_config else "/app/logs")
        )
        logger.info("Starting Jellynouncer service initialization...")
        # Log which source provided the log level for debugging
        logger.debug(f"Log level '{app_log_level}' determined from configuration system")

        # Create and initialize the main webhook service
        # This handles all the complex business logic and integrations
        webhook_service = WebhookService()
        await webhook_service.initialize()

        # Start background tasks for maintenance and monitoring
        # These tasks run continuously to sync with Jellyfin and maintain the database
        background_task = asyncio.create_task(webhook_service.background_tasks())

        # Get port from same config system used by uvicorn
        if app_config:
            service_port = int(os.getenv("PORT", str(app_config.server.port)))
        else:
            service_port = int(os.getenv("PORT", 1984))

        log_jellynouncer_startup(port=service_port, logger=logger)

        # Yield control back to FastAPI to start serving requests
        # Everything after this yield runs during shutdown
        yield

    except Exception as e:
        # Use logger if available, otherwise fall back to print
        if logger:
            logger.error(f"Failed to start Jellynouncer: {e}", exc_info=True)
        else:
            print(f"Failed to start Jellynouncer (logging not initialized): {e}")
            import traceback
            traceback.print_exc()
        raise SystemExit(f"Service startup failed: {e}")

    # === SHUTDOWN PHASE ===
    # This code runs when the FastAPI application stops

    try:
        if logger:
            logger.info("Starting graceful shutdown...")
        else:
            print("Starting graceful shutdown...")

        if webhook_service:
            # Cancel background tasks
            if 'background_task' in locals():
                background_task.cancel()
                try:
                    await background_task
                except asyncio.CancelledError:
                    pass

            # Clean up service resources
            await webhook_service.cleanup()

        if logger:
            logger.info("Jellynouncer shutdown completed successfully")
        else:
            print("Jellynouncer shutdown completed successfully")

    except Exception as e:
        if logger:
            logger.error(f"Error during shutdown: {e}", exc_info=True)
        else:
            print(f"Error during shutdown: {e}")
            import traceback
            traceback.print_exc()


# Create FastAPI application with lifespan management
app = FastAPI(
    title="Jellynouncer",
    description="Intermediary Discord webhook service for Jellyfin media notifications",
    version="2.0.0",
    lifespan=lifespan
)

# Configure CORS to allow the web interface to access this service
# Using ["*"] allows all origins - you can restrict this to specific origins if needed
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for simplicity
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/webhook")
async def receive_webhook(request: Request):
    """
    Main webhook endpoint for receiving notifications from Jellyfin.

    This endpoint processes incoming webhooks from Jellyfin's webhook plugin
    and triggers the appropriate notification workflow. It validates the
    payload format and handles the complete notification pipeline.
    
    When LOG_LEVEL is set to DEBUG, provides comprehensive request analysis
    including headers, body content, and field-by-field validation.

    Args:
        request (Request): FastAPI request object containing the webhook data

    Returns:
        dict: Processing result with status and details

    Raises:
        HTTPException: If service is not ready or processing fails

    Example:
        Jellyfin webhook plugin should be configured to send POST requests to:
        `http://your-jellynouncer-server:PORT/webhook`

        Default port is 1984, but can be configured via PORT environment variable
        or config file server.port setting.

        Example webhook payload:
        ```json
        {
            "ItemId": "abc123",
            "Name": "The Matrix",
            "ItemType": "Movie",
            "NotificationType": "library.new"
        }
        ```
    """
    if webhook_service is None:
        raise HTTPException(
            status_code=503,
            detail="Service not ready - still initializing"
        )

    try:
        # Get raw body once - we'll use it for both debug logging and parsing
        raw_body = await request.body()
        
        # Parse the webhook payload
        try:
            json_data = json.loads(raw_body)
            payload = WebhookPayload(**json_data)
        except (json.JSONDecodeError, ValidationError) as e:
            webhook_service.logger.error(f"Failed to parse webhook payload: {e}")
            raise HTTPException(
                status_code=400,
                detail=f"Invalid webhook payload: {str(e)}"
            )
        
        # Debug logging when enabled
        if webhook_service.logger.isEnabledFor(logging.DEBUG):
            
            # Get client information
            client_info = getattr(request, "client", None)
            client_host = getattr(client_info, "host", "unknown") if client_info else "unknown"
            client_port = getattr(client_info, "port", "unknown") if client_info else "unknown"
            
            # Log comprehensive request details
            webhook_service.logger.debug("=" * 80)
            webhook_service.logger.debug("📡 WEBHOOK REQUEST RECEIVED")
            webhook_service.logger.debug("=" * 80)
            webhook_service.logger.debug(f"📡 Client: {client_host}:{client_port}")
            webhook_service.logger.debug(f"🌐 Method: {request.method}")
            webhook_service.logger.debug(f"📍 URL: {request.url}")
            webhook_service.logger.debug(f"📋 Content-Type: {request.headers.get('content-type', 'none')}")
            webhook_service.logger.debug(f"🤖 User-Agent: {request.headers.get('user-agent', 'none')}")
            webhook_service.logger.debug(f"📏 Body Length: {len(raw_body)} bytes")
            
            # Log headers (mask sensitive ones)
            webhook_service.logger.debug("📨 REQUEST HEADERS:")
            for header_name, header_value in request.headers.items():
                if header_name.lower() in ['authorization', 'x-api-key', 'x-jellyfin-token']:
                    masked_value = header_value[:8] + "***" if len(header_value) > 8 else "***"
                    webhook_service.logger.debug(f"    {header_name}: {masked_value}")
                else:
                    webhook_service.logger.debug(f"    {header_name}: {header_value}")
            
            # Log raw body content
            webhook_service.logger.debug("📦 RAW BODY CONTENT:")
            try:
                body_text = raw_body.decode('utf-8', errors='replace')
                if len(body_text) > 2000:
                    webhook_service.logger.debug(f"    {body_text[:2000]}... (truncated, total length: {len(body_text)})")
                else:
                    webhook_service.logger.debug(f"    {body_text}")
            except Exception as decode_error:
                webhook_service.logger.debug(f"    Failed to decode body as UTF-8: {decode_error}")
                webhook_service.logger.debug(f"    Raw bytes (first 200): {raw_body[:200]}")
            
            # Parse and log JSON structure
            webhook_service.logger.debug("📋 PARSED JSON STRUCTURE:")
            try:
                json_data = json.loads(raw_body)
                webhook_service.logger.debug(f"    Top-level keys: {list(json_data.keys())}")
                webhook_service.logger.debug(f"    Total fields: {len(json_data)}")
                
                # Log each field with type information
                webhook_service.logger.debug("🔍 FIELD DETAILS:")
                for key, value in json_data.items():
                    value_type = type(value).__name__
                    if value is None:
                        value_str = "null"
                    elif isinstance(value, str):
                        value_str = f'"{value[:100]}..."' if len(value) > 100 else f'"{value}"'
                    else:
                        value_str = str(value)
                    webhook_service.logger.debug(f"    {key} ({value_type}): {value_str}")
            except json.JSONDecodeError as e:
                webhook_service.logger.debug(f"    JSON parse error: {e}")
            
            # Log payload details (structured)
            webhook_service.logger.debug("📦 WEBHOOK PAYLOAD (Validated):")
            webhook_service.logger.debug(f"    ItemId: {payload.ItemId}")
            webhook_service.logger.debug(f"    Name: {payload.Name}")
            webhook_service.logger.debug(f"    ItemType: {payload.ItemType}")
            webhook_service.logger.debug(f"    NotificationType: {getattr(payload, 'NotificationType', 'N/A')}")
            webhook_service.logger.debug(f"    ServerId: {getattr(payload, 'ServerId', 'N/A')}")
            webhook_service.logger.debug(f"    ServerName: {getattr(payload, 'ServerName', 'N/A')}")
            
            # Log additional fields if present (checking for attributes that might not exist)
            if hasattr(payload, 'Username'):
                webhook_service.logger.debug(f"    Username: {payload.Username}")
            if hasattr(payload, 'UserId'):
                webhook_service.logger.debug(f"    UserId: {payload.UserId}")
            if hasattr(payload, 'LibraryName'):
                webhook_service.logger.debug(f"    LibraryName: {payload.LibraryName}")
            if hasattr(payload, 'Path'):
                webhook_service.logger.debug(f"    Path: {payload.Path}")
            if hasattr(payload, 'Year'):
                webhook_service.logger.debug(f"    Year: {payload.Year}")
            
            # Show payload as formatted JSON for easy copying
            webhook_service.logger.debug("📋 PAYLOAD AS FORMATTED JSON:")
            webhook_service.logger.debug(json.dumps(payload.model_dump(), indent=2))
            webhook_service.logger.debug("=" * 80)
        
        # Process the webhook through our service layer
        result = await webhook_service.process_webhook(payload)
        
        # Log success in debug mode
        if webhook_service.logger.isEnabledFor(logging.DEBUG):
            webhook_service.logger.debug(f"✅ Webhook processed successfully: {result.get('status')}")
        
        return result

    except Exception as e:
        # Log the error but don't expose internal details to the client
        webhook_service.logger.error(f"Webhook processing failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Internal error processing webhook"
        )


# Debug webhook endpoint has been removed - its functionality is now in the main /webhook endpoint
# To enable debug logging, set LOG_LEVEL=DEBUG in your environment or config

@app.post("/webhook/debug", deprecated=True, include_in_schema=False)
async def webhook_debug_endpoint_deprecated(request: Request) -> Dict[str, Any]:
    """
    DEPRECATED: This endpoint has been removed. Debug functionality is now in /webhook.
    
    Set LOG_LEVEL=DEBUG to enable comprehensive request/response logging.
    """
    _ = request  # Required by FastAPI signature but not used
    return {
        "status": "deprecated",
        "message": "The /webhook/debug endpoint has been deprecated",
        "recommendation": "Use the main /webhook endpoint with LOG_LEVEL=DEBUG for debugging",
        "migration_guide": {
            "old_endpoint": "/webhook/debug",
            "new_endpoint": "/webhook",
            "enable_debug": "Set LOG_LEVEL=DEBUG in environment variables or config.json"
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
@app.get("/health")
async def health_check():
    """
    Health check endpoint for monitoring and load balancers.

    This endpoint provides a quick health check for external monitoring
    systems, Docker health checks, and load balancers. It returns basic
    service status without detailed component information.

    Returns:
        dict: Simple health status

    Example:
        ```bash
        curl http://jellynouncer:PORT/health
        # Returns: {"status": "healthy", "timestamp": "2024-01-01T12:00:00Z"}
        ```

        Replace PORT with your configured port (default: 1984).

    Note:
        This endpoint is lightweight and designed for frequent polling.
        For detailed service information, use the /stats endpoint instead.
    """
    if webhook_service is None:
        raise HTTPException(
            status_code=503,
            detail="Service not ready - still initializing"
        )

    try:
        # Perform comprehensive health check
        health_data = await webhook_service.health_check()

        # Return appropriate HTTP status based on health
        if health_data["status"] == "healthy":
            return health_data
        elif health_data["status"] == "degraded":
            return JSONResponse(status_code=200, content=health_data)
        else:
            return JSONResponse(status_code=503, content=health_data)

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Health check failed: {str(e)}"
        )


@app.get("/validate-templates")
async def validate_templates():
    """
    Validate all Discord notification templates for JSON syntax errors.
    
    This endpoint renders each template with sample data and checks for JSON validity.
    Useful for catching template errors during development or after template modifications.
    
    Returns:
        dict: Validation results for each template with error details if any
    
    Example:
        ```bash
        curl http://jellynouncer:1984/validate-templates
        ```
    """
    if webhook_service is None:
        raise HTTPException(
            status_code=503,
            detail="Service not ready - still initializing"
        )
    
    if not webhook_service.discord:
        raise HTTPException(
            status_code=503,
            detail="Discord notifier not initialized"
        )
    
    try:
        results = await webhook_service.discord.validate_all_templates()
        
        # Count valid/invalid templates
        valid_count = sum(1 for r in results.values() if r["status"].startswith("✅"))
        total_count = len(results)
        
        return {
            "status": "success" if valid_count == total_count else "errors_found",
            "summary": {
                "total_templates": total_count,
                "valid_templates": valid_count,
                "invalid_templates": total_count - valid_count
            },
            "templates": results,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        webhook_service.logger.error(f"Template validation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Template validation failed: {str(e)}"
        )

@app.get("/stats")
async def service_statistics():
    """
    Detailed service statistics endpoint for monitoring and diagnostics.

    This endpoint provides comprehensive statistics about the service
    including database metrics, processing counts, and component status.
    It's designed for administrative monitoring and troubleshooting.

    Returns:
        dict: Detailed service statistics and metrics

    Example:
        ```bash
        curl http://jellynouncer:1984/stats
        ```

    Note:
        This endpoint provides more detailed information than /health.
        It should not be called as frequently as the health check endpoint.
    """
    if webhook_service is None:
        raise HTTPException(
            status_code=503,
            detail="Service not ready - still initializing"
        )

    try:
        # Gather comprehensive statistics from the service
        stats = await webhook_service.get_service_stats()

        # Add timestamp and metadata
        stats["timestamp"] = datetime.now(timezone.utc).isoformat()
        stats["service_info"] = {
            "name": "Jellynouncer",
            "version": "2.0.0",
            "author": "Mark Newton"
        }

        return stats

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving service statistics: {str(e)}"
        )


@app.post("/sync")
async def trigger_manual_sync():
    """
    Trigger a manual library synchronization with Jellyfin.

    This endpoint allows administrators to manually start a full library sync
    without waiting for the scheduled background sync. This is useful when
    you know items have been added to Jellyfin but want to ensure they're
    processed immediately.

    Returns:
        dict: Sync initiation status with details about the operation

    Raises:
        HTTPException:
            - 503 if service is not ready
            - 409 if a sync is already in progress
            - 500 if sync initiation fails

    Example:
        ```bash
        curl -X POST http://jellynouncer:1984/sync
        # Returns: {"status": "success", "message": "Library sync started"}
        ```

    Note:
        The sync runs in the background, so this endpoint returns immediately.
        Use the /stats endpoint to monitor sync progress and completion.
        Multiple sync requests will be queued to prevent resource conflicts.
    """
    if webhook_service is None:
        raise HTTPException(
            status_code=503,
            detail="Service not ready - still initializing"
        )

    try:
        # Initiate manual library sync
        result = await webhook_service.trigger_manual_sync()

        # Return appropriate HTTP status based on result
        if result.get("status") == "success":
            return result
        elif result.get("status") == "warning":
            # Sync already in progress
            raise HTTPException(status_code=409, detail=result.get("message"))
        else:
            # Error starting sync
            raise HTTPException(status_code=500, detail=result.get("message"))

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error triggering manual sync: {str(e)}"
        )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Custom exception handler for Pydantic validation errors.

    This handler provides more user-friendly error messages when webhook
    payloads don't match the expected structure. It's particularly useful
    for debugging webhook configuration issues with Jellyfin.

    Args:
        request: The FastAPI request that caused the validation error
        exc: The Pydantic validation exception with detailed error information

    Returns:
        JSONResponse: Formatted error response with detailed validation errors

    Example:
        When Jellyfin sends an invalid webhook payload, this handler returns:
        ```json
        {
            "error": "Validation Error",
            "details": [
                {
                    "field": "ItemId",
                    "message": "field required",
                    "input": null
                }
            ],
            "help": "Check your Jellyfin webhook configuration..."
        }
        ```

    Note:
        This handler helps administrators diagnose webhook configuration
        problems by providing clear, actionable error messages rather than
        generic HTTP 422 responses.
    """
    # Extract detailed error information from the Pydantic exception
    errors = []
    for error in exc.errors():
        field_path = " → ".join(str(loc) for loc in error["loc"])
        # Handle bytes input that can't be JSON serialized
        input_value = error.get("input", "unknown")
        if isinstance(input_value, bytes):
            try:
                # Try to decode bytes to string for better error messages
                input_value = input_value.decode('utf-8')[:500]  # Limit to 500 chars
            except (UnicodeDecodeError, AttributeError):
                input_value = f"<binary data: {len(input_value)} bytes>"
        errors.append({
            "field": field_path,
            "message": error["msg"],
            "input": input_value
        })

    # Log the validation error for debugging
    if webhook_service and webhook_service.logger:
        webhook_service.logger.warning(
            f"Webhook validation error from {request.client.host if request.client else 'unknown'}: "
            f"{len(errors)} field errors"
        )

    # Return user-friendly error response
    return JSONResponse(
        status_code=422,
        content={
            "error": "Webhook Validation Error",
            "message": "The webhook payload from Jellyfin doesn't match the expected format",
            "details": errors,
            "help": (
                "This usually indicates a configuration issue with the Jellyfin webhook plugin. "
                "Please check that your webhook is configured to send the required fields: "
                "ItemId, Name, ItemType, NotificationType"
            )
        }
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Global exception handler for unexpected errors.

    This handler catches any unhandled exceptions in the application and
    provides a consistent error response format. It also ensures that
    sensitive error details are not exposed to clients while still
    logging the full error for debugging.

    Args:
        request: The FastAPI request that caused the exception
        exc: The unhandled exception

    Returns:
        JSONResponse: Generic error response without sensitive details

    Note:
        This handler serves as a safety net to prevent the application
        from crashing on unexpected errors while ensuring that detailed
        error information is logged for debugging purposes.
    """
    # Log the full error with stack trace for debugging
    if webhook_service and webhook_service.logger:
        webhook_service.logger.error(
            f"Unhandled exception in {request.method} {request.url}: {exc}",
            exc_info=True
        )

    # Return generic error response without sensitive details
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "message": "An unexpected error occurred while processing your request",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": str(hash(f"{request.method}{request.url}{time.time()}"))
        }
    )


def setup_signal_handlers():
    """
    Set up signal handlers for graceful shutdown.

    This function configures the application to handle system signals
    (like SIGTERM from Docker or SIGINT from Ctrl+C) gracefully,
    ensuring that connections are closed and data is saved properly.

    The signal handlers work with the FastAPI lifespan manager to
    ensure clean shutdown procedures are followed.

    Note:
        Signal handlers only work on Unix-based systems (Linux, macOS).
        On Windows, the application will still shut down cleanly when
        the process is terminated normally.
    """
    # Get logger for signal handling
    logger = get_logger("main")

    def signal_handler(signum, frame):
        """Handle shutdown signals gracefully."""
        _ = frame  # Required by signal handler signature but not used
        signal_name = signal.Signals(signum).name
        logger.info(f"Received {signal_name} signal - initiating graceful shutdown...")

        # Exit with success code to trigger the lifespan shutdown
        sys.exit(0)

    # Register handlers for common shutdown signals
    signal.signal(signal.SIGTERM, signal_handler)  # Docker stop
    signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C


if __name__ == "__main__":
    """
    Main entry point when running the webhook API directly.

    This block only executes when the script is run directly (python webhook_api.py)
    rather than being imported as a module. It sets up signal handlers and
    starts the Uvicorn ASGI server with production-ready configuration.

    Environment Variables:
        HOST: Server host address (default: 0.0.0.0)
        PORT: Server port number (default: 1984)
        WORKERS: Number of worker processes (default: 1)
        LOG_LEVEL: Uvicorn log level (default: info)

    Example:
        ```bash
        # Run with default settings
        python webhook_api.py

        # Run with custom configuration
        HOST=127.0.0.1 PORT=3000 python webhook_api.py
        ```

    Note:
        In production, you should use the main.py launcher to run both
        the webhook API and web interface together.
    """
    # Set up signal handlers for graceful shutdown
    setup_signal_handlers()

    # This allows config file settings to be used with environment variable overrides
    config = None
    try:
        config_validator = ConfigurationValidator()
        config = config_validator.load_and_validate_config()
        print(f"Configuration loaded successfully from config file")
    except Exception as e:
        print(f"Warning: Could not load configuration file, using environment variables and defaults: {e}")

    # Get configuration from config file with environment variable overrides
    if config:
        # Use config values with environment variable overrides (environment takes priority)
        host = os.getenv("HOST", config.server.host)
        port = int(os.getenv("PORT", str(config.server.port)))
        # Convert log_level to lowercase for uvicorn
        log_level = os.getenv("LOG_LEVEL", config.server.log_level).lower()
        print(f"Using server config: {host}:{port}, log_level={log_level}")
    else:
        # Fallback to environment variables with hardcoded defaults
        host = os.getenv("HOST", "0.0.0.0")  # Listen on all interfaces
        port = int(os.getenv("PORT", 1984))  # Standard webhook port
        log_level = os.getenv("LOG_LEVEL", "info").lower()
        print(f"Using fallback config: {host}:{port}, log_level={log_level}")

    # Start the Uvicorn ASGI server
    # Uvicorn is a lightning-fast ASGI server implementation for Python
    uvicorn.run(
        "jellynouncer.webhook_api:app",  # Module and app variable
        host=host,
        port=port,
        log_level=log_level,
        # Use only 1 worker with SQLite to avoid database locking issues
        # Multiple workers would require PostgreSQL or MySQL
        workers=1,
        # Enable auto-reload in development
        reload=os.getenv("ENVIRONMENT", "production") == "development",
        # Server configuration for production
        access_log=True,  # Enable access logging
        use_colors=True,  # Colorized logs for better readability
    )