# Launcher Architecture - Detailed Diagrams & Flows

---

## STATE MACHINE: PersistentTerminalManager

```
┌─────────────────────────────────────────────────────────────────┐
│                       INITIALIZATION                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  __init__():                                                     │
│    ├─ Create locks (_write_lock, _state_lock, _restart_lock)    │
│    ├─ _dummy_writer_ready = False                               │
│    ├─ _dummy_writer_fd = None                                   │
│    ├─ dispatcher_pid = None                                     │
│    ├─ _restart_attempts = 0                                     │
│    └─ _fallback_mode = False                                    │
│                                                                  │
│  Result: Ready to start terminal on first send_command()        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│                    IDLE (No Terminal)                            │
├─────────────────────────────────────────────────────────────────┤
│  State:                                                          │
│    - terminal_pid = None                                        │
│    - dispatcher_pid = None                                      │
│    - _dummy_writer_ready = False                                │
│    - FIFO: May or may not exist                                 │
│                                                                  │
│  Triggered by: send_command() with ensure_terminal=True         │
│                                                                  │
│  Action:                                                         │
│    1. Call _ensure_dispatcher_healthy()                         │
│    2. If unhealthy: _launch_terminal()                          │
│    3. Wait for dispatcher ready (with poll loop)                │
│    4. _open_dummy_writer()                                      │
│    5. Set _dummy_writer_ready = True                            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│              HEALTHY (Terminal Running)                          │
├─────────────────────────────────────────────────────────────────┤
│  State:                                                          │
│    - terminal_pid = <PID of dispatcher>                         │
│    - dispatcher_pid = <extracted from shell>                    │
│    - _dummy_writer_ready = True ✓                               │
│    - _dummy_writer_fd = <open FD to FIFO reader>               │
│    - FIFO exists and has reader (dispatcher)                    │
│    - _fallback_mode = False                                     │
│                                                                  │
│  Normal Operation:                                               │
│    ├─ send_command() → Write to FIFO (succeeds)                │
│    ├─ send_command_async() → Create worker (succeeds)          │
│    ├─ Worker runs health checks (pass)                          │
│    └─ Cycle repeats                                             │
│                                                                  │
│  Failure Detection:                                              │
│    - send_command() gets ENXIO (no reader) → UNHEALTHY          │
│    - send_command() gets ENOENT (FIFO missing) → UNHEALTHY      │
│    - Health check times out → UNHEALTHY                         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
         │                           ↑                    │
    Failure             Recovery succeeds            Failure x3
         │              (restart OK)                    │
         └──────────────────────────────────────────────┘
                            │
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│          RECOVERY_IN_PROGRESS (Restarting)                      │
├─────────────────────────────────────────────────────────────────┤
│  State:                                                          │
│    - Close existing terminal (SIGTERM)                          │
│    - Set _dummy_writer_ready = False (no new commands)          │
│    - Close dummy writer FD                                      │
│    - Delete stale FIFO                                          │
│    - Create new FIFO (atomic rename)                            │
│    - Launch new terminal process                                │
│    - Open new dummy writer                                      │
│    - Set _dummy_writer_ready = True                             │
│    - _restart_attempts++                                        │
│                                                                  │
│  Duration: ~2-5 seconds (includes SIGTERM + startup)            │
│                                                                  │
│  Success Path:                                                   │
│    - dispatcher_pid re-discovered                               │
│    - Return to HEALTHY state                                    │
│    - _restart_attempts = 0 (reset counter)                      │
│                                                                  │
│  Failure Path:                                                   │
│    - If _restart_attempts >= 3:                                 │
│      → Enter FALLBACK_MODE                                      │
│    - Else retry recovery                                        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
         │                                                │
         Success                                     Attempts ≥ 3
         │                                                │
         └─────────┬───────────────────────────────┬─────┘
                   │                               │
          Return to HEALTHY              Enter FALLBACK_MODE
                   ↑                               ↓
        ┌──────────────────────────────────────────────────────┐
        │    FALLBACK_MODE (Terminal Unavailable)              │
        ├──────────────────────────────────────────────────────┤
        │  State:                                              │
        │    - _fallback_mode = True                           │
        │    - _fallback_entered_at = current_time             │
        │    - All send_command() calls rejected immediately   │
        │    - Error: "Terminal in fallback mode"              │
        │                                                      │
        │  Duration: 300 seconds (5 minutes)                   │
        │                                                      │
        │  Auto-Recovery Attempt:                              │
        │    - Every send_command(), check: elapsed >= 300s    │
        │    - If true: Try _ensure_dispatcher_healthy()       │
        │    - If recovery succeeds: Return to HEALTHY         │
        │    - If recovery fails: Reset cooldown timer         │
        │                                                      │
        │  User Interaction:                                   │
        │    - Can't send commands (all rejected)              │
        │    - Error signals emitted but UI might not show     │
        │    - No UI button to retry immediately               │
        │                                                      │
        └──────────────────────────────────────────────────────┘
                         │
            Auto-recovery after 300s
                         │
                         ↓
            Try _ensure_dispatcher_healthy()
                    │         │
              Success ↓       ↓ Failure
                      │       └─→ Reset cooldown, stay in FALLBACK
                      │
                      └─→ Return to HEALTHY state
                          (_fallback_mode = False)
                          (_restart_attempts = 0)

```

