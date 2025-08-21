#!/usr/bin/env python3
"""
Test script to verify web logging configuration.

This script tests that web components log to jellynouncer-web.log
instead of the main jellynouncer.log file.
"""

import sys
import os
import json

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jellynouncer.utils import setup_web_logging, get_web_logger

def test_web_logging():
    """Test the web logging configuration."""
    
    # Set up test environment
    log_dir = "logs"
    log_level = "DEBUG"
    
    print(f"Setting up web logging...")
    print(f"  Log directory: {log_dir}")
    print(f"  Log level: {log_level}")
    
    # Initialize web logging
    web_logger = setup_web_logging(log_level, log_dir)
    
    # Test different logger names
    loggers_to_test = [
        ("jellynouncer.web", "Main web logger"),
        ("jellynouncer.web_api", "Web API logger"),
        ("jellynouncer.web_client", "Client logger"),
        ("jellynouncer.web_db", "Web database logger"),
        ("jellynouncer.web_interface", "Web interface logger")
    ]
    
    print(f"\nTesting loggers:")
    for logger_name, description in loggers_to_test:
        logger = get_web_logger(logger_name)
        
        # Test all log levels
        logger.debug(f"[TEST] Debug message from {description}")
        logger.info(f"[TEST] Info message from {description}")
        logger.warning(f"[TEST] Warning message from {description}")
        logger.error(f"[TEST] Error message from {description}")
        
        print(f"  [OK] {description} ({logger_name})")
    
    # Test client log format
    print(f"\nTesting client log format:")
    client_logger = get_web_logger("jellynouncer.web_client")
    
    # Simulate client log entries
    test_client_logs = [
        {
            "level": "INFO",
            "sessionId": "test-123456789",
            "url": "http://localhost:3000/",
            "message": "Test client log entry",
            "metadata": {"component": "App", "action": "initialize"}
        },
        {
            "level": "ERROR",
            "sessionId": "test-123456789",
            "url": "http://localhost:3000/config",
            "message": "Test error from client",
            "metadata": {"error": "Network timeout", "retries": 3}
        }
    ]
    
    for log_entry in test_client_logs:
        formatted_message = f"[CLIENT] [{log_entry['sessionId'][:8]}] {log_entry['url']} - {log_entry['message']}"
        if log_entry.get('metadata'):
            formatted_message += f" | Metadata: {json.dumps(log_entry['metadata'])}"
        
        level = log_entry['level'].upper()
        if level == "INFO":
            client_logger.info(formatted_message)
        elif level == "ERROR":
            client_logger.error(formatted_message)
        
        print(f"  [OK] Client log: {log_entry['level']} - {log_entry['message'][:30]}...")
    
    # Check if log file was created
    web_log_file = os.path.join(log_dir, "jellynouncer-web.log")
    if os.path.exists(web_log_file):
        file_size = os.path.getsize(web_log_file)
        print(f"\n[SUCCESS] Success! Web log file created:")
        print(f"  Path: {web_log_file}")
        print(f"  Size: {file_size} bytes")
        
        # Show last few lines
        print(f"\nLast 5 lines from log file:")
        with open(web_log_file, 'r') as f:
            lines = f.readlines()
            for line in lines[-5:]:
                print(f"  {line.rstrip()}")
    else:
        print(f"\n[ERROR] Error: Web log file not created at {web_log_file}")
        return False
    
    return True

if __name__ == "__main__":
    print("=" * 60)
    print("Web Logging Test")
    print("=" * 60)
    
    success = test_web_logging()
    
    print("\n" + "=" * 60)
    if success:
        print("[SUCCESS] All tests passed!")
    else:
        print("[ERROR] Some tests failed!")
    print("=" * 60)