# Terminal Management and IPC - Complete Issues Audit

**Analysis Date**: 2025-11-13  
**Total Issues Found**: 22 (5 CRITICAL, 7 HIGH, 7 MEDIUM, 3 LOW)

## CRITICAL ISSUES (5)

### 1.0: PersistentTerminalManager Race in send_command() - lines 802-925
- Health check WITHOUT lock (838), FIFO write WITH lock (869)
- Dispatcher can crash between checks, causing ENXIO failures
- Race window: 100-500ms on slow systems

### 1.1: ProcessExecutor Signal Leak - lines 82-89 (process_executor.py), 151-172 (command_launcher.py)
- ProcessExecutor connects to PersistentTerminalManager signals
- CommandLauncher.cleanup() never calls ProcessExecutor.cleanup()
- Signal connections persist after destruction → memory leak

### 1.2: SimplifiedLauncher Subprocess Leak - lines 366-416
- Exception handler assumes process not in tracking
- But signal emission after tracking can throw
- Results in killing already-tracked processes

### 1.3: PersistentTerminalManager Worker Thread Leak - lines 927-1005
- cleanup_worker() closure has race conditions
- Multiple scenarios: list cleared while removing, deleteLater() never executes, timeout

### 1.4: PersistentTerminalManager Fallback Mode Permanent - lines 1024-1112
- Once fallback_mode = True (1056), ALL commands blocked (816-820)
- reset_fallback_mode() exists but NOBODY calls it
- Terminal permanently disabled after recovery failure

## HIGH-PRIORITY ISSUES (7)

2.0: ProcessExecutor subprocess never awaited (173-216)
2.1: SimplifiedLauncher no cleanup on terminal failure (99-186)
2.2: CommandLauncher doesn't call ProcessExecutor.cleanup() (151-172)
2.3: PersistentTerminalManager incomplete ENXIO handling (899-912)
2.4: LauncherManager fragile signal disconnection (638-665)
2.5: PersistentTerminalManager dummy writer FD race (240-315, 360-382)
2.6: PersistentTerminalManager workers not waited during cleanup (1291-1316)
2.7: SimplifiedLauncher cache not thread-safe (525-561)

## MEDIUM-PRIORITY ISSUES (7)

3.0: Dispatcher PID detection unreliable (422-469)
3.1: Heartbeat timeout too aggressive (505-537)
3.2: Worker cleanup order issues (1291-1323)
3.3: Environment variable isolation missing (233-247)
3.4: No timeout for blocking FIFO operations (615-672)
3.5: ProcessExecutor doesn't cleanup subprocess references (173-216)
3.6: LauncherManager properties return unsynchronized references (139-158)

## LOW-PRIORITY ISSUES (3)

4.0: Subprocess.Popen close() called incorrectly (400-401, 412-413)
4.1: Signal connection assumes signals exist (122-130)
4.2: ProcessPoolManager singleton not thread-safe (250-298)

## KEY FINDINGS

**Root Causes**:
1. Lock acquired too late (health check before acquiring lock)
2. Signal connections never cleaned up (cleanup methods incomplete)
3. Exception handlers make incorrect assumptions
4. Cleanup operations not synchronized with background workers
5. One-way initialization without proper reset

**Impact**:
- Race conditions under concurrent operation
- Resource leaks over application lifetime
- Cascading failures when components crash
- Permanent failure states with no recovery

## IMMEDIATE ACTIONS REQUIRED

Fix CRITICAL issues 1.0-1.4 before production deployment