---

## LOCK ACQUISITION PATTERN: send_command()

```
CRITICAL: Lock ordering must follow priority:
  1. _restart_lock (outermost - restart coordination)
  2. _write_lock (FIFO write serialization)  
  3. _state_lock (state snapshot protection)

Timeline of send_command():

┌────────────────────────────────────────────────────────────┐
│ Main Thread: send_command(command="nuke ...")              │
└────────────────────────────────────────────────────────────┘
                        │
                        ↓
┌────────────────────────────────────────────────────────────┐
│ PHASE 1: Check Fallback (snapshot under _state_lock)      │
├────────────────────────────────────────────────────────────┤
│  Lock: _state_lock (short hold)                            │
│  ─ Read: _fallback_mode                                    │
│  ─ Read: _fallback_entered_at                              │
│  Unlock                                                     │
│                                                             │
│  If fallback && cooldown expired:                          │
│    → Release lock, proceed to recovery attempt             │
│    → NOT under _state_lock                                 │
│                                                             │
│  If fallback && cooldown not expired:                      │
│    → Return False, "Fallback mode active"                  │
│                                                             │
└────────────────────────────────────────────────────────────┘
                        │
                        ↓
┌────────────────────────────────────────────────────────────┐
│ PHASE 2: Check Dummy Writer Ready (snapshot)               │
├────────────────────────────────────────────────────────────┤
│  Lock: _state_lock (short hold)                            │
│  ─ Read: _dummy_writer_ready                               │
│  Unlock                                                     │
│                                                             │
│  If NOT ready:                                              │
│    → Emit error signal                                     │
│    → Return False (terminate early)                        │
│                                                             │
└────────────────────────────────────────────────────────────┘
                        │
                        ↓
┌────────────────────────────────────────────────────────────┐
│ PHASE 3: Ensure Dispatcher Healthy                         │
├────────────────────────────────────────────────────────────┤
│  if ensure_terminal:                                        │
│    Call _ensure_dispatcher_healthy()                       │
│      ├─ May acquire _restart_lock internally               │
│      ├─ May restart terminal (LONG operation)              │
│      └─ Returns: Bool (healthy or recovery failed)         │
│                                                             │
│  CRITICAL: Still NO _write_lock acquired!                 │
│            Lock ordering will be: _restart_lock only       │
│            OR no lock (if health check passes)              │
│                                                             │
│  If health check fails:                                    │
│    → Emit error signal                                     │
│    → Return False (terminate early)                        │
│                                                             │
└────────────────────────────────────────────────────────────┘
                        │
                        ↓
┌────────────────────────────────────────────────────────────┐
│ PHASE 4: Re-check Health After Acquiring Write Lock        │
├────────────────────────────────────────────────────────────┤
│  Lock: _write_lock (SERIALIZE ALL FIFO WRITES)             │
│  ─ Fast health check: _is_dispatcher_healthy()             │
│    (no restart attempts, just check if alive)              │
│                                                             │
│  If not healthy:                                            │
│    → Emit error signal                                     │
│    → Unlock, return False                                  │
│                                                             │
│  REASON FOR RE-CHECK:                                       │
│    Race condition: Dispatcher could die between            │
│    PHASE 3 and PHASE 4 while waiting for lock              │
│                                                             │
└────────────────────────────────────────────────────────────┘
                        │
                        ↓
┌────────────────────────────────────────────────────────────┐
│ PHASE 5: Acquire Debug Snapshot (under _state_lock)        │
├────────────────────────────────────────────────────────────┤
│  Lock: _state_lock (very short, read-only)                 │
│  ─ Read: terminal_pid, dispatcher_pid                      │
│  Unlock                                                     │
│                                                             │
│  PURPOSE: Debug logging (not critical for execution)       │
│                                                             │
└────────────────────────────────────────────────────────────┘
                        │
                        ↓
┌────────────────────────────────────────────────────────────┐
│ PHASE 6: Write to FIFO (CRITICAL SECTION)                  │
├────────────────────────────────────────────────────────────┤
│  Still holding: _write_lock                                 │
│                                                             │
│  FOR attempt = 0,1,2:                                       │
│    TRY:                                                     │
│      fd = os.open(fifo_path, O_WRONLY | O_NONBLOCK)        │
│      write(command + newline)                              │
│      close(fd)                                              │
│                                                             │
│    ON ERROR:                                                │
│      ├─ ENOENT: FIFO missing, try recreate (sleep 0.1s)    │
│      ├─ ENXIO: No reader, retry (sleep 0.5s)               │
│      ├─ EAGAIN: Buffer full, retry (sleep 0.1-0.4s)        │
│      └─ Other: Emit error, return False                    │
│                                                             │
│  DANGER: Long sleep while holding _write_lock!             │
│          Other threads blocked from writing FIFO             │
│          Duration: Up to 1.1 seconds (0.1 + 0.2 + 0.4 + 0.4)
│                                                             │
│  SUCCESS:                                                    │
│    ├─ Emit command_sent signal                             │
│    └─ Return True                                          │
│                                                             │
└────────────────────────────────────────────────────────────┘
                        │
                        ↓
┌────────────────────────────────────────────────────────────┐
│ FINALLY: Unlock _write_lock (if acquired in PHASE 4)       │
├────────────────────────────────────────────────────────────┤
│  Release lock (even if exception)                          │
│  Other threads can now acquire _write_lock                 │
│                                                             │
└────────────────────────────────────────────────────────────┘
                        │
                        ↓
                   Return to Caller
                   (success or failure)

LOCK ORDERING VERIFICATION:
  ✓ PHASE 1: _state_lock only (released before PHASE 2)
  ✓ PHASE 2: _state_lock only (released before PHASE 3)
  ✓ PHASE 3: May acquire _restart_lock, NO _write_lock yet
  ✓ PHASE 4: _write_lock ONLY (after _restart_lock released)
  ✓ PHASE 5: _state_lock only (after _write_lock released)
  ✓ PHASE 6: _write_lock held (no other locks acquired)

CORRECT ORDER: _restart_lock → _write_lock (never reversed)
This prevents AB-BA deadlock with restart_terminal()
```

