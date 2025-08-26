"""Standardized exception hierarchy for ShotBot application.

This module provides a comprehensive error handling system with specific
exception types for different failure scenarios, enabling better error
tracking, debugging, and user feedback.

Following best practices for exception design:
- Clear hierarchy with base ShotBotError
- Specific exceptions for each subsystem
- Useful error messages and context
- Integration with logging system
"""

from typing import Any, Dict, Optional


class ShotBotError(Exception):
    """Base exception for all ShotBot errors.
    
    This is the root of the exception hierarchy. All custom exceptions
    in the ShotBot application should inherit from this class.
    
    Attributes:
        message: Human-readable error message
        details: Optional additional error details
        error_code: Optional error code for categorization
    """
    
    def __init__(
        self, 
        message: str, 
        details: Optional[Dict[str, Any]] = None,
        error_code: Optional[str] = None
    ):
        """Initialize ShotBot error.
        
        Args:
            message: Error message
            details: Optional dictionary with additional context
            error_code: Optional error code for categorization
        """
        super().__init__(message)
        self.message = message
        self.details = details or {}
        self.error_code = error_code or "SHOTBOT_ERROR"
    
    def __str__(self) -> str:
        """String representation of the error."""
        if self.details:
            details_str = ", ".join(f"{k}={v}" for k, v in self.details.items())
            return f"{self.message} ({details_str})"
        return self.message


