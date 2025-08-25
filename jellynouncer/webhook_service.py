#!/usr/bin/env python3
"""
Jellynouncer Webhook Service Module

This module contains the main WebhookService class that serves as the central orchestrator
for all Jellynouncer functionality. It coordinates between Jellyfin webhooks, change
detection, database management, and Discord notifications to provide a complete media
notification service.

The WebhookService acts as the "conductor" of the application, managing the flow of data
between all other components and ensuring they work together harmoniously.

Classes:
    WebhookService: Main service orchestrator that coordinates all other components

Author: Mark Newton
Project: Jellynouncer
Version: 1.0.0
License: MIT
"""

import asyncio
import time
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

import aiohttp
import aiosqlite

from .config_models import AppConfig, ConfigurationValidator
from .webhook_models import WebhookPayload
from .media_models import MediaItem
from .database_manager import DatabaseManager
from .jellyfin_api import JellyfinAPI
from .discord_services import DiscordNotifier
from .metadata_services import MetadataService
from .change_detector import ChangeDetector
from .utils import get_logger
from .sync_progress import SyncProgressDisplay


class WebhookService:
    """
    Main webhook service orchestrator that coordinates all application components.

    Think of this class as the "conductor" of an orchestra - it doesn't play any
    instruments itself, but it coordinates all the other "musicians" (components)
    to create a harmonious performance. The WebhookService manages the entire
    flow of data from Jellyfin webhooks through to Discord notifications.

    The service handles several key responsibilities:
    - Service initialization and configuration management
    - Background maintenance tasks (database cleanup, health monitoring)
    - Webhook processing from Jellyfin (the main event loop)
    - Library synchronization with Jellyfin
    - Health monitoring and diagnostics
    - Graceful shutdown procedures

    The service follows an async-first design pattern, meaning most operations
    are asynchronous (non-blocking) to handle multiple webhook requests
    simultaneously without slowing down.

    **Understanding Async/Await:**
        The `async` and `await` keywords are Python's way of handling concurrent
        operations. When a method is marked `async`, it means it can be paused
        and resumed, allowing other operations to run while waiting for slow
        operations (like network requests or database queries) to complete.

    **The Orchestrator Pattern:**
        This class implements the "orchestrator" or "service coordinator" pattern.
        Instead of having components directly communicate with each other, they
        all report to this central coordinator which manages their interactions.
        This makes the system easier to maintain and debug.

    Attributes:
        logger (logging.Logger): Main application logger for tracking operations
        config (AppConfig): Validated application configuration from files/environment
        db (DatabaseManager): Database manager for storing media item information
        jellyfin (JellyfinAPI): Jellyfin API client for communicating with media server
        change_detector (ChangeDetector): Logic for detecting meaningful media changes
        discord (DiscordNotifier): Discord notification manager for sending messages
        metadata_service (MetadataService): Service for fetching external metadata information

    Service State Tracking:
        last_vacuum (float): Timestamp of last database maintenance operation
        server_was_offline (bool): Whether Jellyfin server was previously offline
        sync_in_progress (bool): Whether library sync is currently running
        is_background_sync (bool): Whether current sync is running in background
        initial_sync_complete (bool): Whether initial startup sync finished
        shutdown_event (asyncio.Event): Coordination signal for graceful shutdown

    Example:
        Basic service lifecycle:
        ```python
        # Create and initialize the service
        service = WebhookService()
        await service.initialize()

        # Process a webhook from Jellyfin
        webhook_payload = WebhookPayload(ItemId="123", Name="Movie", ...)
        result = await service.process_webhook(webhook_payload)
        logger.info(f"Processed {result['action']} for {result['item_name']}")

        # Check service health
        health = await service.health_check()
        logger.info(f"Service status: {health['status']}")

        # Clean up when shutting down
        await service.cleanup()
        ```

    Note:
        This class is designed to be a singleton - only one instance should
        exist per application to avoid conflicts with shared resources like
        the database and background tasks.
    """

    def __init__(self):
        """
        Initialize webhook service with logging and configuration loading.

        This constructor handles the early initialization steps that must happen
        synchronously (without async/await). The heavy lifting of async operations
        happens later in the initialize() method.

        **Why Two-Phase Initialization?**
            Python constructors (__init__) cannot be async, but we need to perform
            async operations like database connections and API calls. So we split
            initialization into two phases:
            1. __init__: Sync operations (logging, config loading, object creation)
            2. initialize(): Async operations (database setup, API connections)

        **Understanding Component Initialization:**
            We initialize all component references to None and populate them during
            the async initialize() method. This ensures clean error handling and
            allows for proper resource management.

        Raises:
            SystemExit: If configuration loading or validation fails critically
        """
        # Set up component-specific logger
        self.logger = get_logger("jellynouncer.webhook")

        # Initialize component references to None
        # We'll populate these with actual objects later
        self.config = None
        self.db = None
        self.jellyfin = None
        self.change_detector = None
        self.discord = None
        self.metadata_service = None

        # Initialize service state tracking attributes
        # These keep track of what the service is currently doing
        self.last_vacuum: float = 0.0  # When we last cleaned up the database
        self.server_was_offline = False  # Was Jellyfin offline last time we checked?
        self.sync_in_progress = False  # Are we currently syncing the library?
        self.is_background_sync = False  # Is the sync running in the background?
        self.initial_sync_complete = False  # Have we done our first sync?
        self.shutdown_event = asyncio.Event()  # Graceful shutdown coordination

        # Record service startup time for uptime tracking
        self._start_time: float = time.time()
        self._last_sync_time: float = 0.0  # Initialize sync time
        
        # Deletion tracking for filtering upgrades/renames
        self.pending_deletions = {}  # Track recent deletions to filter upgrades
        self.deletion_timeout = 30  # Wait 30 seconds before processing deletions
        self.deletion_cleanup_task = None  # Background task for cleaning old deletions

        self.logger.info("WebhookService created - ready for initialization")

    async def initialize(self) -> None:
        """
        Initialize all service components and establish connections.

        This async method handles the complex initialization process that requires
        network connections, database setup, and component coordination. It's
        designed to fail gracefully if any component cannot be initialized.

        **Initialization Steps:**
            1. Load and validate configuration from files and environment
            2. Initialize database manager and create/migrate tables
            3. Connect to Jellyfin API and verify authentication
            4. Set up Discord notification manager with webhooks
            5. Initialize external metadata services (OMDb, TMDb, TVDb)
            6. Create change detector for upgrade notifications
            7. Perform initial library sync if needed
            8. Start background maintenance tasks

        **Error Handling Strategy:**
            Each initialization step is wrapped in try/catch blocks to provide
            detailed error information. Critical failures will stop the service,
            while non-critical failures (like metadata services) will log warnings
            but allow the service to continue.

        Raises:
            SystemExit: If critical components (database, Jellyfin) cannot be initialized
            Various exceptions: If configuration is invalid or connections fail

        Example:
            ```python
            webhook_service = WebhookService()
            try:
                await webhook_service.initialize()
                logger.info("Service ready to process webhooks")
            except Exception as e:
                logger.error(f"Service initialization failed: {e}")
                sys.exit(1)
            ```
        """
        try:
            self.logger.info("Starting WebhookService initialization...")

            # Step 1: Load and validate configuration
            self.logger.debug("Loading application configuration...")
            try:
                config_validator = ConfigurationValidator()
                self.config = config_validator.load_and_validate_config()
                self.logger.info("Configuration loaded and validated successfully")
                self.logger.debug(f"Jellyfin server: {self.config.jellyfin.server_url}")
                self.logger.debug(f"Database path: {self.config.database.path}")
            except Exception as e:
                self.logger.error(f"Configuration loading failed: {e}")
                raise SystemExit(f"Cannot start without valid configuration: {e}")

            # Step 2: Initialize database manager
            self.logger.debug("Initializing database manager...")
            try:
                self.db = DatabaseManager(self.config.database)
                await self.db.initialize()
                self.logger.info("Database manager initialized successfully")

                # Load service state after database initialization
                await self._load_service_state()

            except Exception as e:
                self.logger.error(f"Database initialization failed: {e}")
                raise SystemExit(f"Cannot start without database: {e}")

            # Step 3: Initialize Jellyfin API client
            self.logger.debug("Connecting to Jellyfin API...")
            try:
                self.jellyfin = JellyfinAPI(self.config.jellyfin)
                if await self.jellyfin.connect():
                    self.logger.info("Connected to Jellyfin API successfully")
                else:
                    self.logger.error("Failed to connect to Jellyfin API")
                    raise SystemExit("Cannot start without Jellyfin connection")
            except Exception as e:
                self.logger.error(f"Jellyfin API initialization failed: {e}")
                raise SystemExit(f"Cannot connect to Jellyfin: {e}")

            # Step 4: Initialize Discord notification manager
            self.logger.debug("Setting up Discord notification manager...")
            try:
                # Create optimized aiohttp session with connection pooling
                connector = aiohttp.TCPConnector(
                    limit=200,  # Total connection pool limit
                    limit_per_host=50,  # Per-host connection limit
                    ttl_dns_cache=300,  # DNS cache timeout in seconds
                    enable_cleanup_closed=True,  # Clean up closed connections
                    force_close=False,  # Keep connections alive for reuse
                    keepalive_timeout=30  # Keep connections alive for 30 seconds
                )
                timeout = aiohttp.ClientTimeout(
                    total=30,  # Total timeout
                    connect=5,  # Connection timeout
                    sock_read=10  # Socket read timeout
                )
                session = aiohttp.ClientSession(
                    connector=connector,
                    timeout=timeout
                )
                self.discord = DiscordNotifier(self.config.discord)
                await self.discord.initialize(session, self.config.jellyfin, self.config.templates, self.config.notifications)
                self.logger.info("Discord notification manager initialized")
            except Exception as e:
                self.logger.error(f"Discord manager initialization failed: {e}")
                raise SystemExit(f"Cannot start without Discord manager: {e}")

            # Step 5: Initialize metadata service (non-critical)
            self.logger.debug("Initializing external metadata services...")
            try:
                self.metadata_service = MetadataService(self.config.metadata_services)
                await self.metadata_service.initialize(session, self.db)
                if self.metadata_service.enabled:
                    self.logger.info("Metadata services initialized and enabled")
                else:
                    self.logger.info("Metadata services initialized but disabled")
            except Exception as e:
                self.logger.warning(f"Metadata service initialization failed: {e}")
                self.logger.info("Service will continue without metadata enhancements")

            # Step 6: Initialize change detector
            self.logger.debug("Setting up change detector...")
            try:
                self.change_detector = ChangeDetector(self.config.notifications)
                self.logger.info("Change detector initialized successfully")
            except Exception as e:
                self.logger.error(f"Change detector initialization failed: {e}")
                raise SystemExit(f"Cannot start without change detection: {e}")

            # Step 7: Perform initial library sync if needed
            await self._check_initial_sync()

            # Step 8: Log successful initialization
            self.logger.info("=" * 60)
            self.logger.info("🚀 WebhookService initialization completed successfully!")
            self.logger.info("Service is ready to process Jellyfin webhooks")
            self.logger.info("=" * 60)

        except SystemExit:
            # Re-raise SystemExit exceptions to stop the application
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error during initialization: {e}", exc_info=True)
            raise SystemExit(f"Service initialization failed: {e}")

    async def _load_service_state(self) -> None:
        """
        Load service state from database.

        This method loads persistent service state like last vacuum time
        and last sync time from the database to prevent NoneType errors
        in background tasks.
        """
        try:
            if not self.db:
                self.logger.warning("Database not initialized, using default state values")
                return

            # Load last vacuum time from database
            vacuum_time = await self.db.get_vacuum_timestamp()
            if vacuum_time is not None:
                self.last_vacuum = vacuum_time
                self.logger.debug(f"Loaded last vacuum time: {vacuum_time}")
            else:
                # Set to current time to prevent immediate vacuum on startup
                self.last_vacuum = time.time()
                self.logger.debug("No vacuum history found, using current time")

            # Load last sync time from database
            sync_time = await self._get_last_sync_time()
            if sync_time is not None:
                self._last_sync_time = sync_time
                self.logger.debug(f"Loaded last sync time: {sync_time}")

        except Exception as e:
            self.logger.warning(f"Failed to load service state: {e}")
            # Ensure we have safe defaults even if loading fails
            self.last_vacuum = time.time()
            self._last_sync_time = 0.0

    async def _get_last_sync_time(self) -> Optional[float]:
        """
        Get the last sync time from database.

        Returns:
            Optional[float]: Unix timestamp of last sync, or None if not found
        """
        try:
            async with aiosqlite.connect(self.db.db_path) as db:
                cursor = await db.execute("""
                                          SELECT strftime('%s', last_sync_time)
                                          FROM sync_status
                                          WHERE id = 1
                                            AND sync_type = 'library_sync'
                                          """)
                row = await cursor.fetchone()
                if row and row[0]:
                    return float(row[0])
                return None
        except Exception as e:
            self.logger.debug(f"Could not retrieve last sync time: {e}")
            return None

    async def process_webhook(self, payload: WebhookPayload) -> Dict[str, Any]:
        """
        Process incoming webhook from Jellyfin media server.

        This is the main entry point for webhook processing. It handles the entire
        workflow from receiving a webhook payload to sending Discord notifications,
        including change detection, database updates, and error recovery.

        **Webhook Processing Pipeline:**
            1. Validate and extract media information from webhook payload
            2. Fetch additional metadata from Jellyfin API if needed
            3. Check database for existing item to detect changes vs new items
            4. Apply intelligent change detection for upgrade scenarios
            5. Update database with new/changed information
            6. Send appropriate Discord notifications based on content type
            7. Handle errors gracefully without breaking the service

        **Understanding the Workflow:**
            Not every webhook should result in a notification. The service needs
            to distinguish between:
            - New items that should always generate notifications
            - Updated items where only meaningful changes warrant notifications
            - Metadata-only updates that don't affect the user experience

        Args:
            payload (WebhookPayload): Validated webhook data from Jellyfin

        Returns:
            Dict[str, Any]: Processing result with details about the action taken

        Raises:
            HTTPException: If processing fails critically (rare - most errors are handled gracefully)

        Example:
            ```python
            # Webhook payload from Jellyfin
            payload = WebhookPayload(
                ItemId="abc123",
                Name="The Matrix",
                ItemType="Movie",
                NotificationType="library.new"
            )

            # Process the webhook
            result = await webhook_service.process_webhook(payload)

            logger.info(f"Action: {result['action']}")  # "new_item" or "item_updated"
            logger.info(f"Item: {result['item_name']}")  # "The Matrix"
            ```

        Note:
            This method is designed to be resilient and should never crash the
            entire service. All errors are logged and handled gracefully.
        """
        # Initialize timing variable
        start_time = time.time()

        try:
            self.logger.debug(f"Processing webhook for {payload.Name} ({payload.ItemType}) - Event: {payload.NotificationType}")
            
            # Handle ItemDeleted notifications
            if payload.NotificationType == "ItemDeleted":
                return await self._handle_item_deleted(payload)
            
            # Handle ItemAdded notifications with rename/upgrade filtering
            if payload.NotificationType == "ItemAdded":
                # Check if this might be a rename or upgrade
                deletion_info = await self._check_pending_deletion(payload.Name, payload.ItemType)
                if deletion_info:
                    # This might be an upgrade or rename
                    return await self._handle_potential_upgrade(payload, deletion_info)
                else:
                    # Normal add without prior deletion
                    return await self._process_item_added(payload)
            
            # For other notification types, continue with original logic
            # Get detailed item information from Jellyfin
            item_data = await self.jellyfin.get_item(payload.ItemId)
            if not item_data:
                self.logger.warning(f"Could not fetch item data for {payload.ItemId}")
                return {
                    "status": "error",
                    "action": "fetch_failed",
                    "item_id": payload.ItemId,
                    "item_name": payload.Name,
                    "message": "Could not fetch item data from Jellyfin"
                }

            # Convert to our internal MediaItem format (for database storage)
            media_item = await self.jellyfin.convert_to_media_item(item_data)
            self.logger.debug(f"Converted to MediaItem: {media_item.name}")
            
            # Add server information from webhook payload (not available in Jellyfin API)
            media_item.server_id = payload.ServerId
            media_item.server_name = payload.ServerName
            media_item.server_version = payload.ServerVersion
            media_item.server_url = payload.ServerUrl
            self.logger.debug(f"Added server info: {media_item.server_name}")
            
            # Use provider IDs from webhook as they are the real-time notification data
            if hasattr(payload, 'Provider_imdb') and payload.Provider_imdb:
                media_item.imdb_id = payload.Provider_imdb
                self.logger.debug(f"Using IMDB ID from webhook: {payload.Provider_imdb}")
            if hasattr(payload, 'Provider_tmdb') and payload.Provider_tmdb:
                media_item.tmdb_id = payload.Provider_tmdb
                self.logger.debug(f"Using TMDB ID from webhook: {payload.Provider_tmdb}")
            if hasattr(payload, 'Provider_tvdb') and payload.Provider_tvdb:
                media_item.tvdb_id = payload.Provider_tvdb
                self.logger.debug(f"Using TVDB ID from webhook: {payload.Provider_tvdb}")
            if hasattr(payload, 'Provider_tvdbslug') and payload.Provider_tvdbslug:
                media_item.tvdb_slug = payload.Provider_tvdbslug
                self.logger.debug(f"Using TVDB slug from webhook: {payload.Provider_tvdbslug}")

            # Check if this is a new item or an update
            existing_item = await self.db.get_item(media_item.item_id)

            if existing_item:
                # Check for changes
                changes = await self.change_detector.detect_changes(existing_item, media_item)

                if changes:
                    # This is an upgrade - update database with basic fields
                    self.logger.info(f"Quality upgrade detected for: {media_item.name}")
                    await self.db.save_item(media_item)

                    # Enrich with ALL type-specific fields for notification
                    enriched_item = await self.jellyfin.enrich_media_item_for_notification(
                        media_item,
                        item_data,
                        retry_on_failure=True
                    )

                    # Log enrichment status
                    if hasattr(enriched_item, 'is_enriched') and enriched_item.is_enriched:
                        self.logger.info(f"Item enriched with type-specific fields for {enriched_item.item_type}")
                    else:
                        self.logger.warning(f"Using basic item data for notification (enrichment failed)")

                    # Get metadata for upgraded item
                    metadata = {}
                    if self.metadata_service and self.metadata_service.enabled:
                        try:
                            metadata = await self.metadata_service.enrich_media_item(enriched_item)
                        except Exception as e:
                            self.logger.error(f"Error enriching upgraded item with metadata: {e}")
                    
                    # Send upgrade notification with enriched item and metadata
                    await self.discord.send_notification(enriched_item, "upgraded_item", changes, metadata=metadata)

                    return {
                        "status": "success",
                        "action": "upgraded_item",
                        "item_id": media_item.item_id,
                        "item_name": media_item.name,
                        "item_type": media_item.item_type,
                        "changes": len(changes),
                        "enriched": getattr(enriched_item, 'is_enriched', False),
                        "processing_time": round(time.time() - start_time, 3)
                    }
                else:
                    # No significant changes - metadata only update
                    self.logger.debug(f"No significant changes for: {media_item.name}")
                    await self.db.save_item(media_item)  # Update metadata

                    return {
                        "status": "success",
                        "action": "metadata_updated",
                        "item_id": media_item.item_id,
                        "item_name": media_item.name,
                        "message": "Metadata updated, no notification sent",
                        "processing_time": round(time.time() - start_time, 3)
                    }
            else:
                # This is a new item
                self.logger.info(f"New item detected: {media_item.name} ({media_item.item_type})")

                # Save to database (basic fields only)
                await self.db.save_item(media_item)

                # Enrich media item with metadata before rendering templates
                metadata = {}
                if self.metadata_service and self.metadata_service.enabled:
                    try:
                        # Get metadata from external sources (OMDb, TVDb, TMDb)
                        metadata = await self.metadata_service.enrich_media_item(media_item)
                        self.logger.info(
                            f"Added metadata from external sources for {media_item.name}"
                        )
                    except Exception as e:
                        self.logger.error(f"Error enriching item with metadata: {e}")
                        # Continue without metadata if enrichment fails

                # Send new item notification with metadata
                await self.discord.send_notification(media_item, "new_item", metadata=metadata)

                return {
                    "status": "success",
                    "action": "new_item",
                    "item_id": media_item.item_id,
                    "item_name": media_item.name,
                    "item_type": media_item.item_type,
                    "enriched": getattr(media_item, 'is_enriched', False),
                    "processing_time": round(time.time() - start_time, 3)
                }

        except Exception as e:
            processing_time = time.time() - start_time
            self.logger.error(f"Error processing webhook for {payload.Name}: {e}", exc_info=True)
            return {
                "status": "error",
                "action": "processing_failed",
                "item_id": payload.ItemId,
                "item_name": payload.Name,
                "message": str(e),
                "processing_time": round(processing_time, 3)
            }

    async def trigger_manual_sync(self) -> Dict[str, Any]:
        """
        Trigger a manual library synchronization with Jellyfin.

        This method allows administrators to manually start a library sync
        without waiting for the scheduled background sync. It's useful when
        you know items have been added to Jellyfin but want immediate processing.

        **Manual vs Background Sync:**
            Manual syncs take priority over background syncs and provide immediate
            feedback about the sync status. They're designed for on-demand use
            when administrators need immediate results.

        Returns:
            Dict[str, Any]: Sync initiation status and result information

        Example:
            ```python
            result = await webhook_service.trigger_manual_sync()
            if result["status"] == "success":
                logger.info(f"Sync completed: {result['items_processed']} items")
            else:
                logger.warning(f"Sync issue: {result['message']}")
            ```

        Note:
            Multiple sync requests are queued to prevent resource conflicts.
            If a sync is already running, this method returns immediately
            with a warning status.
        """
        if self.sync_in_progress:
            self.logger.warning("Manual sync requested but sync already in progress")
            return {
                "status": "warning",
                "message": "Library sync already in progress",
                "sync_in_progress": True
            }

        try:
            self.logger.info("Manual library sync triggered by administrator")
            result = await self.sync_jellyfin_library(background=False)

            self.logger.info(f"Manual sync completed with status: {result.get('status', 'unknown')}")
            return result

        except Exception as e:
            self.logger.error(f"Manual sync failed: {e}")
            return {
                "status": "error",
                "message": str(e),
                "sync_in_progress": False
            }

    async def health_check(self) -> Dict[str, Any]:
        """
        Perform comprehensive health check of all service components.

        This method tests the health and connectivity of all major service
        components to provide insight into service status. It's designed for
        monitoring and troubleshooting purposes.

        **Health Check Components:**
            - Jellyfin API connectivity and authentication
            - Database accessibility and performance
            - Discord webhook configuration and connectivity
            - Metadata service availability (if enabled)
            - Service operational status (sync status, etc.)

        **Health Status Levels:**
            - healthy: All components functioning normally
            - degraded: Some non-critical components have issues
            - unhealthy: Critical components are failing

        This gives us better visibility into what's working and what isn't.

        Returns:
            Dict[str, Any]: Comprehensive health status including:
                - status: Overall health (healthy, degraded, error)
                - timestamp: When the check was performed
                - components: Individual component health details
                - Service operational status (sync status, etc.)

        Example:
            ```python
            health = await service.health_check()
            logger.info(f"Service is {health['status']}")

            # Check individual components
            if health['components']['database']['status'] != 'healthy':
                logger.warning("Database issues detected!")
            ```
        """
        try:
            health_data = {
                "status": "healthy",  # Assume healthy until proven otherwise
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "components": {}
            }

            # Check Jellyfin connectivity
            try:
                jellyfin_connected = await self.jellyfin.is_connected()
                if jellyfin_connected:
                    # Get additional Jellyfin info if connected
                    jellyfin_info = await self.jellyfin.get_system_info()
                    health_data["components"]["jellyfin"] = {
                        "status": "healthy",
                        "connected": True,
                        "server_name": jellyfin_info.get("ServerName", "Unknown"),
                        "version": jellyfin_info.get("Version", "Unknown")
                    }
                else:
                    health_data["components"]["jellyfin"] = {
                        "status": "unhealthy",
                        "connected": False,
                        "error": "Cannot connect to Jellyfin server"
                    }
                    health_data["status"] = "unhealthy"
            except Exception as e:
                health_data["components"]["jellyfin"] = {
                    "status": "error",
                    "connected": False,
                    "error": str(e)
                }
                health_data["status"] = "unhealthy"

            # Check database health
            try:
                db_stats = await self.db.get_stats()
                health_data["components"]["database"] = {
                    "status": "healthy",
                    "total_items": db_stats.get("total_items", 0),
                    "db_size_mb": db_stats.get("db_size_mb", 0),
                    "wal_mode": db_stats.get("wal_mode", False)
                }
            except Exception as e:
                health_data["components"]["database"] = {
                    "status": "error",
                    "error": str(e)
                }
                if health_data["status"] == "healthy":
                    health_data["status"] = "degraded"

            # Check Discord webhook status
            try:
                webhook_status = self.discord.get_webhook_status()
                health_data["components"]["discord"] = {
                    "status": "healthy" if webhook_status.get("configured", False) else "warning",
                    "webhooks_configured": webhook_status.get("webhook_count", 0),
                    "enabled_webhooks": webhook_status.get("enabled_count", 0)
                }
            except Exception as e:
                health_data["components"]["discord"] = {
                    "status": "error",
                    "error": str(e)
                }
                if health_data["status"] == "healthy":
                    health_data["status"] = "degraded"

            # Check metadata service status (non-critical)
            try:
                if self.metadata_service and self.metadata_service.enabled:
                    health_data["components"]["metadata_services"] = {
                        "status": "healthy",
                        "enabled": True,
                        "cache_duration_hours": self.metadata_service.cache_duration_hours
                    }
                else:
                    health_data["components"]["metadata_services"] = {
                        "status": "disabled",
                        "enabled": False
                    }
            except Exception as e:
                health_data["components"]["metadata_services"] = {
                    "status": "error",
                    "error": str(e)
                }
                # Metadata service errors don't affect overall health

            # Add service operational status
            health_data["service_status"] = {
                "sync_in_progress": self.sync_in_progress,
                "initial_sync_complete": self.initial_sync_complete,
                "server_was_offline": self.server_was_offline,
                "uptime_seconds": round(time.time() - self._start_time, 2)
            }

            return health_data

        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            return {
                "status": "error",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": str(e),
                "message": "Health check system failure"
            }

    async def get_service_stats(self) -> Dict[str, Any]:
        """
        Get detailed service statistics for monitoring and diagnostics.

        This method collects detailed statistics from all components to provide
        a complete picture of service operation. It's useful for monitoring,
        debugging, and capacity planning.

        **Statistics Collection Strategy:**
            We collect stats from each component separately and handle errors
            gracefully. If one component fails to provide stats, we still
            return statistics from the others with an error indicator.

        Returns:
            Dict[str, Any]: Detailed service statistics including:
                - service: Version, uptime, and operational status
                - database: Item counts, performance metrics
                - webhooks: Configuration and status information
                - jellyfin: Connection status and server information

        Example:
            ```python
            stats = await service.get_service_stats()

            logger.info(f"Service uptime: {stats['service']['uptime_seconds']} seconds")
            logger.info(f"Database items: {stats['database']['total_items']}")
            logger.info(f"Jellyfin connected: {stats['jellyfin']['connected']}")
            ```
        """
        try:
            # Calculate uptime since service started
            uptime_seconds = time.time() - getattr(self, '_start_time', time.time())

            stats = {
                "service": {
                    "version": "1.0.0",
                    "uptime_seconds": round(uptime_seconds, 2),
                    "sync_in_progress": self.sync_in_progress,
                    "initial_sync_complete": self.initial_sync_complete
                }
            }

            # Get database statistics
            try:
                db_stats = await self.db.get_stats()
                stats["database"] = db_stats
            except Exception as e:
                self.logger.warning(f"Could not get database stats: {e}")
                stats["database"] = {"error": str(e)}

            # Get webhook configuration and status
            try:
                webhook_status = self.discord.get_webhook_status()
                stats["webhooks"] = webhook_status
            except Exception as e:
                self.logger.warning(f"Could not get webhook status: {e}")
                stats["webhooks"] = {"error": str(e)}
            
            # Get Discord notification queue statistics
            try:
                queue_stats = self.discord.get_queue_stats()
                stats["notification_queue"] = queue_stats
            except Exception as e:
                self.logger.warning(f"Could not get queue stats: {e}")
                stats["notification_queue"] = {"error": str(e)}

            # Get Jellyfin connection status
            try:
                jellyfin_connected = await self.jellyfin.is_connected()
                stats["jellyfin"] = {
                    "connected": jellyfin_connected,
                    "server_url": self.config.jellyfin.server_url,
                    "server_was_offline": self.server_was_offline
                }
            except Exception as e:
                self.logger.warning(f"Could not get Jellyfin status: {e}")
                stats["jellyfin"] = {"error": str(e)}

            return stats

        except Exception as e:
            self.logger.error(f"Error getting service stats: {e}")
            return {"error": str(e)}

    async def send_server_status_notification(self, is_online: bool, error: Optional[Exception] = None) -> None:
        """
        Send server status notification to Discord.

        Args:
            is_online: Whether the server is currently online
            error: Optional error that caused offline status
        """
        try:
            # Gather health data
            health_data = None
            server_info = None
            queue_status = None

            if is_online:
                # Get current health status
                health_data = await self.health_check()

                # Get server information
                try:
                    server_info = await self.jellyfin.get_system_info()
                except Exception as e:
                    self.logger.warning(f"Could not get server info: {e}")

                # Get queue status
                try:
                    queue_status = {
                        "new_items": len(self.discord.notification_queue.get("new_items", [])),
                        "upgraded_items": len(self.discord.notification_queue.get("upgraded_items", [])),
                        "total": len(self.discord.notification_queue.get("new_items", [])) +
                                 len(self.discord.notification_queue.get("upgraded_items", []))
                    }
                except Exception as e:
                    self.logger.warning(f"Could not get queue status: {e}")

            # Calculate downtime if coming back online
            downtime_duration = None
            if is_online and self.server_was_offline:
                # Calculate downtime (you'd need to track when it went offline)
                if hasattr(self, '_offline_since'):
                    duration_seconds = time.time() - self._offline_since
                    hours = int(duration_seconds // 3600)
                    minutes = int((duration_seconds % 3600) // 60)
                    if hours > 0:
                        downtime_duration = f"{hours}h {minutes}m"
                    else:
                        downtime_duration = f"{minutes} minutes"

            # Prepare template data with all the enhanced fields
            template_data = {
                # Basic fields (existing)
                "is_online": is_online,
                "jellyfin_url": self.config.jellyfin.server_url,
                "timestamp": datetime.now(timezone.utc).isoformat(),

                # Enhanced fields (new)
                "health_data": health_data,
                "server_info": server_info,
                "downtime_duration": downtime_duration,
                "error_details": str(error) if error else None,
                "error_type": type(error).__name__ if error else None,
                "queue_status": queue_status
            }

            # Send notification using the template
            await self.discord.send_server_status(template_data)

            # Track offline state
            if not is_online and not self.server_was_offline:
                self._offline_since = time.time()
            elif is_online and self.server_was_offline:
                self._offline_since = None

        except Exception as e:
            self.logger.error(f"Failed to send server status notification: {e}")

    async def background_tasks(self) -> None:
        """
        Run background maintenance tasks.

        This method runs indefinitely and performs periodic maintenance
        tasks to keep the service healthy and performant. It's designed
        to run as a background task alongside webhook processing.

        **Background Tasks:**
            - Periodic library synchronization with Jellyfin
            - Database maintenance (VACUUM, cleanup)
            - Connection health monitoring
            - Performance optimization tasks

        **Task Scheduling:**
            Tasks are scheduled based on time intervals and system load.
            Critical tasks run more frequently, while maintenance tasks
            run during low-activity periods.

        Note:
            This method runs indefinitely until the service is shut down.
            All errors are caught and logged to prevent the background
            tasks from crashing the main service.
        """
        self.logger.info("Starting background maintenance tasks")

        while not self.shutdown_event.is_set():
            try:
                # Task 1: Periodic library sync (every 6 hours)
                if not self.sync_in_progress and self.initial_sync_complete:
                    sync_interval = 6 * 3600  # 6 hours in seconds

                    # Ensure _last_sync_time is always a float
                    last_sync = getattr(self, '_last_sync_time', 0.0)
                    if not isinstance(last_sync, (int, float)):
                        last_sync = 0.0
                        self._last_sync_time = 0.0

                    time_since_last_sync = time.time() - last_sync

                    if time_since_last_sync > sync_interval:
                        self.logger.info("Starting scheduled background library sync")
                        try:
                            result = await self.sync_jellyfin_library(background=True)
                            self.logger.info(f"Background sync completed: {result.get('status', 'unknown')}")
                            self._last_sync_time = time.time()
                        except Exception as e:
                            self.logger.error(f"Background sync failed: {e}")

                # Task 2: Database maintenance (weekly) - WITH TYPE SAFETY
                vacuum_interval = 7 * 24 * 3600  # 1 week in seconds

                # Ensure last_vacuum is always a float
                if not isinstance(self.last_vacuum, (int, float)) or self.last_vacuum is None:
                    self.logger.warning("last_vacuum was None or invalid, resetting to current time")
                    self.last_vacuum = time.time()

                time_since_vacuum = time.time() - self.last_vacuum

                if time_since_vacuum > vacuum_interval:
                    self.logger.info("Starting scheduled database maintenance")
                    try:
                        if await self.db.vacuum_database():
                            await self.db.update_vacuum_timestamp()  # Update in database too
                            self.last_vacuum = time.time()
                            self.logger.info("Database maintenance completed successfully")
                        else:
                            self.logger.warning("Database maintenance completed with warnings")
                    except Exception as e:
                        self.logger.error(f"Database maintenance failed: {e}")

                # Task 3: Jellyfin connectivity monitoring (UPDATED)
                try:
                    is_connected = await self.jellyfin.is_connected()

                    # Server went offline
                    if not is_connected and not self.server_was_offline:
                        self.logger.warning("Jellyfin server appears to be offline")
                        self.server_was_offline = True

                        # Send offline notification with enhanced data
                        await self.send_server_status_notification(
                            is_online=False,
                            error=Exception("Connection timeout or refused")
                        )

                    # Server came back online
                    elif is_connected and self.server_was_offline:
                        self.logger.info("Jellyfin server is back online")
                        self.server_was_offline = False

                        # Send online notification with recovery info
                        await self.send_server_status_notification(
                            is_online=True
                        )

                except Exception as e:
                    self.logger.debug(f"Connection check failed: {e}")

                    if not self.server_was_offline:
                        self.server_was_offline = True
                        await self.send_server_status_notification(
                            is_online=False,
                            error=e
                        )

                # Wait before next iteration (5 minutes)
                await asyncio.sleep(300)

            except Exception as e:
                self.logger.error(f"Background task error: {e}", exc_info=True)
                await asyncio.sleep(60)  # Wait 1 minute before retrying

        self.logger.info("Background tasks stopped - service is shutting down")
    
    async def _convert_item_safe(self, item_data: Dict[str, Any]):
        """
        Safely convert Jellyfin API item to DatabaseItem for efficient sync storage.
        
        This wrapper method ensures that conversion errors don't crash the batch
        processing and provides detailed error information for debugging.
        Uses DatabaseItem for efficient storage during syncs.
        
        Args:
            item_data: Raw item data from Jellyfin API
            
        Returns:
            DatabaseItem if conversion successful, None if failed
        """
        try:
            # Use the optimized DatabaseItem conversion for syncs
            return await self.jellyfin.convert_to_database_item(item_data)
        except Exception as e:
            # Log the error with item details for debugging
            item_id = item_data.get('Id', 'unknown')
            item_name = item_data.get('Name', 'unknown')
            item_type = item_data.get('Type', 'unknown')
            
            self.logger.debug(
                f"Failed to convert item {item_name} (ID: {item_id}, Type: {item_type}): {e}"
            )
            return None

    async def sync_jellyfin_library(self, background: bool = False) -> Dict[str, Any]:
        """
        Synchronize entire Jellyfin library to local database using streaming batch processing.

        This method performs a complete sync of the Jellyfin library using a producer-consumer
        pattern that streams batches from the API while concurrently processing them to the
        database. This provides optimal memory usage and performance for large libraries.

        **Streaming Architecture:**
            - Producer task: Fetches batches from Jellyfin API and queues them
            - Consumer task: Processes queued batches and saves to database
            - Concurrent execution with configurable queue size for backpressure
            - Memory-efficient: Only a few batches in memory at once

        **Enhanced Performance:**
            - Overlapping network I/O (API fetch) with database I/O (batch save)
            - True streaming: No accumulation of all items in memory
            - Real-time progress logging shows fetch and save operations
            - Partial progress saved even if sync fails midway

        **Background vs Foreground Sync:**
            - Background: Doesn't block webhook processing (for periodic syncs)
            - Foreground: Blocks webhook processing (for initial setup)

        Args:
            background (bool): Whether to run sync in background mode.
                Background syncs don't block webhook processing.

        Returns:
            Dict[str, Any]: Sync results including status, items processed, and timing

        Example:
            ```python
            # Perform initial sync (blocks webhooks)
            result = await service.sync_jellyfin_library(background=False)

            # Periodic sync (non-blocking)
            result = await service.sync_jellyfin_library(background=True)

            logger.info(f"Sync status: {result['status']}")
            logger.info(f"Items processed: {result['items_processed']}")
            ```

        Note:
            This streaming implementation is suitable for libraries with millions of items,
            providing consistent memory usage regardless of library size.
        """
        # Initialize timing variable
        sync_start_time = time.time()

        # Prevent multiple syncs from running simultaneously
        if self.sync_in_progress:
            self.logger.warning("Library sync already in progress - skipping")
            return {
                "status": "skipped",
                "message": "Sync already in progress",
                "items_processed": 0,
                "total_items": 0,
                "errors": 0,
                "processing_time": 0
            }

        try:
            # Set sync state flags
            self.sync_in_progress = True
            self.is_background_sync = background

            if background:
                self.logger.info("Starting background library sync...")
            else:
                self.logger.info("Starting foreground library sync...")

            # Check Jellyfin connectivity before starting
            if not await self.jellyfin.is_connected():
                self.logger.error("Cannot sync: Jellyfin server is not accessible")
                return {
                    "status": "error",
                    "message": "Jellyfin server not accessible",
                    "items_processed": 0,
                    "total_items": 0,
                    "errors": 0,
                    "processing_time": round(time.time() - sync_start_time, 2)
                }

            # Use adaptive batch sizing (will be determined based on library size)
            # API will automatically select optimal batch size
            self.logger.info("Starting streaming sync with adaptive batch sizing")

            # Create async queue for producer-consumer pattern
            # Queue size of 20 provides plenty of headroom for API requests without overloading memory
            batch_queue = asyncio.Queue(maxsize=20)
            
            # Shared state for tracking progress (thread-safe via asyncio)
            sync_state = {
                'total_items': 0,
                'items_fetched': 0,
                'items_processed': 0,
                'batch_errors': 0,
                'total_individual_errors': 0,
                'new_items': 0,
                'updated_items': 0,
                'producer_done': False,
                'consumer_done': False,
                'fatal_error': '',  # Empty string instead of None for type consistency
                'should_stop': False,  # Early exit flag for high error rates
                'batch_size': 200  # Default, will be updated
            }
            
            # Initialize progress display (will be set once we know total items)
            progress_display = None
            
            # Error threshold for early exit (stop if more than 10% of items fail)
            error_threshold_percent = 10
            consecutive_batch_error_limit = 3
            
            async def producer():
                """Fetch batches from Jellyfin API and queue them for processing."""
                nonlocal progress_display  # Declare nonlocal at the start of the function
                batch_num = 0
                try:
                    async for batch_items, total_count in self.jellyfin.get_items_stream():
                        batch_num += 1
                        sync_state['total_items'] = total_count
                        sync_state['items_fetched'] += len(batch_items)
                        sync_state['batch_size'] = len(batch_items)  # Update batch size
                        
                        # Initialize progress display on first batch
                        if batch_num == 1 and progress_display is None:
                            sync_type = "initial" if not background else "background"
                            progress_display = SyncProgressDisplay(
                                total_items=total_count,
                                batch_size=len(batch_items),
                                sync_type=sync_type,
                                logger=self.logger
                            )
                            progress_display.log_sync_start()
                        
                        # Update progress display instead of basic logging
                        if progress_display:
                            progress_display.log_batch_progress(
                                batch_num=batch_num,
                                items_in_batch=len(batch_items),
                                total_fetched=sync_state['items_fetched'],
                                items_processed=sync_state['items_processed'],
                                errors=sync_state['total_individual_errors'],
                                new_items=sync_state.get('new_items', 0),
                                updated_items=sync_state.get('updated_items', 0)
                            )
                        else:
                            # Fallback to basic logging
                            self.logger.info(
                                f"Fetched batch {batch_num} from API: {len(batch_items)} items "
                                f"(total fetched: {sync_state['items_fetched']}/{total_count})"
                            )
                        
                        # Check if we should stop due to high error rate
                        if sync_state['should_stop']:
                            self.logger.warning("Producer stopping early due to high error rate")
                            break
                        
                        # Queue the batch for processing
                        await batch_queue.put((batch_num, batch_items))
                        
                    # Signal completion
                    await batch_queue.put(None)
                    sync_state['producer_done'] = True
                    self.logger.info(f"API fetch completed: {sync_state['items_fetched']} total items fetched")
                    
                except Exception as e:
                    self.logger.error(f"Producer task failed: {e}")
                    sync_state['fatal_error'] = str(e)
                    # Signal error to consumer
                    await batch_queue.put(None)
                    sync_state['producer_done'] = True
            
            async def consumer():
                """Process batches from queue and save to database."""
                nonlocal progress_display  # Declare nonlocal at the start of the function
                consecutive_batch_errors = 0
                try:
                    while True:
                        # Get batch from queue
                        batch_data = await batch_queue.get()
                        
                        # Check for completion signal
                        if batch_data is None:
                            break
                            
                        batch_num, batch_items = batch_data
                        batch_start_time = time.time()
                        
                        # Don't log processing here, it's handled by progress display
                        self.logger.debug(
                            f"Processing batch {batch_num}: {len(batch_items)} items "
                            f"(queue size: {batch_queue.qsize()})"
                        )
                        
                        try:
                            # Convert API data to DatabaseItem objects in parallel for speed
                            db_items = []
                            conversion_errors = 0
                            failed_items = []
                            
                            # Time the conversion process
                            conversion_start_time = time.time()
                            
                            # Create conversion tasks for parallel processing
                            conversion_tasks = []
                            for item_data in batch_items:
                                # Create task with item data for error tracking
                                task = asyncio.create_task(self._convert_item_safe(item_data))
                                conversion_tasks.append((task, item_data))
                            
                            # Wait for all conversions to complete
                            results = await asyncio.gather(*[task for task, _ in conversion_tasks], return_exceptions=True)
                            
                            conversion_time = time.time() - conversion_start_time
                            
                            # Process results
                            for (task, item_data), result in zip(conversion_tasks, results):
                                if isinstance(result, Exception):
                                    item_id = item_data.get('Id', 'unknown')
                                    item_name = item_data.get('Name', 'unknown')
                                    failed_items.append((item_id, item_name, str(result)))
                                    conversion_errors += 1
                                    sync_state['total_individual_errors'] += 1
                                elif result is not None:
                                    db_items.append(result)
                            
                            # Log conversion errors if any
                            if failed_items:
                                self.logger.warning(
                                    f"Batch {batch_num}: {conversion_errors} items failed conversion"
                                )
                                # Log first few failed items for debugging
                                for item_id, item_name, error in failed_items[:3]:
                                    self.logger.debug(
                                        f"  - Failed item: {item_name} (ID: {item_id}): {error}"
                                    )
                                if len(failed_items) > 3:
                                    self.logger.debug(f"  ... and {len(failed_items) - 3} more")
                            
                            # Log conversion performance
                            if db_items:
                                conv_time_ms = conversion_time * 1000
                                conv_per_item_ms = conv_time_ms / len(db_items) if db_items else 0
                                self.logger.debug(
                                    f"DatabaseItem conversion for {len(db_items)} items: "
                                    f"Total: {conv_time_ms:.1f}ms, "
                                    f"Avg: {conv_per_item_ms:.2f}ms/item"
                                )
                            
                            # Pre-generate content hashes to measure performance
                            # This triggers the lazy hash calculation before database save
                            # Note: We don't parallelize this because:
                            # 1. Our hash data is <2KB (below GIL release threshold of 2047 bytes)
                            # 2. Blake2b is already very fast for small data
                            # 3. Database I/O is the actual bottleneck
                            if db_items:
                                hash_start_time = time.time()
                                hash_generation_times = []
                                
                                for item in db_items:
                                    try:
                                        item_hash_start = time.time()
                                        # Access the property to trigger hash generation
                                        _ = item.content_hash
                                        item_hash_time = time.time() - item_hash_start
                                        hash_generation_times.append(item_hash_time)
                                    except Exception as e:
                                        self.logger.debug(f"Hash generation failed for {item.name}: {e}")
                                
                                total_hash_time = time.time() - hash_start_time
                                
                                # Log hash generation performance statistics
                                if hash_generation_times:
                                    avg_hash_time_ms = (sum(hash_generation_times) / len(hash_generation_times)) * 1000
                                    max_hash_time_ms = max(hash_generation_times) * 1000
                                    total_hash_time_ms = total_hash_time * 1000
                                    hashes_per_second = len(hash_generation_times) / total_hash_time if total_hash_time > 0 else 0
                                    
                                    self.logger.debug(
                                        f"Hash generation stats for {len(db_items)} items: "
                                        f"Total: {total_hash_time_ms:.1f}ms, "
                                        f"Avg: {avg_hash_time_ms:.2f}ms/item, "
                                        f"Max: {max_hash_time_ms:.2f}ms, "
                                        f"Rate: {hashes_per_second:.0f} hashes/sec"
                                    )
                            
                            # Save batch to database with timing
                            if db_items:
                                db_save_start = time.time()
                                batch_results = await self.db.save_items_batch(db_items)
                                db_save_time = time.time() - db_save_start
                                
                                # Check if entire batch failed
                                if batch_results['failed'] == len(db_items) and batch_results['successful'] == 0:
                                    sync_state['batch_errors'] += 1
                                    sync_state['total_individual_errors'] += batch_results['failed']
                                    consecutive_batch_errors += 1
                                    
                                    self.logger.error(
                                        f"Batch {batch_num}: ENTIRE BATCH FAILED - "
                                        f"likely schema mismatch or database issue. "
                                        f"{batch_results['failed']} items could not be saved."
                                    )
                                    
                                    # Check for consecutive batch failures
                                    if consecutive_batch_errors >= consecutive_batch_error_limit:
                                        self.logger.error(
                                            f"Stopping sync: {consecutive_batch_errors} consecutive batches failed completely"
                                        )
                                        sync_state['should_stop'] = True
                                        sync_state['fatal_error'] = f"Too many consecutive batch failures: {consecutive_batch_errors}"
                                        break
                                else:
                                    # Reset consecutive error counter on successful batch
                                    if batch_results['successful'] > 0:
                                        consecutive_batch_errors = 0
                                    
                                    # Update progress
                                    sync_state['items_processed'] += batch_results['successful']
                                    sync_state['total_individual_errors'] += batch_results['failed']
                                    
                                    # Track new vs updated items
                                    if 'new' in batch_results:
                                        sync_state['new_items'] += batch_results['new']
                                    if 'updated' in batch_results:
                                        sync_state['updated_items'] += batch_results['updated']
                                    
                                    batch_time = time.time() - batch_start_time
                                    
                                    # Log batch save completion with breakdown
                                    self.logger.debug(
                                        f"Batch {batch_num} saved to database: "
                                        f"{batch_results['successful']}/{len(db_items)} items "
                                        f"(Total: {batch_time:.2f}s, DB: {db_save_time:.2f}s)"
                                    )
                                    
                                    # Log performance breakdown if timing data is available
                                    if 'total_hash_time' in locals() and 'conversion_time' in locals():
                                        hash_percent = (total_hash_time / batch_time) * 100 if batch_time > 0 else 0
                                        db_percent = (db_save_time / batch_time) * 100 if batch_time > 0 else 0
                                        conversion_percent = (conversion_time / batch_time) * 100 if batch_time > 0 else 0
                                        other_percent = 100 - hash_percent - db_percent - conversion_percent
                                        
                                        self.logger.debug(
                                            f"Batch {batch_num} performance breakdown: "
                                            f"Conversion: {conversion_percent:.1f}%, "
                                            f"Hashing: {hash_percent:.1f}%, "
                                            f"DB Save: {db_percent:.1f}%, "
                                            f"Other: {other_percent:.1f}%"
                                        )
                                    
                                    # Log failures if any
                                    if batch_results['failed'] > 0:
                                        self.logger.warning(
                                            f"Batch {batch_num}: {batch_results['failed']} items failed to save"
                                        )
                            else:
                                # All items in batch failed conversion
                                self.logger.warning(f"Batch {batch_num}: All {len(batch_items)} items failed conversion")
                                sync_state['batch_errors'] += 1
                                consecutive_batch_errors += 1
                                
                                # Check for consecutive failures
                                if consecutive_batch_errors >= consecutive_batch_error_limit:
                                    self.logger.error(
                                        f"Stopping sync: {consecutive_batch_errors} consecutive batches failed completely"
                                    )
                                    sync_state['should_stop'] = True
                                    sync_state['fatal_error'] = f"Too many consecutive batch failures: {consecutive_batch_errors}"
                                    break
                            
                            # Progress is now handled by the progress display in producer
                            # Just update the progress display reference if needed
                            if progress_display and batch_num % 5 == 0:
                                # Update cumulative stats in progress display
                                progress_display.items_processed = sync_state['items_processed']
                                progress_display.errors = sync_state['total_individual_errors']
                                progress_display.new_items = sync_state.get('new_items', 0)
                                progress_display.updated_items = sync_state.get('updated_items', 0)
                                
                                # Check error rate and stop if too high
                                if sync_state['items_processed'] > 100:  # Only check after processing some items
                                    error_rate = (sync_state['total_individual_errors'] / sync_state['items_processed']) * 100
                                    if error_rate > error_threshold_percent:
                                        self.logger.error(
                                            f"Stopping sync: Error rate {error_rate:.1f}% exceeds threshold {error_threshold_percent}%"
                                        )
                                        sync_state['should_stop'] = True
                                        sync_state['fatal_error'] = f"Error rate too high: {error_rate:.1f}%"
                                        break
                            
                        except Exception as e:
                            self.logger.error(f"Error processing batch {batch_num}: {e}")
                            sync_state['batch_errors'] += 1
                            sync_state['total_individual_errors'] += len(batch_items)
                        
                        # Small delay to prevent overwhelming the database
                        if not sync_state['producer_done']:
                            await asyncio.sleep(0.1)  # Hardcoded optimal delay
                    
                    sync_state['consumer_done'] = True
                    self.logger.info(f"Database processing completed: {sync_state['items_processed']} items saved")
                    
                except Exception as e:
                    self.logger.error(f"Consumer task failed: {e}")
                    sync_state['fatal_error'] = str(e)
                    sync_state['consumer_done'] = True
            
            # Run producer and consumer concurrently
            producer_task = asyncio.create_task(producer())
            consumer_task = asyncio.create_task(consumer())
            
            try:
                # Wait for both tasks to complete
                await asyncio.gather(producer_task, consumer_task)
            except Exception as e:
                self.logger.error(f"Sync tasks failed: {e}")
                sync_state['fatal_error'] = str(e)
                # Cancel any running tasks
                producer_task.cancel()
                consumer_task.cancel()
            
            # Update last sync time in database
            try:
                await self.db.update_last_sync_time()
            except Exception as e:
                self.logger.warning(f"Could not update last sync time: {e}")
            
            processing_time = time.time() - sync_start_time
            
            # Determine final status
            total_items = sync_state['total_items']
            items_processed = sync_state['items_processed']
            total_individual_errors = sync_state['total_individual_errors']
            batch_errors = sync_state['batch_errors']
            
            if total_items == 0:
                return {
                    "status": "warning",
                    "message": "No items found in library",
                    "items_processed": 0,
                    "total_items": 0,
                    "errors": 0,
                    "processing_time": round(processing_time, 2)
                }
            
            success_rate = (items_processed / total_items) * 100 if total_items > 0 else 0

            if total_individual_errors == 0:
                status = "success"
            elif success_rate >= 50:  # More than half succeeded
                status = "partial"
            else:
                status = "error"

            # Use progress display for completion summary if available
            if progress_display:
                progress_display.items_processed = items_processed
                progress_display.errors = total_individual_errors
                progress_display.new_items = sync_state.get('new_items', 0)
                progress_display.updated_items = sync_state.get('updated_items', 0)
                progress_display.log_sync_complete(success=(status == "success"))
            else:
                # Fallback to basic logging
                self.logger.info("=" * 80)
                self.logger.info(f"Library sync completed with status: {status.upper()}")
                self.logger.info(f"  Items processed: {items_processed:,}/{total_items:,}")
                self.logger.info(f"  Success rate: {success_rate:.1f}%")
                self.logger.info(f"  Individual errors: {total_individual_errors:,}")
                self.logger.info(f"  Batch errors: {batch_errors:,}")
                self.logger.info(f"  Processing time: {processing_time:.2f}s")
                self.logger.info(f"  Throughput: {items_processed / processing_time:.1f} items/sec")
                self.logger.info(f"  Batch size used: {api_batch_size:,}")
                self.logger.info("=" * 80)

            return {
                "status": status,
                "items_processed": items_processed,
                "total_items": total_items,
                "new_items": sync_state.get('new_items', 0),
                "updated_items": sync_state.get('updated_items', 0),
                "errors": total_individual_errors,
                "batch_errors": batch_errors,
                "success_rate": round(success_rate, 1),
                "processing_time": round(processing_time, 2),
                "throughput": round(items_processed / processing_time, 1) if processing_time > 0 else 0,
                "batch_size_used": sync_state.get('batch_size', 200)
            }

        except Exception as e:
            processing_time = time.time() - sync_start_time
            self.logger.error(f"Library sync failed after {processing_time:.2f}s: {e}")
            return {
                "status": "error",
                "message": str(e),
                "items_processed": 0,
                "total_items": 0,
                "errors": 0,
                "processing_time": round(processing_time, 2)
            }

        finally:
            # Always reset sync flags, even if an error occurred
            self.sync_in_progress = False
            self.is_background_sync = False

    async def _check_initial_sync(self) -> None:
        """
        Check if initial sync is needed and perform it.

        This private method determines whether the service needs to perform
        an initial library sync. It's called during service initialization
        to ensure the database is populated with existing library content.

        **Initial Sync Logic:**
            The service creates a marker file after successful initial sync.
            If this marker doesn't exist, we perform initial sync to populate
            the database with existing Jellyfin library content.

        **Why Initial Sync Matters:**
            Without initial sync, all existing library items would be treated
            as "new" when webhooks are received, resulting in duplicate
            notifications for content that already existed.

        Note:
            This method runs a complete library sync and blocks webhook processing
            until it completes. It's only used on the very first service startup
            to populate the database with existing library content.

        **Why Block During Initial Sync?**
            We need a complete picture of the library before processing webhooks,
            otherwise we might treat existing items as "new" items.
        """
        try:
            # Check for completion marker
            init_complete_path = Path("/app/data/init_complete")

            if not init_complete_path.exists():
                self.logger.info("No initial sync marker found - performing initial library sync")
                await self._perform_initial_sync()
            else:
                self.logger.info("Initial sync marker found - skipping initial sync")
                self.initial_sync_complete = True

        except Exception as e:
            self.logger.error(f"Error checking initial sync status: {e}")

    async def _perform_initial_sync(self) -> None:
        """
        Perform initial library synchronization.

        This private method runs a complete library sync and blocks webhook processing
        until it completes. It's only used on the very first service startup
        to populate the database with existing library content.

        **Why Block During Initial Sync?**
            We need a complete picture of the library before processing webhooks,
            otherwise we might treat existing items as "new" items.
        """
        try:
            self.logger.info("Starting initial Jellyfin library sync...")
            result = await self.sync_jellyfin_library()

            # Create completion marker only if sync was successful
            if result.get("status") == "success":
                init_complete_path = Path("/app/data/init_complete")
                try:
                    init_complete_path.touch(exist_ok=True)
                    self.logger.info("Initial sync completed successfully - created completion marker")
                    self.initial_sync_complete = True
                    self._last_sync_time = time.time()
                    self.logger.debug(f"Set initial sync timestamp: {self._last_sync_time}")

                except Exception as e:
                    self.logger.warning(f"Could not create completion marker: {e}")
            else:
                self.logger.warning(f"Initial sync completed with status: {result.get('status', 'unknown')}")

        except Exception as e:
            self.logger.error(f"Initial sync failed: {e}")
            # Don't raise - service can continue without initial sync

    async def cleanup(self) -> None:
        """
        Clean up service resources during shutdown.

        This method performs graceful cleanup of all service components
        and resources. It's called during application shutdown to ensure
        proper resource cleanup and prevent data loss.

        **Cleanup Tasks:**
            - Signal background tasks to stop
            - Close database connections
            - Close HTTP sessions
            - Flush any pending operations
            - Log shutdown completion

        Example:
            ```python
            # During application shutdown
            await webhook_service.cleanup()
            logger.info("Service cleanup completed")
            ```

        Note:
            This method should be called during application shutdown
            to ensure proper resource cleanup. It's designed to be
            safe to call multiple times.
        """
        try:
            self.logger.info("Starting service cleanup...")

            # Signal background tasks to stop
            self.shutdown_event.set()

            # Close metadata service (which handles TVDB cleanup internally)
            if self.metadata_service:
                try:
                    await self.metadata_service.cleanup()
                    self.logger.debug("Metadata service cleaned up")
                except Exception as e:
                    self.logger.error(f"Error cleaning up metadata service: {e}")

            # Close database connections
            if self.db:
                await self.db.close()
                self.logger.debug("Database connections closed")

            # Close Discord notifier and its sessions
            if hasattr(self, 'discord') and self.discord:
                await self.discord.cleanup()
                self.logger.debug("Discord notifier cleaned up")

            self.logger.info("Service cleanup completed successfully")

        except Exception as e:
            self.logger.error(f"Error during service cleanup: {e}")
    
    async def _handle_item_deleted(self, payload: WebhookPayload) -> Dict[str, Any]:
        """
        Handle ItemDeleted notifications with filtering for upgrades.
        
        When an item is deleted, we don't immediately send a notification.
        Instead, we queue it and wait to see if an ItemAdded comes shortly after
        (indicating an upgrade or rename).
        
        Args:
            payload: The deletion webhook payload
            
        Returns:
            Processing result dictionary
        """
        start_time = time.time()
        
        # Enhanced debug logging for delete events
        self.logger.debug("=" * 60)
        self.logger.debug("🗑️ ITEM DELETION WEBHOOK RECEIVED")
        self.logger.debug("=" * 60)
        self.logger.debug(f"  Item Name: {payload.Name}")
        self.logger.debug(f"  Item ID: {payload.ItemId}")
        self.logger.debug(f"  Item Type: {payload.ItemType}")
        self.logger.debug(f"  Library: {getattr(payload, 'LibraryName', 'Unknown')}")
        self.logger.debug(f"  Path: {getattr(payload, 'Path', 'Not provided')}")
        self.logger.debug(f"  Server: {payload.ServerName}")
        self.logger.debug(f"  User: {payload.Username}")
        self.logger.debug(f"  Delete filtering enabled: {self.config.notifications.filter_deletes}")
        self.logger.debug(f"  Rename filtering enabled: {self.config.notifications.filter_renames}")
        self.logger.debug("=" * 60)
        
        # Check if deletion filtering is enabled
        if self.config.notifications.filter_deletes:
            # Store deletion info with timestamp
            deletion_key = f"{payload.Name}_{payload.ItemType}"
            self.pending_deletions[deletion_key] = {
                'payload': payload,
                'timestamp': time.time(),
                'item_id': payload.ItemId,
                'file_path': getattr(payload, 'Path', None)
            }
            
            self.logger.info(f"Queued deletion for {payload.Name} - waiting for potential upgrade")
            self.logger.debug(f"  Deletion key: {deletion_key}")
            self.logger.debug(f"  Pending deletions queue size: {len(self.pending_deletions)}")
            
            # Start cleanup task if not running
            if not self.deletion_cleanup_task or self.deletion_cleanup_task.done():
                self.deletion_cleanup_task = asyncio.create_task(self._cleanup_old_deletions())
            
            return {
                "status": "queued",
                "action": "deletion_queued",
                "item_id": payload.ItemId,
                "item_name": payload.Name,
                "message": "Deletion queued for upgrade detection",
                "processing_time": round(time.time() - start_time, 3)
            }
        else:
            # Send deletion notification immediately if filtering is disabled
            return await self._send_deletion_notification(payload)
    
    async def _check_pending_deletion(self, item_name: str, item_type: str) -> Optional[Dict]:
        """
        Check if there's a pending deletion for this item.
        
        Args:
            item_name: Name of the item being added
            item_type: Type of the item
            
        Returns:
            Deletion info if found, None otherwise
        """
        deletion_key = f"{item_name}_{item_type}"
        return self.pending_deletions.get(deletion_key)
    
    async def _handle_potential_upgrade(self, add_payload: WebhookPayload, deletion_info: Dict) -> Dict[str, Any]:
        """
        Handle a potential upgrade or rename scenario.
        
        Args:
            add_payload: The ItemAdded webhook payload
            deletion_info: Information about the previous deletion
            
        Returns:
            Processing result dictionary
        """
        start_time = time.time()
        deletion_key = f"{add_payload.Name}_{add_payload.ItemType}"
        
        # Remove from pending deletions
        del self.pending_deletions[deletion_key]
        
        # Get item details to check if it's a rename or upgrade
        item_data = await self.jellyfin.get_item(add_payload.ItemId)
        if not item_data:
            # Can't determine, treat as normal add
            return await self._process_item_added(add_payload)
        
        # Convert to MediaItem for comparison
        new_item = await self.jellyfin.convert_to_media_item(item_data)
        
        # Check if this is just a rename (same content hash = same file, just moved/renamed)
        # NOTE: ItemId changes when files are renamed in Jellyfin, so we can't compare by ID
        is_rename = False
        if self.config.notifications.filter_renames:
            # Get the OLD item from database using the deletion's item_id
            old_item = await self.db.get_item(deletion_info['item_id'])
            if old_item:
                # Compare content hashes - if they match, it's the same file content
                # Since we exclude file_path from hash, only actual quality changes will differ
                if old_item.content_hash == new_item.content_hash:
                    is_rename = True
                    self.logger.info(f"Detected rename/move for {add_payload.Name} (matching content hash) - filtering notification")
                    self.logger.debug(f"  Old ItemId: {deletion_info['item_id']}")
                    self.logger.debug(f"  New ItemId: {add_payload.ItemId}")
                    self.logger.debug(f"  Old Path: {deletion_info.get('file_path', 'unknown')}")
                    self.logger.debug(f"  New Path: {new_item.file_path}")
                else:
                    # Different hash means actual content changes (quality upgrade)
                    changes = await self.change_detector.detect_changes(old_item, new_item)
                    self.logger.debug(f"Content changed for {add_payload.Name}: {len(changes)} changes detected")
        
        if is_rename:
            # Just update the database, don't send notification
            await self.db.save_item(new_item)
            return {
                "status": "filtered",
                "action": "rename_filtered",
                "item_id": add_payload.ItemId,
                "item_name": add_payload.Name,
                "message": "Rename detected and filtered",
                "processing_time": round(time.time() - start_time, 3)
            }
        else:
            # This is an upgrade - process normally but skip the deletion notification
            self.logger.info(f"Detected upgrade for {add_payload.Name} - processing as upgrade")
            return await self._process_item_added(add_payload)
    
    async def _process_item_added(self, payload: WebhookPayload) -> Dict[str, Any]:
        """
        Process a normal ItemAdded notification.
        
        This is a helper method that contains the original ItemAdded logic.
        
        Args:
            payload: The webhook payload
            
        Returns:
            Processing result dictionary
        """
        # This will contain the rest of the original process_webhook logic
        # Moving it here for clarity
        start_time = time.time()
        
        # Get detailed item information from Jellyfin
        item_data = await self.jellyfin.get_item(payload.ItemId)
        if not item_data:
            return {
                "status": "error",
                "action": "fetch_failed",
                "item_id": payload.ItemId,
                "item_name": payload.Name,
                "message": "Could not fetch item data from Jellyfin"
            }
        
        # Continue with the rest of the original logic...
        # (This would be moved from the main process_webhook method)
        media_item = await self.jellyfin.convert_to_media_item(item_data)
        media_item.server_id = payload.ServerId
        media_item.server_name = payload.ServerName
        media_item.server_version = payload.ServerVersion
        media_item.server_url = payload.ServerUrl
        
        # Use provider IDs from webhook as they are the real-time notification data
        # The webhook is the source of truth for what was just added
        if hasattr(payload, 'Provider_imdb') and payload.Provider_imdb:
            media_item.imdb_id = payload.Provider_imdb
            self.logger.debug(f"Using IMDB ID from webhook: {payload.Provider_imdb}")
        if hasattr(payload, 'Provider_tmdb') and payload.Provider_tmdb:
            media_item.tmdb_id = payload.Provider_tmdb  
            self.logger.debug(f"Using TMDB ID from webhook: {payload.Provider_tmdb}")
        if hasattr(payload, 'Provider_tvdb') and payload.Provider_tvdb:
            media_item.tvdb_id = payload.Provider_tvdb
            self.logger.debug(f"Using TVDB ID from webhook: {payload.Provider_tvdb}")
        if hasattr(payload, 'Provider_tvdbslug') and payload.Provider_tvdbslug:
            media_item.tvdb_slug = payload.Provider_tvdbslug
            self.logger.debug(f"Using TVDB slug from webhook: {payload.Provider_tvdbslug}")
        
        existing_item = await self.db.get_item(media_item.item_id)
        
        if existing_item:
            changes = await self.change_detector.detect_changes(existing_item, media_item)
            if changes:
                await self.db.save_item(media_item)
                enriched_item = await self.jellyfin.enrich_media_item_for_notification(
                    media_item, item_data, retry_on_failure=True
                )
                # Get metadata for upgraded item
                metadata = {}
                if self.metadata_service and self.metadata_service.enabled:
                    try:
                        metadata = await self.metadata_service.enrich_media_item(enriched_item)
                    except Exception as e:
                        self.logger.error(f"Error enriching upgraded item with metadata: {e}")
                
                await self.discord.send_notification(enriched_item, "upgraded_item", changes, metadata=metadata)
                return {
                    "status": "success",
                    "action": "upgraded_item",
                    "item_id": media_item.item_id,
                    "item_name": media_item.name,
                    "changes": len(changes),
                    "processing_time": round(time.time() - start_time, 3)
                }
            else:
                await self.db.save_item(media_item)
                return {
                    "status": "success",
                    "action": "metadata_updated",
                    "item_id": media_item.item_id,
                    "item_name": media_item.name,
                    "processing_time": round(time.time() - start_time, 3)
                }
        else:
            await self.db.save_item(media_item)
            metadata = {}
            if self.metadata_service and self.metadata_service.enabled:
                try:
                    metadata = await self.metadata_service.enrich_media_item(media_item)
                except Exception as e:
                    self.logger.error(f"Error enriching item with metadata: {e}")
            
            await self.discord.send_notification(media_item, "new_item", metadata=metadata)
            return {
                "status": "success",
                "action": "new_item",
                "item_id": media_item.item_id,
                "item_name": media_item.name,
                "processing_time": round(time.time() - start_time, 3)
            }
    
    async def _send_deletion_notification(self, payload: WebhookPayload) -> Dict[str, Any]:
        """
        Send a deletion notification to Discord.
        
        Args:
            payload: The deletion webhook payload
            
        Returns:
            Processing result dictionary
        """
        start_time = time.time()
        
        self.logger.debug("=" * 60)
        self.logger.debug("🗑️ SENDING DELETION NOTIFICATION")
        self.logger.debug("=" * 60)
        self.logger.debug(f"  Item: {payload.Name}")
        self.logger.debug(f"  Type: {payload.ItemType}")
        self.logger.debug(f"  ID: {payload.ItemId}")
        self.logger.debug("=" * 60)
        
        try:
            # Create a minimal MediaItem for the deletion notification
            from media_models import MediaItem
            
            deleted_item = MediaItem(
                item_id=payload.ItemId,
                name=payload.Name,
                item_type=payload.ItemType,
                server_id=payload.ServerId,
                server_name=payload.ServerName,
                server_version=payload.ServerVersion,
                server_url=payload.ServerUrl,
                file_path=getattr(payload, 'Path', None),
                content_hash="",  # Required field
                timestamp_created=str(int(time.time()))
            )
            
            # Send deletion notification
            await self.discord.send_notification(deleted_item, "deleted_item")
            
            self.logger.info(f"Sent deletion notification for {payload.Name}")
            
            return {
                "status": "success",
                "action": "item_deleted",
                "item_id": payload.ItemId,
                "item_name": payload.Name,
                "processing_time": round(time.time() - start_time, 3)
            }
        except Exception as e:
            self.logger.error(f"Failed to send deletion notification: {e}")
            return {
                "status": "error",
                "action": "deletion_failed",
                "item_id": payload.ItemId,
                "item_name": payload.Name,
                "error": str(e),
                "processing_time": round(time.time() - start_time, 3)
            }
    
    async def _cleanup_old_deletions(self):
        """
        Background task to clean up old pending deletions.
        
        This runs periodically to process deletions that weren't followed
        by an add (true deletions, not upgrades).
        """
        self.logger.debug("Starting deletion cleanup task")
        
        while not self.shutdown_event.is_set():
            try:
                await asyncio.sleep(10)  # Check every 10 seconds
                
                if self.pending_deletions:
                    self.logger.debug(f"Checking {len(self.pending_deletions)} pending deletions for expiry")
                
                current_time = time.time()
                expired_deletions = []
                
                # Find expired deletions
                for key, info in self.pending_deletions.items():
                    age = current_time - info['timestamp']
                    if age > self.deletion_timeout:
                        expired_deletions.append(key)
                        self.logger.debug(f"  - {key}: aged {age:.1f}s (expired, timeout={self.deletion_timeout}s)")
                    else:
                        self.logger.debug(f"  - {key}: aged {age:.1f}s (waiting, timeout={self.deletion_timeout}s)")
                
                # Process expired deletions
                for key in expired_deletions:
                    info = self.pending_deletions.pop(key)
                    self.logger.info(f"Processing expired deletion for {info['payload'].Name} (no upgrade detected)")
                    await self._send_deletion_notification(info['payload'])
                    
            except Exception as e:
                self.logger.error(f"Error in deletion cleanup task: {e}")
                await asyncio.sleep(30)  # Wait longer on error