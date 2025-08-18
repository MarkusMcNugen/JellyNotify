#!/usr/bin/env python3
"""
Jellynouncer Utilities Module

This module provides shared utility functions including logging setup and common helpers
used throughout the Jellynouncer application. It consolidates cross-cutting concerns
like logging configuration to prevent code duplication and ensure consistency.

The primary purpose is to provide a centralized location for utility functions that
don't belong to any specific service component but are needed across the application.
This promotes code reuse and maintains consistent behavior for common operations.

Functions:
    setup_logging: Configure logging with rotation and custom formatting
    get_logger: Retrieve existing logger instances by name
    format_bytes: Convert byte counts to human-readable format
    sanitize_filename: Clean filenames for safe filesystem usage

Author: Mark Newton
Project: Jellynouncer
Version: 1.0.0
License: MIT
"""

import logging
import logging.handlers
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Try to import colorama for colored output
try:
    import colorama
    from colorama import Fore, Style
    COLORAMA_AVAILABLE = True
except ImportError:
    COLORAMA_AVAILABLE = False
    # Define dummy classes to prevent reference errors
    colorama = None
    
    class Fore:
        """Dummy Fore class when colorama is not available."""
        BLACK = ''
        RED = ''
        GREEN = ''
        YELLOW = ''
        BLUE = ''
        MAGENTA = ''
        CYAN = ''
        WHITE = ''
        RESET = ''
    
    class Style:
        """Dummy Style class when colorama is not available."""
        DIM = ''
        NORMAL = ''
        BRIGHT = ''
        RESET_ALL = ''


def interpolate_color(start_rgb, end_rgb, position):
    """
    Interpolate between two RGB colors based on position (0.0 to 1.0).
    
    Args:
        start_rgb: Tuple of (r, g, b) for start color
        end_rgb: Tuple of (r, g, b) for end color  
        position: Float between 0.0 and 1.0
        
    Returns:
        Tuple of interpolated (r, g, b) values
    """
    r = int(start_rgb[0] + (end_rgb[0] - start_rgb[0]) * position)
    g = int(start_rgb[1] + (end_rgb[1] - start_rgb[1]) * position)
    b = int(start_rgb[2] + (end_rgb[2] - start_rgb[2]) * position)
    return r, g, b


def rgb_to_ansi(r, g, b):
    """
    Convert RGB values to ANSI 256-color escape code.
    
    Args:
        r, g, b: RGB values (0-255)
        
    Returns:
        ANSI escape code string
    """
    return f"\033[38;2;{r};{g};{b}m"


# Jellyfin gradient colors
JELLYFIN_PURPLE_RGB = (170, 92, 195)  # #AA5CC3
JELLYFIN_BLUE_RGB = (0, 164, 220)     # #00A4DC

