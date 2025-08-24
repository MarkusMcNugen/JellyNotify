#!/usr/bin/env python3
"""
Jellynouncer Main Entry Point

This is the main entry point for the Jellynouncer application. It launches both 
the webhook service and web interface simultaneously, managing their lifecycle 
and ensuring proper shutdown handling.

The launcher uses multiprocessing to run both services in separate processes
and handles signals for graceful shutdown in Docker environments.

Services:
    - Webhook API: Receives webhooks from Jellyfin (port 1984)
    - Web Interface: Management UI and API (port 1985/9000)

Author: Mark Newton
Project: Jellynouncer
Version: 1.0.0
License: MIT
"""

import os
import sys
import asyncio
import signal
import platform
from multiprocessing import Process, set_start_method
from typing import Optional

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set multiprocessing start method for Windows compatibility
# This doesn't affect Linux/Docker which already use 'fork' by default
if platform.system() == 'Windows':
    try:
        set_start_method('spawn', force=True)
    except RuntimeError:
        # Already set, ignore
        pass

from jellynouncer.utils import setup_logging, get_logger
from jellynouncer.network_utils import log_jellynouncer_startup


class ServiceLauncher:
    """Manages launching and coordinating both services"""
    
    def __init__(self):
        self.webhook_process: Optional[Process] = None
        self.web_process: Optional[Process] = None
        self.logger = None  # Will be initialized after setup_logging
        self.running = False
        
    def start_webhook_service(self):
        """Start the webhook service in a separate process"""
        try:
            # Setup logging for the webhook service process
            log_level = os.environ.get("LOG_LEVEL", "INFO")
            log_dir = os.environ.get("LOG_DIR", "/app/logs")
            if not os.path.exists('/.dockerenv'):
                log_dir = "logs"
            setup_logging(log_level, log_dir)
            
            # Get logger after setup_logging
            logger = get_logger("launcher")
            
            # Import here to avoid circular imports
            from jellynouncer import webhook_api
            
            logger.info("Starting Webhook Service on port 1984...")
            
            # Run the webhook service
            import uvicorn
            uvicorn.run(
                "jellynouncer.webhook_api:app",
                host="0.0.0.0",
                port=1984,
                log_level=os.environ.get("LOG_LEVEL", "info").lower(),
                access_log=False  # We have our own logging
            )
        except Exception as e:
            logger = get_logger("launcher")
            logger.error(f"Webhook service failed: {e}")
            sys.exit(1)
    
    def start_web_service(self):
        """Start the web interface in a separate process"""
        try:
            # Setup logging for the web service process
            log_level = os.environ.get("LOG_LEVEL", "INFO")
            log_dir = os.environ.get("LOG_DIR", "/app/logs")
            if not os.path.exists('/.dockerenv'):
                log_dir = "logs"
            setup_logging(log_level, log_dir)
            
            # Get logger after setup_logging
            logger = get_logger("launcher")
            
            # Import here to avoid circular imports
            from jellynouncer import web_api
            
            logger.info("Starting Web Interface on port 1985...")
            
            # Check if SSL is configured
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            ssl_config = loop.run_until_complete(web_api.get_ssl_config())
            
            port = ssl_config.get("port", 1985)
            protocol = "https" if ssl_config.get("ssl_context") else "http"
            
            logger.info(f"Web Interface will be available at {protocol}://localhost:{port}")
            
            # Run the web interface
            import uvicorn
            uvicorn.run(
                "jellynouncer.web_api:app",
                host="0.0.0.0",
                port=port,
                ssl_keyfile=ssl_config.get("ssl_keyfile"),
                ssl_certfile=ssl_config.get("ssl_certfile"),
                log_level=os.environ.get("LOG_LEVEL", "info").lower(),
                access_log=False  # We have our own logging
            )
        except Exception as e:
            logger = get_logger("launcher")
            logger.error(f"Web service failed: {e}")
            sys.exit(1)
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        # frame parameter is required by signal handler signature but not used
        _ = frame
        if self.logger:
            self.logger.info(f"Received signal {signum}, shutting down services...")
        self.shutdown()
    
    def shutdown(self):
        """Shutdown both services gracefully"""
        self.running = False
        
        if self.webhook_process and self.webhook_process.is_alive():
            if self.logger:
                self.logger.info("Stopping webhook service...")
            self.webhook_process.terminate()
            self.webhook_process.join(timeout=5)
            if self.webhook_process.is_alive():
                self.webhook_process.kill()
        
        if self.web_process and self.web_process.is_alive():
            if self.logger:
                self.logger.info("Stopping web interface...")
            self.web_process.terminate()
            self.web_process.join(timeout=5)
            if self.web_process.is_alive():
                self.web_process.kill()
        
        if self.logger:
            self.logger.info("All services stopped")
    
    def run(self):
        """Main entry point to run both services"""
        try:
            # Setup logging
            log_level = os.environ.get("LOG_LEVEL", "INFO")
            log_dir = os.environ.get("LOG_DIR", "/app/logs")
            if not os.path.exists('/.dockerenv'):
                log_dir = "logs"
            setup_logging(log_level, log_dir)
            
            # Now initialize the logger after setup_logging
            self.logger = get_logger("launcher")
            
            # Log startup banner
            log_jellynouncer_startup()
            
            self.logger.info("=" * 60)
            self.logger.info("Starting Jellynouncer Services")
            self.logger.info("=" * 60)
            
            # Setup signal handlers for graceful shutdown
            signal.signal(signal.SIGINT, self.signal_handler)
            signal.signal(signal.SIGTERM, self.signal_handler)
            
            # Check if we should run only one service (for development)
            # Get run mode from config or environment override
            from jellynouncer.config_models import ConfigurationValidator
            config_validator = ConfigurationValidator()
            config = config_validator.load_and_validate_config()
            run_mode = os.environ.get("JELLYNOUNCER_RUN_MODE", config.server.run_mode).lower()
            
            if run_mode in ["all", "both"]:
                # Start both services
                self.webhook_process = Process(target=self.start_webhook_service)
                self.web_process = Process(target=self.start_web_service)
                
                self.webhook_process.start()
                self.web_process.start()
                
                self.logger.info("Both services started successfully")
                self.logger.info("Webhook Service: http://localhost:1984")
                self.logger.info("Web Interface: http://localhost:1985")
                
                # Wait for both processes
                self.running = True
                while self.running:
                    # Check if processes are still alive
                    if not self.webhook_process.is_alive():
                        self.logger.error("Webhook service died unexpectedly")
                        self.shutdown()
                        sys.exit(1)
                    
                    if not self.web_process.is_alive():
                        self.logger.error("Web interface died unexpectedly")
                        self.shutdown()
                        sys.exit(1)
                    
                    # Sleep briefly to avoid busy waiting
                    asyncio.run(asyncio.sleep(1))
                    
            elif run_mode == "webhook":
                # Run only webhook service
                self.logger.info("Running webhook service only")
                self.start_webhook_service()
                
            elif run_mode == "web":
                # Run only web interface
                self.logger.info("Running web interface only")
                self.start_web_service()
                
            else:
                self.logger.error(f"Unknown run mode: {run_mode}")
                self.logger.info("Valid modes: all, both, webhook, web")
                sys.exit(1)
                
        except KeyboardInterrupt:
            self.logger.info("Keyboard interrupt received")
            self.shutdown()
        except Exception as e:
            self.logger.error(f"Launcher error: {e}")
            self.shutdown()
            sys.exit(1)


def main():
    """Main entry point"""
    launcher = ServiceLauncher()
    launcher.run()


if __name__ == "__main__":
    main()