---

## FIFO LIFECYCLE: Normal Startup

```
Timeline: PersistentTerminalManager Initialization → First Command

T+0s:
  ┌────────────────────────────────────────────────────┐
  │ User Launches Application                          │
  └────────────────────────────────────────────────────┘
           │
           ↓
  ┌────────────────────────────────────────────────────┐
  │ MainWindow.__init__()                              │
  │  → Create PersistentTerminalManager                │
  │                                                     │
  │ State:                                              │
  │  - FIFO: DOES NOT EXIST (not created yet)          │
  │  - Terminal: NOT RUNNING                           │
  │  - Dispatcher: NOT RUNNING                         │
  │  - _dummy_writer_ready = False                     │
  └────────────────────────────────────────────────────┘

T+5s:
  (User waits for GUI to fully load)

T+10s:
  ┌────────────────────────────────────────────────────┐
  │ User Clicks "Launch Nuke" Button                   │
  │  → LauncherController.launch_app("nuke")           │
  │  → CommandLauncher.launch_app()                    │
  │  → ProcessExecutor.can_use_persistent_terminal()   │
  │                                                     │
  │ Checks:                                             │
  │  ✓ Persistent terminal available                   │
  │  ✓ Not in fallback mode                            │
  │  ✓ Dummy writer ready = FALSE ← ISSUE!             │
  │                                                     │
  │ Result: Try to send_command_async()                │
  └────────────────────────────────────────────────────┘
           │
           ↓
  ┌────────────────────────────────────────────────────┐
  │ PersistentTerminalManager.send_command_async()     │
  │  (First command ever sent)                         │
  │                                                     │
  │ Step 1: Check shutdown flag (OK)                   │
  │ Step 2: Check dummy_writer_ready = FALSE           │
  │                                                     │
  │ DECISION POINT:                                    │
  │  IF dummy_writer_ready check enforced:             │
  │    → Reject command: "Dummy writer not ready"      │
  │    → Return False                                  │
  │  ELSE:                                              │
  │    → Continue anyway                               │
  │                                                     │
  │ DESIGN QUESTION:                                   │
  │  Should first command be rejected if no terminal?  │
  │  Or should first command trigger terminal launch?  │
  └────────────────────────────────────────────────────┘
           │
           ↓ (assuming code continues)
  ┌────────────────────────────────────────────────────┐
  │ TerminalOperationWorker("send_command") created    │
  │  in worker thread                                  │
  │                                                     │
  │ worker.run() → _run_send_command()                 │
  │   Step 1: _ensure_dispatcher_healthy()             │
  │                                                     │
  │   Check: Is dispatcher running? NO (first time)    │
  │                                                     │
  │   Action: Enter restart sequence:                  │
  │     Acquire _restart_lock                          │
  │     Re-check health (still not running)            │
  │     Check restart attempts: 0 < 3 (OK)             │
  │     Increment: _restart_attempts = 1               │
  │     Call _perform_restart_internal()               │
  └────────────────────────────────────────────────────┘

T+11s:
  ┌────────────────────────────────────────────────────┐
  │ _perform_restart_internal()                        │
  │                                                     │
  │ Step 1: Acquire _restart_lock (already have it)    │
  │ Step 2: Set _dummy_writer_ready = False            │
  │ Step 3: close_terminal() (nothing to close)        │
  │ Step 4: _close_dummy_writer_fd() (nothing to close)│
  │ Step 5: Clean up stale temp FIFO (none exist)      │
  │                                                     │
  │ Step 6: Acquire _write_lock                        │
  │         ATOMIC FIFO REPLACEMENT:                   │
  │           - FIFO doesn't exist (first time)        │
  │           - Create temp path: .../fifo.PID.tmp     │
  │           - mkfifo(temp_fifo, 0o600)               │
  │           - os.rename(temp_fifo, fifo_path)        │
  │           - FIFO now exists at: /tmp/shotbot_...   │
  │         Release _write_lock                        │
  │                                                     │
  │ Step 7: Launch terminal process                    │
  │         Command: terminal_dispatcher.sh             │
  │         Background: True                            │
  │         Returns: process object                    │
  │                                                     │
  │ State:                                              │
  │  - FIFO: EXISTS (empty, no readers yet)            │
  │  - Terminal: RUNNING (PID assigned)                │
  │  - Dispatcher: STARTING (reads FIFO initially)    │
  │                                                     │
  │ Step 8: Wait for dispatcher ready (poll loop)      │
  │         Timeout: 30 seconds                        │
  │         Poll interval: 0.1 seconds                 │
  │         Condition: _is_dispatcher_running()        │
  │                                                     │
  │         [Polling for next 1-2 seconds...]          │
  │         Dispatcher ready!                          │
  │                                                     │
  │ Step 9: _open_dummy_writer()                       │
  │         Open FIFO for reading (r mode)             │
  │         FD kept open for duration of manager       │
  │         PURPOSE: Keep FIFO reader open             │
  │                 Prevents EOF if command writer     │
  │                 closes before dispatcher reads     │
  │                                                     │
  │ Step 10: Set _dummy_writer_ready = True            │
  │          Release _restart_lock                     │
  │                                                     │
  │ Return: True (restart successful)                  │
  └────────────────────────────────────────────────────┘

T+12s:
  ┌────────────────────────────────────────────────────┐
  │ TerminalOperationWorker continues:                 │
  │  _ensure_dispatcher_healthy() returned True        │
  │                                                     │
  │ Step 2: _send_command_direct(command)              │
  │         Acquire _write_lock                        │
  │         Open FIFO for writing (w mode)             │
  │         Write: "nuke -c script.py\n"               │
  │         Close FIFO                                 │
  │         Release _write_lock                        │
  │         Return: True                               │
  │                                                     │
  │ Step 3: ProcessVerifier.wait_for_process()         │
  │         Poll for: /tmp/shotbot_pids/nuke.pid       │
  │         Timeout: 30 seconds                        │
  │         Poll interval: 0.2 seconds                 │
  │                                                     │
  │         [Waiting for app to start and write PID]  │
  │         [This takes ~5-10 seconds for Nuke]        │
  │                                                     │
  │         PID file found! (e.g., "12847")            │
  │         Verify: psutil.Process(12847).exists()     │
  │         Result: True                               │
  │                                                     │
  │ Step 4: Emit "command_verified" signal             │
  │         Emit "operation_finished" signal           │
  │         Return                                     │
  │                                                     │
  │ Worker thread exits                                │
  │ QThread cleanup triggered                          │
  │ Signals delivered to main thread                   │
  └────────────────────────────────────────────────────┘

T+22s:
  ┌────────────────────────────────────────────────────┐
  │ Main Thread receives signals                       │
  │  "command_verified": Nuke verified (PID 12847)     │
  │  "operation_finished": Success                     │
  │                                                     │
  │ CommandLauncher._on_persistent_terminal_...()      │
  │  Emits: command_executed signal                    │
  │                                                     │
  │ MainWindow receives "command_executed"             │
  │  Updates UI: "Launched Nuke successfully"          │
  │                                                     │
  │ User sees Nuke window opening...                   │
  │                                                     │
  │ TERMINAL STATE:                                    │
  │  ✓ FIFO: EXISTS, has reader (dummy writer)         │
  │  ✓ Terminal: RUNNING (dispatcher shell)            │
  │  ✓ Dispatcher: RUNNING                             │
  │  ✓ _dummy_writer_ready = True                      │
  │  ✓ Ready for next command immediately              │
  └────────────────────────────────────────────────────┘

SUMMARY:
  Total startup time: ~12 seconds (from click to verified launch)
    - Terminal launch: ~1-2s
    - Dispatcher startup: ~0.5s
    - Dummy writer setup: <0.1s
    - Command send: ~0.1s
    - App startup & PID write: ~8-10s
    - Process verification: ~0.1s

EFFICIENCY: GOOD
  - Terminal starts only once (on first command)
  - Subsequent commands reuse same terminal
  - Dummy writer persists across all commands
  - No per-command terminal overhead
```