# Track gradient message groups and their positions
gradient_message_tracker = {
    'webhook_init': {
        'messages': [
            "=" * 60,
            "🚀 WebhookService initialization completed successfully!",
            "Service is ready to process Jellyfin webhooks",
            "=" * 60
        ],
        'current_index': 0
    },
    'app_startup': {
        'messages': [
            "Jellynouncer app started successfully",
            "=" * 60,
            "🎬 Jellynouncer is ready to receive webhooks!",
            "Send webhooks to:",  # Partial match for dynamic content
            "Health check:",       # Partial match for dynamic content
            "Also available on:",  # Optional, partial match
            "=" * 60
        ],
        'current_index': 0,
        'debug_messages': [  # Debug messages that appear in this section
            "Primary IP detected via external route:",
            "Local hostname:",
            "Hostname",
            "Total interfaces discovered:",
            "User-friendly interfaces:"
        ]
    },
    'jellyfin_logo': {
        'messages': [
            "                                                                     ",
            "                                                                     ",
            "                                _@@@@p,                              ",
            "                              _@@@@@@@@g                             ",
            "                            _@@@@@@@@@@@@g                           ",
            "                          _@@@@@@@@@@@@@@@@L                         ",
            "                         g@@@@@@@@@@@@@@@@@@@,                       ",
            "                       _@@@@@@@@@B\"\"%@@@@@@@@@b                      ",
            "                      g@@@@@@@@P      '@@@@@@@@@_                    ",
            "                    _@@@@@@@@@          \\@@@@@@@@p                   ",
            "                   /@@@@@@@@/             @@@@@@@@@                  ",
            "                  @@@@@@@@D                \"@@@@@@@@_                ",
            "                ,@@@@@@@@/                   @@@@@@@@a               ",
            "               /@@@@@@@@          _gg_    ,_  T@@@@@@@@              ",
            "              j@@@@@@@P          /@ @@@L   '8g '@@@@@@@@             ",
            "             @@@@@@@@/          @@| @@@@g 0g  @L @@@@@@@@,           ",
            "            @@@@@@@@          o@@@| ==B@@h  @, @, %@@@@@@@L          ",
            "          ,@@@@@@@@       __@@@@@@@     @@, [@ @]  T@@@@@@@L         ",
            "         ,@@@@@@@W  __g@@@@@@@@@@@@,    @@@ (/ @'   \\@@@@@@@L        ",
            "        ,@@@@@@@D _@@@@@@@@@@@@@@@@@  ~@@@@   (F     \\@@@@@@@1       ",
            "       ,@@@@@@@D  @@@@@@@@@@@@@@@@@@@_'@@@@           \\@@@@@@@l      ",
            "      ,@@@@@@@W   \"@@@@@@@D>\"\"  '\"<4@@@_\"@P            \\@@@@@@@L     ",
            "      @@@@@@@@         _og@@           \"=\"              T@@@@@@@\\    ",
            "     @@@@@@@@           @@@@L                            @@@@@@@@,   ",
            "    @@@@@@@@g            Q@@@g                           '@@@@@@@@   ",
            "   /@@@@@@@@@_            0@@@@                         _g@@@@@@@@@  ",
            "   @@@@@@@@@@@@@g____      \"\"                    ____g@@@@@@@@@@@@@, ",
            "  |@@@@@@@@@@@@@@@@@@@@@@@@gggggggggggggggg@@@@@@@@@@@@@@@@@@@@@@@@@ ",
            "  '@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@P ",
            "   '0@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@B\"  ",
            "        \"<4B@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@B=\"       ",
            "                   \"\"\"\"===4BBBB@@@@@@@@@BBBBP==*\"\"\"\"                 ",
            "                                                                     "
        ],
        'current_index': 0
    }
}


