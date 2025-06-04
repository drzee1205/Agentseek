import logging
import json
from datetime import datetime
from typing import Optional, Dict, Any
import os

# Ensure the .logs directory exists
LOGS_DIR = ".logs"
if not os.path.exists(LOGS_DIR):
    os.makedirs(LOGS_DIR)

class StructuredLogger:
    def __init__(self, service_name: str, log_level: int = logging.INFO):
        self.service_name = service_name
        self.logger = logging.getLogger(service_name)
        self.logger.setLevel(log_level)

        # Configure file handler
        log_file_path = os.path.join(LOGS_DIR, "backend_structured.log")

        # Use 'a' mode for appending, and ensure the directory exists
        # The directory LOGS_DIR is already created above.
        file_handler = logging.FileHandler(log_file_path, mode='a')

        # No formatter is needed as we are logging JSON strings directly
        self.logger.addHandler(file_handler)
        # Prevent propagation to root logger to avoid duplicate logs if root is configured
        self.logger.propagate = False


    def _log(self, level: str, event: str, context: Optional[Dict[str, Any]] = None):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "service": self.service_name,
            "event": event,
            "level": level.upper(), # Ensure level is uppercase
            "context": context or {},
        }
        try:
            # Ensure the logger has handlers configured
            if not self.logger.handlers:
                # This case should ideally not be reached if constructor is always called
                # and handlers are not removed elsewhere.
                # Attempt to re-add handler as a fallback.
                log_file_path = os.path.join(LOGS_DIR, "backend_structured.log")
                file_handler = logging.FileHandler(log_file_path, mode='a')
                self.logger.addHandler(file_handler)
                # Log a warning about this recovery.
                recovery_event = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "service": self.service_name,
                    "event": "LoggerRecovery",
                    "level": "WARNING",
                    "context": {"detail": f"Logger for {self.service_name} had no handlers. File handler re-added."},
                }
                self.logger.log(logging.WARNING, json.dumps(recovery_event))


            actual_log_level = getattr(logging, level.upper(), logging.INFO) # Get actual level int
            self.logger.log(actual_log_level, json.dumps(log_entry))
        except Exception as e:
            # Fallback logging in case of issues with JSON serialization or logging itself
            # This fallback will print to stdout/stderr if the logger is completely broken
            fallback_log_entry_str = json.dumps({
                "timestamp": datetime.utcnow().isoformat(),
                "service": self.service_name,
                "event": "LoggingError",
                "level": "ERROR",
                "context": {"original_event": event, "error": str(e), "detail": "Fallback print to stdout"},
            })
            print(fallback_log_entry_str) # Print to stdout as a last resort
            # Also try to log to the file with a potentially broken logger
            if self.logger.handlers:
                 self.logger.log(logging.ERROR, fallback_log_entry_str)


    def info(self, event: str, context: Optional[Dict[str, Any]] = None):
        self._log("INFO", event, context)

    def error(self, event: str, context: Optional[Dict[str, Any]] = None):
        self._log("ERROR", event, context)

    def warning(self, event: str, context: Optional[Dict[str, Any]] = None):
        self._log("WARNING", event, context)

    def debug(self, event: str, context: Optional[Dict[str, Any]] = None):
        self._log("DEBUG", event, context)

# Example usage (optional, can be removed or kept for testing)
if __name__ == "__main__":
    # Example:
    logger = StructuredLogger("MyTestService", log_level=logging.DEBUG)
    logger.info("Service started", {"version": "1.0"})
    logger.debug("Debugging information", {"user_id": 123, "action": "test_action"})
    logger.warning("A potential issue detected.", {"code": 503})
    try:
        x = 1 / 0
    except ZeroDivisionError as e:
        logger.error("An error occurred", {"error_type": str(type(e).__name__), "message": str(e), "trace_id": "abcdef12345"})

    # Test logging with no context
    logger.info("Simple info event, no context.")

    # Test logging after removing handler (to test recovery)
    # print("Testing logger recovery...")
    # logger.logger.handlers.clear()
    # logger.info("Info after handler removal - should trigger recovery.")
    # print(f"Log file should be at: {os.path.join(LOGS_DIR, 'backend_structured.log')}")