---

## CRITICAL RACE CONDITION: Dummy Writer Timing

```
This is BUG FIX #19 - The dummy writer timing race

PROBLEM SCENARIO:
  Dispatcher starts → FIFO exists but dispatcher hasn't opened reader yet
  Command sent immediately → Sent to FIFO with no reader attached
  Command writer closes → FD drops, EOF sent to FIFO
  Dummy writer can't open → FIFO has no readers (EOF already sent)

Race Window Diagram:

T0s: restart_terminal() launches dispatcher (shell process)
     │
     ├─ FIFO created ✓
     │
     ├─ Shell spawned (terminal_dispatcher.sh)
     │  Shell initialization begins...
     │
T0.1s: send_command() decides to send (main thread)
       ├─ Checks: _is_dispatcher_running() ← checking if PID is alive
       │  (shell is alive, so returns True)
       │
       ├─ ✓ Checks: _dummy_writer_ready
       │  (Should be False! Not ready yet)
       │  BUG: If not checked, proceeds anyway...
       │
       └─ Opens FIFO for writing
          Sends command ✓
          Closes FD ← EOF signal goes to FIFO!

T0.15s: Dispatcher shell FINALLY opens FIFO for reading
        ├─ open(fifo_path, O_RDONLY) ✓
        │
        └─ But already received EOF!
           FIFO is "closed on write side"

T0.2s: _open_dummy_writer() tries to open FIFO
       ├─ open(fifo_path, O_RDONLY) 
       │
       └─ Fails: ENXIO (no writers!)
           EOF already sent by command writer

RESULT: Dispatcher has no reader, next command hangs ENXIO


THE FIX (BUG FIX #19):

Add flag: _dummy_writer_ready (Protected by _state_lock)

Timeline with fix:

T0s: restart_terminal() called
     ├─ Set: _dummy_writer_ready = False (block all sends)
     │
     └─ Launch dispatcher

T0.1s: send_command() called
       ├─ Check: with _state_lock: _dummy_writer_ready
       │
       └─ Is False → Return error "Dummy writer not ready"
          ✓ Send prevented!

T0.15s: Dispatcher opens FIFO
        ├─ Shell continues...
        │
        └─ No EOF yet (no one sent to FIFO)

T0.2s: _open_dummy_writer() opens FIFO for reading ✓
       ├─ Can open successfully (dispatcher is reader)
       │
       └─ No EOF ever sent!

T0.3s: Set _dummy_writer_ready = True ✓

T0.4s: send_command() called
       ├─ Check: _dummy_writer_ready = True ✓
       │
       └─ Proceed with send
          FIFO has both:
            - Dispatcher reading
            - Dummy writer reading
          ✓ SAFE!

IMPROVEMENT OPPORTUNITIES:

1. Set _dummy_writer_ready flag MORE ATOMICALLY
   Currently: Set to False, lots of work, set to True
   Risk: Code path changes, flag not properly managed
   
2. Instead of flag, use explicit state machine:
   enum STATE { STARTING, WAITING, READY, CLOSED }
   Much clearer than boolean flag

3. Provide synchronization primitive for "ready":
   event = threading.Event()
   # In restart:
   event.clear()  # Not ready
   ... do work ...
   event.set()    # Now ready
   
   # In send_command:
   if not event.is_set():
       return error
   
   Better self-documenting than boolean
```