def setup_logging(log_level: str = "INFO", log_dir: str = "/app/logs") -> logging.Logger:
    """
    Set up logging with rotation and custom formatting.

    This function configures Python's logging system for production use with both
    console and file output. It's designed to provide detailed logging information
    while managing disk space usage through automatic log rotation.

    **Understanding Python Logging for Beginners:**

    Python's logging system allows applications to record events, errors, and
    diagnostic information. Key concepts:

    - **Loggers**: Named loggers that generate log messages
    - **Handlers**: Direct log messages to destinations (console, files, etc.)
    - **Formatters**: Control the format of log messages
    - **Levels**: Control message severity (DEBUG < INFO < WARNING < ERROR < CRITICAL)

    **Log Rotation Explained:**
    Without rotation, log files grow indefinitely and can fill up disk space.
    Log rotation automatically manages this by:
    - Creating new log files when current ones reach size limits
    - Keeping a fixed number of backup files
    - Automatically deleting the oldest files when limits are exceeded

    **Custom Formatting:**
    This function uses a structured log format with brackets for easy parsing:
    `[timestamp] [user] [level] [component] message`

    This format is both human-readable and machine-parseable for log analysis tools.

    **Logging Configuration:**
    - Console Handler: Shows messages at specified level for immediate feedback
    - File Handler: Stores all messages with automatic rotation
    - Custom Formatter: Structured format with UTC timestamps
    - Rotation: 10MB per file, 5 backup files (50MB total maximum)

    Args:
        log_level (str): Python logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
            Both console and file handlers will use this level.
        log_dir (str): Directory path where log files will be stored.
            Created automatically if it doesn't exist.

    Returns:
        logging.Logger: Configured logger instance ready for use throughout the application

    Raises:
        ValueError: If log_level is not a valid Python logging level
        PermissionError: If log directory cannot be created or accessed

    Example:
        ```python
        # Basic setup for production
        logger = setup_logging("INFO", "/var/logs/jellynouncer")
        logger.info("Application starting up")
        logger.error("Database connection failed", exc_info=True)

        # Debug setup for development
        debug_logger = setup_logging("DEBUG", "./logs")
        debug_logger.debug("Detailed debugging information")
        debug_logger.warning("This is a warning message")

        # The logger will create structured output like:
        # [2025-01-15 10:30:45 UTC] [system] [INFO] [jellynouncer] Application starting up
        # [2025-01-15 10:30:46 UTC] [system] [ERROR] [jellynouncer] Database connection failed
        ```

    Note:
        This function should only be called once during application startup.
        Multiple calls will create duplicate log handlers, resulting in
        duplicate log messages. Use get_logger() to retrieve the configured
        logger in other parts of the application.

        The function uses RotatingFileHandler to automatically manage log file
        sizes and keep old logs as backup files. This prevents logs from
        consuming unlimited disk space over time.
    """
    # Validate log level first
    valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
    log_level_upper = log_level.upper()
    if log_level_upper not in valid_levels:
        raise ValueError(f"Invalid log level '{log_level}'. Must be one of: {valid_levels}")

    # Convert string to logging constant
    numeric_level = getattr(logging, log_level_upper)

    # Create logs directory if it doesn't exist with error handling
    log_path = Path(log_dir)
    try:
        log_path.mkdir(parents=True, exist_ok=True)
    except PermissionError as e:
        raise PermissionError(f"Cannot create log directory '{log_dir}': {e}")

    # Initialize colorama if available - colors on by default in Docker
    use_colors = False
    
    # Create a basic logger for debugging color initialization
    # We can't use the main logger yet since it hasn't been set up
    init_logger = logging.getLogger("jellynouncer.init")
    init_logger.setLevel(logging.DEBUG)
    if not init_logger.handlers:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s'))
        init_logger.addHandler(console_handler)
    
    init_logger.debug("=" * 60)
    init_logger.debug("Color initialization starting...")
    init_logger.debug(f"Colorama available: {COLORAMA_AVAILABLE}")
    
    # Initialize variables with defaults to avoid "referenced before assignment" warnings
    in_docker = False
    has_tty = False
    force_no_color = False
    
    if COLORAMA_AVAILABLE:
        # Check if colors are explicitly disabled via NO_COLOR environment variable
        force_no_color = os.environ.get('NO_COLOR', '').lower() in ('1', 'true', 'yes')
        init_logger.debug(f"NO_COLOR environment variable: {os.environ.get('NO_COLOR', 'not set')}")
        init_logger.debug(f"Force no color: {force_no_color}")
        
        # Check if we're in Docker (by checking for /.dockerenv file)
        in_docker = os.path.exists('/.dockerenv')
        init_logger.debug(f"Docker environment detected (/.dockerenv exists): {in_docker}")
        
        # Check if we have a TTY
        has_tty = hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()
        init_logger.debug(f"TTY detected: {has_tty}")
        init_logger.debug(f"stdout type: {type(sys.stdout)}")
        
        # Check TERM environment variable
        term_var = os.environ.get('TERM', 'not set')
        init_logger.debug(f"TERM environment variable: {term_var}")
        
        # Check FORCE_COLOR environment variable
        force_color_var = os.environ.get('FORCE_COLOR', 'not set')
        init_logger.debug(f"FORCE_COLOR environment variable: {force_color_var}")
        
        # Determine if we should use colors
        if force_no_color:
            # User explicitly disabled colors
            init_logger.debug("Colors DISABLED: NO_COLOR environment variable is set")
            use_colors = False
        elif in_docker:
            # Always force colors in Docker environments
            # Use strip=False to keep colors even without TTY
            # Use convert=False to prevent colorama from converting/stripping codes
            init_logger.debug("Colors ENABLED: Docker environment detected, forcing colors")
            init_logger.debug("Initializing colorama with: autoreset=True, strip=False, convert=False")
            colorama.init(autoreset=True, strip=False, convert=False)
            use_colors = True
        elif has_tty:
            # Normal TTY environment (not Docker)
            init_logger.debug("Colors ENABLED: TTY detected")
            init_logger.debug("Initializing colorama with: autoreset=True (standard mode)")
            colorama.init(autoreset=True)
            use_colors = True
        elif os.environ.get('FORCE_COLOR', '').lower() in ('1', 'true', 'yes'):
            # Allow forcing colors even in non-Docker, non-TTY environments if needed
            init_logger.debug("Colors ENABLED: FORCE_COLOR environment variable is set")
            init_logger.debug("Initializing colorama with: autoreset=True, strip=False, convert=False")
            colorama.init(autoreset=True, strip=False, convert=False)
            use_colors = True
        else:
            init_logger.debug("Colors DISABLED: No TTY, not in Docker, and FORCE_COLOR not set")
    else:
        init_logger.debug("Colors DISABLED: Colorama module not available")
    
    init_logger.debug(f"Final decision - use_colors: {use_colors}")
    init_logger.debug("=" * 60)
    
    class BracketFormatter(logging.Formatter):
        """
        Custom log formatter that uses brackets for structured, readable output.

        This nested class creates a custom formatter that generates consistent,
        structured log messages. The bracket format makes it easy to parse logs
        programmatically while remaining human-readable. When colorama is available
        and we're in a suitable environment, it adds color coding by log level.
        """
        
        def __init__(self, use_color_output=False):
            """Initialize formatter with color support option."""
            super().__init__()
            self.use_colors = use_color_output
            
            # Only set up colors if requested
            if self.use_colors and COLORAMA_AVAILABLE:
                # Color mappings for different log levels
                self.LEVEL_COLORS = {
                    'DEBUG': Fore.CYAN,
                    'INFO': Fore.GREEN,
                    'WARNING': Fore.YELLOW,
                    'ERROR': Fore.RED,
                    'CRITICAL': Fore.RED + Style.BRIGHT
                }
                # Component colors for better visual separation
                self.COMPONENT_COLOR = Fore.BLUE
                self.TIMESTAMP_COLOR = Fore.WHITE + Style.DIM
                self.USER_COLOR = Fore.MAGENTA
                self.RESET = Style.RESET_ALL
            else:
                # No colors for file output or when disabled
                self.LEVEL_COLORS = {
                    'DEBUG': '',
                    'INFO': '',
                    'WARNING': '',
                    'ERROR': '',
                    'CRITICAL': ''
                }
                self.COMPONENT_COLOR = ''
                self.TIMESTAMP_COLOR = ''
                self.USER_COLOR = ''
                self.RESET = ''

        def format(self, record: logging.LogRecord) -> str:
            """
            Format log record with structured bracket format and optional colors.

            This method is called automatically by the logging system for each
            log message. It extracts information from the LogRecord and formats
            it according to our structured format, with color coding when available.

            Args:
                record (LogRecord): Log record containing message and metadata

            Returns:
                str: Formatted log message ready for output, optionally with ANSI color codes

            Example:
                Input LogRecord with message "Database connected"
                Output: "[2025-01-15 10:30:45 UTC][system][INFO][jellynouncer.db] Database connected"
                (with green coloring for INFO level when colors are enabled)
            """
            # Get UTC timestamp for consistency across time zones and deployments
            timestamp = datetime.fromtimestamp(
                record.created,
                tz=timezone.utc
            ).strftime('%Y-%m-%d %H:%M:%S UTC')

            # User context available via getattr(record, 'user', 'system') if needed
            # This allows tracking which user or process generated the log message
            
            # Check if this is a gradient message
            is_gradient_message = False
            gradient_color = None
            message_text = record.getMessage()
            
            if self.use_colors and record.name in ['jellynouncer.webhook', 'jellynouncer', 'jellynouncer.logo']:
                # Check webhook initialization messages
                if record.name == 'jellynouncer.webhook':
                    for idx, msg in enumerate(gradient_message_tracker['webhook_init']['messages']):
                        if msg in message_text:
                            # Calculate gradient position for this message
                            total_msgs = len(gradient_message_tracker['webhook_init']['messages'])
                            position = idx / (total_msgs - 1) if total_msgs > 1 else 0
                            rgb = interpolate_color(JELLYFIN_PURPLE_RGB, JELLYFIN_BLUE_RGB, position)
                            gradient_color = rgb_to_ansi(*rgb)
                            is_gradient_message = True
                            break
                
                # Check app startup messages
                elif record.name == 'jellynouncer':
                    # First check for debug messages in the startup sequence
                    for debug_msg in gradient_message_tracker['app_startup'].get('debug_messages', []):
                        if debug_msg in message_text and record.levelname == 'DEBUG':
                            # Find position in the main message sequence
                            # Debug messages get colored based on their position in the sequence
                            # They appear after "🎬 Jellynouncer is ready" and before the final separator
                            position = 0.5  # Middle of gradient for debug messages
                            rgb = interpolate_color(JELLYFIN_PURPLE_RGB, JELLYFIN_BLUE_RGB, position)
                            gradient_color = rgb_to_ansi(*rgb)
                            is_gradient_message = True
                            break
                    
                    # Check for main startup messages
                    if not is_gradient_message:
                        for idx, msg in enumerate(gradient_message_tracker['app_startup']['messages']):
                            if msg in message_text or (msg == "=" * 60 and message_text == "=" * 60):
                                # Calculate gradient position for this message
                                total_msgs = len(gradient_message_tracker['app_startup']['messages'])
                                position = idx / (total_msgs - 1) if total_msgs > 1 else 0
                                rgb = interpolate_color(JELLYFIN_PURPLE_RGB, JELLYFIN_BLUE_RGB, position)
                                gradient_color = rgb_to_ansi(*rgb)
                                is_gradient_message = True
                                break
                
                # Check for Jellyfin logo ASCII art
                elif record.name == 'jellynouncer.logo':
                    for idx, msg in enumerate(gradient_message_tracker['jellyfin_logo']['messages']):
                        if message_text == msg:
                            # Calculate gradient position for this line
                            total_msgs = len(gradient_message_tracker['jellyfin_logo']['messages'])
                            position = idx / (total_msgs - 1) if total_msgs > 1 else 0
                            rgb = interpolate_color(JELLYFIN_PURPLE_RGB, JELLYFIN_BLUE_RGB, position)
                            gradient_color = rgb_to_ansi(*rgb)
                            is_gradient_message = True
                            break
            
            # Get the appropriate color for this log level (if not gradient)
            if not is_gradient_message:
                level_color = self.LEVEL_COLORS.get(record.levelname, '')
            else:
                level_color = gradient_color  # Use gradient color for the message

            # Format the complete log message with structured brackets
            if self.use_colors:
                if is_gradient_message:
                    # Special gradient formatting
                    formatted = (
                        f"{self.TIMESTAMP_COLOR}[{timestamp}]{self.RESET}"
                        #f"{self.USER_COLOR}[{user}]{self.RESET}"
                        f"{gradient_color}[{record.levelname}]{self.RESET}"
                        f"{self.COMPONENT_COLOR}[{record.name}]{self.RESET} "
                        f"{gradient_color}{message_text}{self.RESET}"
                    )
                else:
                    # Regular colored format for Docker/TTY environments
                    formatted = (
                        f"{self.TIMESTAMP_COLOR}[{timestamp}]{self.RESET}"
                        #f"{self.USER_COLOR}[{user}]{self.RESET}"
                        f"{level_color}[{record.levelname}]{self.RESET}"
                        f"{self.COMPONENT_COLOR}[{record.name}]{self.RESET} "
                        f"{level_color}{message_text}{self.RESET}"
                    )
            else:
                # Format the log line with the info we'd prefer to display
                # formatted = f"[{timestamp}][{user}][{record.levelname}][{record.name}] {message_text}"
                # Format the log line to exclude the user bracket.
                formatted = f"[{timestamp}][{record.levelname}][{record.name}] {message_text}"
            
            return formatted

    # Create the main application logger with the specified name
    logger = logging.getLogger("jellynouncer")
    logger.setLevel(numeric_level)

    # Clear any existing handlers to prevent duplicate logs during testing/development
    # This is important if setup_logging() is called multiple times
    logger.handlers.clear()

    # Console handler for immediate feedback during development and debugging
    # Shows messages on the terminal/console for real-time monitoring
    console_handler = logging.StreamHandler()
    console_handler.setLevel(numeric_level)  # Use specified log level instead of hardcoded INFO
    # Use colored formatter for console output
    console_handler.setFormatter(BracketFormatter(use_color_output=use_colors))
    logger.addHandler(console_handler)

    # Rotating file handler to prevent logs from consuming unlimited disk space
    # This is crucial for production deployments that run continuously
    log_file_path = log_path / "jellynouncer.log"
    try:
        file_handler = logging.handlers.RotatingFileHandler(
            filename=log_file_path,
            maxBytes=10 * 1024 * 1024,  # 10MB per file (reasonable size for analysis)
            backupCount=5,  # Keep 5 backup files (jellynouncer.log.1, .2, etc.)
            encoding='utf-8',  # Ensure proper encoding for international characters
            mode='a'  # Append mode - preserves logs across service restarts
        )
        file_handler.setLevel(numeric_level)  # Use specified log level for files
        # Use plain formatter for file output (no color codes)
        file_handler.setFormatter(BracketFormatter(use_color_output=False))
        logger.addHandler(file_handler)
    except PermissionError as e:
        # If we can't create file handler, log to console only
        logger.error(f"Cannot create log file '{log_file_path}': {e}")
        logger.warning("Continuing with console logging only")

    # Disable uvicorn's access logger to avoid duplication with our custom logging
    # Uvicorn is the ASGI server that runs FastAPI applications
    logging.getLogger("uvicorn.access").disabled = True

    # Log the configuration for verification and debugging
    # This helps administrators verify logging is set up correctly
    logger.info("=" * 60)
    logger.info("Jellynouncer Logging Configuration")
    logger.info("=" * 60)
    logger.info(f"Log Level: {log_level_upper}")
    logger.info(f"Log Directory: {log_dir}")
    logger.info(f"Main Log File: {log_file_path}")
    logger.info(f"Max Log Size: 10MB per file")
    logger.info(f"Backup Count: 5 files")
    logger.info(f"Total Storage: 50MB maximum")
    logger.info(f"Total Handlers: {len(logger.handlers)}")
    
    # Determine color status message
    if use_colors:
        if in_docker:
            color_status = 'Enabled (Docker environment detected)'
        elif has_tty:
            color_status = 'Enabled (TTY detected)'
        elif os.environ.get('FORCE_COLOR', '').lower() in ('1', 'true', 'yes'):
            color_status = 'Enabled (FORCE_COLOR set)'
        else:
            color_status = 'Enabled'
    else:
        if force_no_color:
            color_status = 'Disabled (NO_COLOR set)'
        elif not COLORAMA_AVAILABLE:
            color_status = 'Disabled (colorama not available)'
        else:
            color_status = 'Disabled (no TTY/Docker detected)'
    
    logger.info(f"Color Support: {color_status}")

    # List each handler for diagnostic purposes
    for handler_idx, handler in enumerate(logger.handlers):
        logger.info(f"Handler {handler_idx + 1}: {type(handler).__name__} - Level: {logging.getLevelName(handler.level)}")

    # Test logging at different levels to verify configuration
    if use_colors:
        logger.info("Color-coded logging enabled - messages will be colored by level:")
        logger.debug("DEBUG messages in cyan - detailed diagnostic information")
        logger.info("INFO messages in green - general informational messages")
        logger.warning("WARNING messages in yellow - warning conditions")
        logger.error("ERROR messages in red - error conditions")
    else:
        logger.debug("DEBUG level logging is working - visible when log level is DEBUG")
        logger.info("INFO level logging is working")

    logger.info("=" * 60)

    return logger