class WorkspaceError(ShotBotError):
    """Exception for workspace-related errors.
    
    Raised when workspace commands fail, workspace paths are invalid,
    or workspace operations cannot be completed.
    """
    
    def __init__(
        self, 
        message: str, 
        workspace_path: Optional[str] = None,
        command: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Initialize workspace error.
        
        Args:
            message: Error message
            workspace_path: The workspace path involved
            command: The workspace command that failed
            details: Additional error context
        """
        error_details = details or {}
        if workspace_path:
            error_details["workspace_path"] = workspace_path
        if command:
            error_details["command"] = command
        
        super().__init__(
            message=message,
            details=error_details,
            error_code="WORKSPACE_ERROR"
        )


class ThumbnailError(ShotBotError):
    """Exception for thumbnail processing errors.
    
    Raised when thumbnail generation fails, cache operations fail,
    or image processing encounters errors.
    """
    
    def __init__(
        self, 
        message: str,
        image_path: Optional[str] = None,
        thumbnail_path: Optional[str] = None,
        reason: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Initialize thumbnail error.
        
        Args:
            message: Error message
            image_path: Source image path
            thumbnail_path: Destination thumbnail path
            reason: Specific reason for failure
            details: Additional error context
        """
        error_details = details or {}
        if image_path:
            error_details["image_path"] = image_path
        if thumbnail_path:
            error_details["thumbnail_path"] = thumbnail_path
        if reason:
            error_details["reason"] = reason
        
        super().__init__(
            message=message,
            details=error_details,
            error_code="THUMBNAIL_ERROR"
        )


class SecurityError(ShotBotError):
    """Exception for security-related errors.
    
    Raised when security violations are detected, such as:
    - Command injection attempts
    - Path traversal attempts
    - Unauthorized command execution
    - Invalid input sanitization
    """
    
    def __init__(
        self, 
        message: str,
        violation_type: Optional[str] = None,
        attempted_command: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Initialize security error.
        
        Args:
            message: Error message
            violation_type: Type of security violation
            attempted_command: The command that was blocked
            details: Additional security context
        """
        error_details = details or {}
        if violation_type:
            error_details["violation_type"] = violation_type
        if attempted_command:
            error_details["attempted_command"] = attempted_command
        
        super().__init__(
            message=message,
            details=error_details,
            error_code="SECURITY_ERROR"
        )


class LauncherError(ShotBotError):
    """Exception for application launcher errors.
    
    Raised when application launching fails, custom launchers
    have errors, or launcher configuration is invalid.
    """
    
    def __init__(
        self, 
        message: str,
        launcher_name: Optional[str] = None,
        launcher_command: Optional[str] = None,
        exit_code: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Initialize launcher error.
        
        Args:
            message: Error message
            launcher_name: Name of the launcher
            launcher_command: The command that failed
            exit_code: Process exit code if available
            details: Additional launcher context
        """
        error_details = details or {}
        if launcher_name:
            error_details["launcher_name"] = launcher_name
        if launcher_command:
            error_details["launcher_command"] = launcher_command
        if exit_code is not None:
            error_details["exit_code"] = exit_code
        
        super().__init__(
            message=message,
            details=error_details,
            error_code="LAUNCHER_ERROR"
        )


class CacheError(ShotBotError):
    """Exception for cache-related errors.
    
    Raised when cache operations fail, cache corruption is detected,
    or cache validation fails.
    """
    
    def __init__(
        self, 
        message: str,
        cache_key: Optional[str] = None,
        cache_file: Optional[str] = None,
        operation: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Initialize cache error.
        
        Args:
            message: Error message
            cache_key: The cache key involved
            cache_file: The cache file path
            operation: The operation that failed (read/write/validate)
            details: Additional cache context
        """
        error_details = details or {}
        if cache_key:
            error_details["cache_key"] = cache_key
        if cache_file:
            error_details["cache_file"] = cache_file
        if operation:
            error_details["operation"] = operation
        
        super().__init__(
            message=message,
            details=error_details,
            error_code="CACHE_ERROR"
        )


class NetworkError(ShotBotError):
    """Exception for network-related errors.
    
    Raised when network operations fail, remote resources
    are unavailable, or network timeouts occur.
    """
    
    def __init__(
        self, 
        message: str,
        url: Optional[str] = None,
        status_code: Optional[int] = None,
        timeout: Optional[float] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Initialize network error.
        
        Args:
            message: Error message
            url: The URL that failed
            status_code: HTTP status code if applicable
            timeout: Timeout value if timeout occurred
            details: Additional network context
        """
        error_details = details or {}
        if url:
            error_details["url"] = url
        if status_code:
            error_details["status_code"] = status_code
        if timeout:
            error_details["timeout"] = timeout
        
        super().__init__(
            message=message,
            details=error_details,
            error_code="NETWORK_ERROR"
        )


class ConfigurationError(ShotBotError):
    """Exception for configuration errors.
    
    Raised when configuration is invalid, missing required
    settings, or configuration files are corrupted.
    """
    
    def __init__(
        self, 
        message: str,
        config_key: Optional[str] = None,
        config_file: Optional[str] = None,
        expected_value: Optional[Any] = None,
        actual_value: Optional[Any] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Initialize configuration error.
        
        Args:
            message: Error message
            config_key: The configuration key with the issue
            config_file: The configuration file path
            expected_value: What was expected
            actual_value: What was found
            details: Additional configuration context
        """
        error_details = details or {}
        if config_key:
            error_details["config_key"] = config_key
        if config_file:
            error_details["config_file"] = config_file
        if expected_value is not None:
            error_details["expected"] = expected_value
        if actual_value is not None:
            error_details["actual"] = actual_value
        
        super().__init__(
            message=message,
            details=error_details,
            error_code="CONFIG_ERROR"
        )


class ValidationError(ShotBotError):
    """Exception for validation errors.
    
    Raised when input validation fails, data doesn't meet
    requirements, or business rules are violated.
    """
    
    def __init__(
        self, 
        message: str,
        field: Optional[str] = None,
        value: Optional[Any] = None,
        constraint: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Initialize validation error.
        
        Args:
            message: Error message
            field: The field that failed validation
            value: The invalid value
            constraint: The constraint that was violated
            details: Additional validation context
        """
        error_details = details or {}
        if field:
            error_details["field"] = field
        if value is not None:
            error_details["value"] = value
        if constraint:
            error_details["constraint"] = constraint
        
        super().__init__(
            message=message,
            details=error_details,
            error_code="VALIDATION_ERROR"
        )


# Convenience functions for common error scenarios

def raise_if_invalid_path(path: str, purpose: str = "access") -> None:
    """Raise SecurityError if path contains dangerous characters.
    
    Args:
        path: Path to validate
        purpose: What the path is used for
        
    Raises:
        SecurityError: If path contains dangerous characters
    """
    dangerous_chars = [';', '&&', '||', '|', '>', '<', '`', '$', '\\', '..']
    for char in dangerous_chars:
        if char in path:
            raise SecurityError(
                f"Invalid path for {purpose}: contains dangerous character '{char}'",
                violation_type="path_traversal",
                attempted_command=path
            )


def raise_if_command_not_allowed(command: str, allowed_commands: set) -> None:
    """Raise SecurityError if command is not in whitelist.
    
    Args:
        command: Command to validate
        allowed_commands: Set of allowed commands
        
    Raises:
        SecurityError: If command is not allowed
    """
    if command not in allowed_commands:
        raise SecurityError(
            f"Command '{command}' is not in the allowed command list",
            violation_type="unauthorized_command",
            attempted_command=command
        )