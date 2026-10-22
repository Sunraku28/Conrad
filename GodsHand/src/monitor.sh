#!/bin/bash
# Make this script executable before running:
# chmod +x monitor.sh

# Resolve the absolute path to the project root's state.jsonl
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
STATE_FILE="$SCRIPT_DIR/../../state.jsonl"
REPO_ROOT="$SCRIPT_DIR/../../"

while true; do
    clear
    echo "========================================"
    echo "ACTIVE SANDBOXES (WORKTREES & BRANCHES)"
    echo "========================================"
    # List active agent worktrees
    ACTIVE_WT=$(git -C "$REPO_ROOT" worktree list | grep -E "godshand_worktrees|\[.+/.+\]")
    if [ -n "$ACTIVE_WT" ]; then
        echo "$ACTIVE_WT"
    else
        echo "No ephemeral worker worktrees currently attached."
    fi

    echo ""
    echo "========================================"
    echo "ACTIVE PODMAN CONTAINERS"
    echo "========================================"
    CONTAINERS=$(podman ps --format "table {{.Names}}	{{.Status}}	{{.Image}}" --filter "name=godshand" 2>/dev/null)
    if [ $(echo "$CONTAINERS" | wc -l) -gt 1 ]; then
        echo "$CONTAINERS"
    else
        echo "No active agent containers running."
    fi

    echo ""
    echo "========================================"
    echo "BLACKBOARD STATE (state.jsonl)"
    echo "========================================"
    
    if [ -f "$STATE_FILE" ] && [ -s "$STATE_FILE" ]; then
        (
            # Print headers
            echo -e "AGENT	TASK	STATUS"
            # Extract fields from the JSON payload (accounting for the nested 'result' structure)
            jq -r 'select(.result != null) | [.result.agent // "N/A", .task_name // "N/A", .status // "N/A"] | @tsv' "$STATE_FILE"
        ) | column -t -s $'	'
    else
        echo "State file ($STATE_FILE) is empty or not yet written."
    fi

    sleep 1
done