def display_jellyfin_logo() -> None:
    """
    Display the Jellyfin ASCII art logo with gradient coloring.
    
    This function outputs the Jellyfin logo line by line with gradient
    coloring from purple to blue. It's meant to be called after the
    "Jellynouncer app started successfully" message.
    """
    logo_logger = logging.getLogger("jellynouncer.logo")
    
    # Output each line of the logo
    for line in gradient_message_tracker['jellyfin_logo']['messages']:
        logo_logger.info(line)


def get_logger(name: str = "jellynouncer") -> logging.Logger:
    """
    Get an existing logger instance by name.

    This function retrieves a logger that should have been previously configured
    by setup_logging(). It's used throughout the application to get consistent
    logging without reconfiguring the logging system.

    **Why Use This Function:**
    - Avoids reconfiguring logging multiple times
    - Ensures consistent logger names across the application
    - Provides a central point to modify logger retrieval if needed
    - Makes it easy to create component-specific loggers

    **Logger Naming Convention:**
    Logger names use a hierarchical structure with dots:
    - "jellynouncer" - Main application logger
    - "jellynouncer.database" - Database operations
    - "jellynouncer.discord" - Discord notifications
    - "jellynouncer.jellyfin" - Jellyfin API operations

    This hierarchy allows fine-grained control over logging levels for different
    components if needed in the future.

    Args:
        name (str): Logger name to retrieve. Defaults to main application logger.

    Returns:
        logging.Logger: Logger instance (may be newly created if name doesn't exist)

    Example:
        ```python
        # Get main application logger
        logger = get_logger()
        logger.info("Main application event")

        # Get component-specific logger
        db_logger = get_logger("jellynouncer.database")
        db_logger.debug("Database query executed")

        # Get Discord service logger
        discord_logger = get_logger("jellynouncer.discord")
        discord_logger.info("Notification sent to Discord")
        ```

    Note:
        If the requested logger name doesn't exist, Python's logging system
        will create it automatically. However, it will inherit configuration
        from its parent logger in the hierarchy, so the main logger should
        be configured first with setup_logging().
    """
    return logging.getLogger(name)