---

## DEADLOCK RISK: AB-BA Scenario (BUG FIX #23)

```
This is the AB-BA deadlock fixed in BUG FIX #23

DEADLOCK SCENARIO (OLD CODE):

Thread A: send_command()
  Step 1: Check dummy_writer_ready (no lock needed)
  Step 2: Acquire _write_lock  ←─────────────┐
  Step 3: Call _ensure_dispatcher_healthy()  │ ACQUIRES
          (INSIDE _write_lock)               │ LOCKS:
          {                                  │ A→B
            Acquire _restart_lock            │
            ...restart code...               │
            Release _restart_lock            │
          }                                  │
  Step 4: Write to FIFO (still have _write_lock)
  Step 5: Release _write_lock ──────────────┘

Thread B: restart_terminal()
  Step 1: Acquire _restart_lock  ←──────────┐
  Step 2: ...restart code...                │ ACQUIRES
  Step 3: Acquire _write_lock  ──┐         │ LOCKS:
          BLOCKS WAITING!         │         │ B→A
          (Thread A holding it)   │         │
  Step 4: (never reaches here)    │         │
  Step 5: Release _restart_lock ──┘─────────┘

TIMELINE OF DEADLOCK:

T0s: Thread A: send_command() starts
     │ Acquires: _write_lock ✓
     │
T0.05s: Thread A: Call _ensure_dispatcher_healthy()
        │ Inside _write_lock
        │ Tries: Acquire _restart_lock ✓ (available)
        │ Dispatcher unhealthy, needs restart
        │ Calls: _perform_restart_internal()
        │
T0.1s:  Thread B: restart_terminal() called (from UI or timeout)
        │ Tries: Acquire _restart_lock 
        │ BLOCKS! (Thread A has it)
        │
T0.2s:  Thread A: _perform_restart_internal() finishes
        │ Releases: _restart_lock
        │ Still holding: _write_lock
        │ Tries to write to FIFO
        │
        Thread B: Acquire _restart_lock ✓
        │ Tries: Acquire _write_lock
        │ BLOCKS! (Thread A has it)
        │
T0.3s:  Thread A: Finishes FIFO write
        │ Tries to release _write_lock, but...
        │ Thread B is blocked waiting for it!
        │ Both threads stuck in circular wait
        │
T5s:    TIMEOUT - Both threads stuck
        Application appears frozen
        Qt event loop unresponsive

VISUALIZATION:

         _write_lock
            ↓
    ┌──────────────┐
    │ Thread A     │
    │ send_cmd()   │
    ├──────────────┤
    │ Holds:       │
    │  _write_lock ├───────────────────┐
    │              │                   │
    │ Wants:       │                   ↓
    │ _restart_lock│          [LOCKED - Thread A waiting for release]
    │ BUT Thread B  │
    │ has it!      │
    └──────────────┘
         ↑    ↓
    Wait Circular
    For  Dependency
         ↓    ↑
    ┌──────────────┐
    │ Thread B     │
    │ restart_term │
    ├──────────────┤
    │ Holds:       │
    │ _restart_lock├────────────┐
    │              │            │
    │ Wants:       │            ↓
    │ _write_lock  │   [LOCKED - Thread B waiting for release]
    │ BUT Thread A  │
    │ has it!      │
    └──────────────┘

    ✗ PERMANENT DEADLOCK ✗


THE FIX (BUG FIX #23):

Change lock acquisition order in send_command():

BEFORE (DEADLOCK):
  1. Acquire _write_lock
  2. Call _ensure_dispatcher_healthy() (inside lock)
     - May acquire _restart_lock internally
  Order: A → B (problematic if B → A elsewhere)

AFTER (CORRECT):
  1. Call _ensure_dispatcher_healthy() FIRST (outside lock)
     - May acquire _restart_lock internally
     - Release _restart_lock when done
  2. THEN acquire _write_lock
  Order: B → A (consistent with restart_terminal())

Timeline with fix:

T0s: Thread A: send_command()
     │ Call _ensure_dispatcher_healthy()
     │   Acquire _restart_lock (fast check)
     │   No restart needed
     │   Release _restart_lock
     │
T0.05s: Thread A: Now acquire _write_lock ✓ (available)
        │
        Thread B: restart_terminal() trying to start
        │ Tries: Acquire _restart_lock ✓ (Thread A released it)
        │ Does restart work...
        │ Tries: Acquire _write_lock
        │ BLOCKED (Thread A has it, but briefly)
        │
T0.1s: Thread A: Finishes with FIFO
       │ Release _write_lock
       │
       Thread B: Acquire _write_lock ✓ (Thread A released it)
       │ Does atomic FIFO recreation
       │ Release _write_lock
       │
T0.2s: Both threads complete successfully
       ✓ NO DEADLOCK

KEY INSIGHT:
  Lock ordering MUST be consistent across all code paths
  
  send_command():  _restart_lock → _write_lock
  restart_terminal(): _restart_lock → _write_lock
  
  ✓ Both follow same order
  ✓ No AB-BA deadlock possible
  
  RULE: Always document lock hierarchy in code comments
```

---

## SUMMARY OF CRITICAL INTERACTIONS

```
Key Component Interactions (What can fail):

1. send_command() → FIFO write
   Risk: FIFO missing, no readers, buffer full, permission denied
   Recovery: Retry 3x, emit error, health check on next attempt

2. restart_terminal() → FIFO atomic recreation  
   Risk: Stale temp file, permission change, concurrent writes
   Recovery: Clean up stale files, atomic rename, fsync parent dir

3. TerminalOperationWorker → _ensure_dispatcher_healthy()
   Risk: Health check runs long (blocks worker)
   Recovery: Worker has timeout, can be interrupted

4. ProcessVerifier → PID file polling
   Risk: PID file not found, stale file, permission denied
   Recovery: 30s timeout, enqueue_time filtering

5. cleanup() → Worker abandonment
   Risk: Worker stuck in health check (holds lock)
   Recovery: 10s timeout, abandon (INCOMPLETE - no deadlock recovery)

6. Fallback mode → Auto-recovery
   Risk: Recovery fails, cooldown resets, infinite fallback
   Recovery: User must wait 5 minutes (no manual retry)
```

