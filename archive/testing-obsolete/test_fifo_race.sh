#!/bin/bash
# Test script to verify FIFO behavior with fresh opens

FIFO="/tmp/test_fifo_$$"

cleanup() {
    rm -f "$FIFO"
    exit
}

trap cleanup EXIT INT TERM

# Create FIFO
mkfifo "$FIFO"
echo "Created FIFO: $FIFO"
echo "PID: $$"

# Main loop - mimics terminal_dispatcher.sh
iteration=0
while true; do
    iteration=$((iteration + 1))
    echo "[Iteration $iteration] Waiting for command (blocking on read)..."
    
    # This mimics the new approach: fresh open on each iteration
    if read -r cmd < "$FIFO"; then
        if [ -z "$cmd" ]; then
            echo "[Iteration $iteration] Got empty string (should not happen)"
            continue
        fi
        
        echo "[Iteration $iteration] Received: '$cmd'"
        
        if [ "$cmd" = "EXIT" ]; then
            echo "Exiting cleanly"
            break
        fi
    else
        # read returned non-zero (failure/EOF)
        echo "[Iteration $iteration] READ FAILED (EOF or error) - EXITING LOOP"
        break
    fi
done

echo "Loop exited after $iteration iterations"