def format_bytes(bytes_value: int) -> str:
    """
    Format byte count into human-readable string with appropriate units.

    This utility function converts raw byte counts into user-friendly representations
    using standard binary units (1024-based). This is essential for displaying file
    sizes, memory usage, and network transfer amounts in a way users can understand.

    **Binary vs Decimal Units:**
    This function uses binary units (1024-based) which are standard for:
    - File systems and storage devices
    - Memory measurements (RAM, cache sizes)
    - Most operating system utilities

    Binary: 1 KB = 1024 bytes, 1 MB = 1024 KB, etc.
    (vs Decimal: 1 kB = 1000 bytes - used by some manufacturers)

    **Unit Progression:**
    B → KB → MB → GB → TB → PB
    Each unit is 1024 times larger than the previous one.

    Args:
        bytes_value (int): Number of bytes to format. Can be 0 or positive integer.

    Returns:
        str: Human-readable string with appropriate unit (e.g., "1.5 MB", "250 KB")

    Example:
        ```python
        print(format_bytes(1024))        # "1.0 KB"
        print(format_bytes(1536))        # "1.5 KB"
        print(format_bytes(1048576))     # "1.0 MB"
        print(format_bytes(1073741824))  # "1.0 GB"
        print(format_bytes(500))         # "500 B"
        print(format_bytes(0))           # "0 B"
        ```

    Note:
        This function handles edge cases gracefully:
        - Zero bytes returns "0 B"
        - Negative values are treated as zero
        - Very large values are supported up to petabytes
        - Results are rounded to one decimal place for readability
    """
    if bytes_value <= 0:
        return "0 B"

    # Define units in order from smallest to largest
    units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']

    # Use bit operations for faster unit calculation
    # Each unit is 1024 (2^10) times larger than the previous
    # So we can use bit length to determine the appropriate unit
    if bytes_value == 0:
        return "0 B"
    
    # Calculate unit index using bit operations (faster than loops)
    # bit_length() - 1 gives us the highest set bit position
    # Dividing by 10 gives us the unit index (since 1024 = 2^10)
    unit_index = min((bytes_value.bit_length() - 1) // 10, len(units) - 1)
    
    # Calculate size using bit shifting for power of 2
    size = bytes_value / (1 << (unit_index * 10))
    
    # Format with one decimal place, but remove trailing zeros
    if size == int(size):
        return f"{int(size)} {units[unit_index]}"
    else:
        return f"{size:.1f} {units[unit_index]}"


def sanitize_filename(filename: str, replacement: str = "_") -> str:
    """
    Clean filename for safe filesystem usage by removing/replacing invalid characters.

    This utility function ensures filenames are safe for use across different
    operating systems and filesystems. It removes or replaces characters that
    could cause issues when creating files or directories.

    **Cross-Platform Compatibility:**
    Different operating systems have different rules for valid filenames:
    - Windows: Cannot contain < > : " | ? * or control characters
    - Linux/Unix: More permissive, but some characters still problematic
    - macOS: Similar to Linux but with additional restrictions

    This function creates filenames that work safely on all major platforms.

    **Character Handling:**
    - Invalid characters are replaced with the replacement string
    - Leading/trailing spaces and dots are removed (Windows requirement)
    - Reserved Windows names are handled (CON, PRN, AUX, etc.)
    - Unicode characters are preserved if they're filesystem-safe

    Args:
        filename (str): Original filename to sanitize
        replacement (str): Character to replace invalid characters with (default: "_")

    Returns:
        str: Sanitized filename safe for filesystem use

    Raises:
        ValueError: If filename is empty or becomes empty after sanitization

    Example:
        ```python
        # Remove problematic characters
        safe_name = sanitize_filename("My Movie: The Sequel (2024)")
        print(safe_name)  # "My Movie_ The Sequel (2024)"

        # Handle Windows reserved names
        safe_name = sanitize_filename("CON.txt")
        print(safe_name)  # "CON_.txt"

        # Custom replacement character
        safe_name = sanitize_filename("File<>Name", replacement="-")
        print(safe_name)  # "File--Name"
        ```

    Note:
        This function is conservative - it may replace some characters that
        are valid on your specific system, but the result will work everywhere.
        The goal is cross-platform compatibility rather than maximum permissiveness.
    """
    if not filename or not filename.strip():
        raise ValueError("Filename cannot be empty")

    # Define characters that are invalid on any major filesystem
    invalid_chars = '<>:"/\\|?*' + ''.join(chr(i) for i in range(32))
    
    # Create translation table for faster character replacement
    # This is more efficient than regex for simple character replacement
    translation_table = str.maketrans(invalid_chars, replacement * len(invalid_chars))
    
    # Replace invalid characters using translate (faster than regex)
    sanitized = filename.translate(translation_table)

    # Remove leading/trailing whitespace and dots (Windows requirement)
    sanitized = sanitized.strip(' .')

    # Handle Windows reserved names (case-insensitive)
    reserved_names = {
        'CON', 'PRN', 'AUX', 'NUL',
        'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
        'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
    }

    # Check if the base name (before extension) is reserved
    name_parts = sanitized.rsplit('.', 1)
    base_name = name_parts[0].upper()

    if base_name in reserved_names:
        # Append replacement character to make it safe
        if len(name_parts) == 2:
            sanitized = f"{name_parts[0]}{replacement}.{name_parts[1]}"
        else:
            sanitized = f"{sanitized}{replacement}"

    # Ensure we still have a valid filename after all transformations
    if not sanitized or not sanitized.strip():
        raise ValueError(f"Filename became empty after sanitization: '{filename}'")

    # Limit length to be safe for most filesystems (255 characters is common limit)
    if len(sanitized) > 255:
        name_parts = sanitized.rsplit('.', 1)
        if len(name_parts) == 2:
            # Preserve extension, truncate name
            max_name_length = 255 - len(name_parts[1]) - 1  # -1 for the dot
            sanitized = f"{name_parts[0][:max_name_length]}.{name_parts[1]}"
        else:
            # No extension, just truncate
            sanitized = sanitized[:255]

    return sanitized