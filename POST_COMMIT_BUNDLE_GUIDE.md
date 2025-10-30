# Post-Commit Bundle & Encoding System - Setup Guide

This guide explains how to set up an automated post-commit hook system that bundles your application files and creates base64-encoded releases after every commit.

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [System Components](#system-components)
4. [Quick Start](#quick-start)
5. [Detailed Configuration](#detailed-configuration)
6. [Testing & Verification](#testing--verification)
7. [Customization](#customization)
8. [Troubleshooting](#troubleshooting)
9. [Advanced Usage](#advanced-usage)

---

## Overview

### What This System Does

After each git commit, this system automatically:
1. **Collects** application files based on configurable patterns
2. **Bundles** them into a temporary directory structure
3. **Encodes** the bundle using base64 compression
4. **Commits** the encoded file to a separate `encoded-releases` branch
5. **Pushes** to remote (optional)

### Why Use This?

- **Easy distribution**: Share entire applications as single text files
- **Version tracking**: Encoded releases correspond to commits
- **Transfer-friendly**: Base64 encoding works everywhere
- **Automated**: No manual steps required
- **Configurable**: Fine-grained control over what gets included

---

## Prerequisites

### Required

- **Python 3.8+**
- **Git repository** (initialized)
- Unix-like environment (Linux/macOS/WSL)

### Required Python Files

You need these three files in your project root:

1. **`bundle_app.py`** - Main bundling script
2. **`transfer_cli.py`** - Base64 encoding tool
3. **`transfer_config.json`** - Configuration file

### Optional Tools

- `ruff` for linting (can be removed from hook)
- `basedpyright` for type checking (can be removed from hook)

---

## System Components

### 1. `bundle_app.py`

**Purpose**: Collects and bundles application files

**Key Features**:
- Respects `.gitignore` patterns
- Configurable include/exclude patterns
- Size filtering (skips large files)
- Metadata generation
- Calls `transfer_cli.py` for encoding

**Usage**:
```bash
# List files that would be bundled
python3 bundle_app.py --list-files -c transfer_config.json

# Create bundle with verbose output
python3 bundle_app.py -v -c transfer_config.json

# Test specific file inclusion
python3 -c "from bundle_app import ApplicationBundler; print(ApplicationBundler('transfer_config.json').should_include_file('your_file.py'))"
```

### 2. `transfer_config.json`

**Purpose**: Defines bundling rules

**Structure**:
```json
{
  "include_patterns": ["*.py", "*.json", "*.md"],
  "exclude_patterns": ["test_*.py", "*_test.py"],
  "exclude_dirs": ["tests", "venv", ".git"],
  "max_file_size_mb": 10,
  "chunk_size_kb": 5120,
  "output_dir": "encoded_releases",
  "remote_branch": "encoded-releases",
  "auto_push": true
}
```

### 3. `transfer_cli.py`

**Purpose**: Encodes bundles to base64

**Features**:
- Gzip compression
- Chunked encoding
- Metadata inclusion
- Single-file or multi-file output

### 4. Post-Commit Hook

**Purpose**: Automates the bundling process

**Location**: `.git/hooks/post-commit`

**What it does**:
- Runs after every commit
- Executes bundling and encoding
- Commits result to separate branch
- Optionally pushes to remote

---

## Quick Start

### Step 1: Copy Required Files

Copy these files to your project root:

```bash
# From the shotbot project
cp /path/to/shotbot/bundle_app.py ./
cp /path/to/shotbot/transfer_cli.py ./
cp /path/to/shotbot/transfer_config.json ./
```

### Step 2: Customize Configuration

Edit `transfer_config.json`:

```json
{
  "include_patterns": [
    "*.py",           // Your source files
    "*.json",         // Configuration files
    "*.md",           // Documentation
    "requirements.txt" // Dependencies
  ],
  "exclude_patterns": [
    "test_*.py",      // Test files
    "*_test.py",
    "*.log",          // Logs
    "bundle_app.py",  // Exclude bundling tools
    "transfer_cli.py"
  ],
  "exclude_dirs": [
    "tests",          // Test directory
    "__pycache__",    // Python cache
    ".git",           // Git directory
    "venv",           // Virtual environments
    "node_modules"    // Node modules (if applicable)
  ],
  "max_file_size_mb": 10,
  "output_dir": "encoded_releases",
  "remote_branch": "encoded-releases",
  "auto_push": false  // Set to true for automatic push
}
```

### Step 3: Create Post-Commit Hook

Create `.git/hooks/post-commit`:

```bash
#!/usr/bin/bash

# Post-commit hook for automated bundling and encoding

# Get project root
PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HOOK_OUTPUT_DIR="$PROJECT_ROOT/.post-commit-output"

# Clean and recreate output directory
rm -rf "$HOOK_OUTPUT_DIR"
mkdir -p "$HOOK_OUTPUT_DIR"

# Log commit info
echo "Post-commit hook executed at $(date)" > "$HOOK_OUTPUT_DIR/info.txt"
echo "Commit: $(git rev-parse HEAD)" >> "$HOOK_OUTPUT_DIR/info.txt"

# Create encoded releases branch if it doesn't exist
cd "$PROJECT_ROOT"
git rev-parse --verify encoded-releases >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "Creating encoded-releases branch..." >> "$HOOK_OUTPUT_DIR/info.txt"
    git checkout --orphan encoded-releases
    git rm -rf .
    git commit --allow-empty -m "Initialize encoded-releases branch"
    git checkout main  # or master, depending on your default branch
fi

# Run bundling and encoding
echo "Creating encoded bundle..." >> "$HOOK_OUTPUT_DIR/bundle.txt"
cd "$PROJECT_ROOT"

# Get current commit hash for filename
COMMIT_HASH=$(git rev-parse --short HEAD)
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_FILE="release_${COMMIT_HASH}_${TIMESTAMP}.txt"

# Run bundle_app.py
python3 bundle_app.py \
    -c transfer_config.json \
    -o "$OUTPUT_FILE" \
    -v \
    >> "$HOOK_OUTPUT_DIR/bundle.txt" 2>&1

BUNDLE_EXIT=$?

if [ $BUNDLE_EXIT -eq 0 ]; then
    echo "✓ Bundle created successfully: $OUTPUT_FILE" >> "$HOOK_OUTPUT_DIR/bundle.txt"

    # Commit to encoded-releases branch
    echo "Committing to encoded-releases branch..." >> "$HOOK_OUTPUT_DIR/bundle.txt"

    # Stash current work
    git stash push -m "temp stash for encoded release" >/dev/null 2>&1

    # Switch to encoded-releases branch
    git checkout encoded-releases >> "$HOOK_OUTPUT_DIR/bundle.txt" 2>&1

    # Copy encoded file
    cp "$PROJECT_ROOT/$OUTPUT_FILE" .

    # Add and commit
    git add "$OUTPUT_FILE"
    git commit -m "Auto-encoded release for commit $COMMIT_HASH" >> "$HOOK_OUTPUT_DIR/bundle.txt" 2>&1

    # Optionally push to remote
    AUTO_PUSH=$(python3 -c "import json; print(json.load(open('transfer_config.json')).get('auto_push', False))" 2>/dev/null || echo "false")
    if [ "$AUTO_PUSH" = "True" ] || [ "$AUTO_PUSH" = "true" ]; then
        echo "Pushing to remote..." >> "$HOOK_OUTPUT_DIR/bundle.txt"
        git push origin encoded-releases >> "$HOOK_OUTPUT_DIR/bundle.txt" 2>&1
    fi

    # Switch back to original branch
    ORIGINAL_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main")
    git checkout - >> "$HOOK_OUTPUT_DIR/bundle.txt" 2>&1

    # Restore stashed work
    git stash pop >/dev/null 2>&1

    # Clean up output file from working directory
    rm -f "$PROJECT_ROOT/$OUTPUT_FILE"

    echo "✓ Encoded release committed successfully" >> "$HOOK_OUTPUT_DIR/bundle.txt"
else
    echo "✗ Bundle creation failed (exit code: $BUNDLE_EXIT)" >> "$HOOK_OUTPUT_DIR/bundle.txt"
fi

# Summary
echo "" > "$HOOK_OUTPUT_DIR/summary.txt"
echo "Post-Commit Hook Summary" >> "$HOOK_OUTPUT_DIR/summary.txt"
echo "========================" >> "$HOOK_OUTPUT_DIR/summary.txt"
echo "Output directory: $HOOK_OUTPUT_DIR" >> "$HOOK_OUTPUT_DIR/summary.txt"
echo "Encoded file: $OUTPUT_FILE" >> "$HOOK_OUTPUT_DIR/summary.txt"
echo "Bundle exit code: $BUNDLE_EXIT" >> "$HOOK_OUTPUT_DIR/summary.txt"

exit 0
```

### Step 4: Make Hook Executable

```bash
chmod +x .git/hooks/post-commit
```

### Step 5: Test the System

```bash
# Test file collection
python3 bundle_app.py --list-files -c transfer_config.json

# Make a test commit
git add transfer_config.json
git commit -m "Test: Setup automated bundling"

# Check output
cat .post-commit-output/bundle.txt

# Verify encoded-releases branch
git checkout encoded-releases
git log --oneline
git checkout -
```

---

## Detailed Configuration

### Include Patterns

Patterns support wildcards and specific files:

```json
"include_patterns": [
  "*.py",              // All Python files
  "*.json",            // All JSON files
  "*.md",              // All Markdown files
  "requirements.txt",  // Specific file
  "wrapper/*",         // All files in wrapper/ (including no extension)
  "*.pyi",             // Type stub files
  "pytest.ini",        // Config files
  "Dockerfile"         // Specific files without extension
]
```

### Exclude Patterns

**Critical**: Patterns are anchored to prevent false matches

```json
"exclude_patterns": [
  "test_*.py",         // Files starting with "test_"
  "*_test.py",         // Files ending with "_test"
  "*.log",             // Log files
  "*.tmp",             // Temporary files
  "bundle_app.py",     // Bundling scripts themselves
  "transfer_cli.py",
  "encoded_app_*.txt", // Previous encoded outputs
  "analyze_*.py",      // Analysis scripts
  "*GUIDE*.md"         // Guide documents
]
```

**Important Pattern Matching Rules**:

- Patterns starting with `test_` are anchored: `^test_.*\.py$`
- This prevents matching `threede_latest_finder.py` (contains "test" but doesn't start with it)
- Use `*test*` to match anywhere, `test_*` to match at start

### Exclude Directories

Directories to skip entirely:

```json
"exclude_dirs": [
  "tests",            // Test directory
  "__pycache__",      // Python cache
  ".git",             // Git metadata
  ".pytest_cache",    // Pytest cache
  "venv",             // Virtual environment
  "node_modules",     // Node dependencies
  "dist",             // Build outputs
  "build",
  ".eggs",
  "htmlcov",          // Coverage reports
  ".vscode",          // Editor configs
  ".idea",
  "encoded_releases"  // Output directory
]
```

### Size Limits

```json
"max_file_size_mb": 10,    // Skip files larger than 10MB
"chunk_size_kb": 5120      // 5MB chunks for encoding
```

### Output Configuration

```json
"output_dir": "encoded_releases",      // Where to save encoded files
"remote_branch": "encoded-releases",   // Branch name for releases
"auto_push": true,                     // Auto-push to remote
"clean_old_releases": true,            // Remove old releases
"max_releases_to_keep": 10            // Keep last 10 releases
```

---

## Testing & Verification

### Verify File Inclusion

Before committing, verify what gets included:

```bash
# List all files that will be bundled
python3 bundle_app.py --list-files -c transfer_config.json

# Count files
python3 bundle_app.py --list-files -c transfer_config.json | wc -l

# Check specific file
python3 bundle_app.py --list-files -c transfer_config.json | grep "your_file.py"

# Get total size
python3 bundle_app.py --list-files -c transfer_config.json | \
    awk '{print $NF}' | \
    grep -oP '\d+' | \
    awk '{sum+=$1} END {print sum " KB"}'
```

### Test Specific File

```python
# Test if a file will be included
python3 -c "
from bundle_app import ApplicationBundler
bundler = ApplicationBundler('transfer_config.json')
print('Will include:', bundler.should_include_file('your_file.py'))
"
```

### Manual Bundle Creation

Test bundling without committing:

```bash
# Create bundle with verbose output
python3 bundle_app.py -v -c transfer_config.json -o test_bundle.txt

# Check output
ls -lh test_bundle.txt

# Keep bundle directory for inspection
python3 bundle_app.py -v -c transfer_config.json --bundle-dir ./test_bundle --keep-bundle

# Inspect bundle
ls -R ./test_bundle
```

### Verify Hook Execution

After a commit:

```bash
# Check hook output
cat .post-commit-output/bundle.txt
cat .post-commit-output/summary.txt

# Check if encoded-releases branch exists
git branch -a | grep encoded-releases

# View encoded releases
git checkout encoded-releases
ls -lh release_*.txt
git log --oneline
git checkout -
```

---

## Customization

### Example 1: Web Application Bundle

```json
{
  "include_patterns": [
    "*.py",
    "*.js",
    "*.html",
    "*.css",
    "*.json",
    "static/**/*",
    "templates/**/*",
    "requirements.txt",
    "package.json"
  ],
  "exclude_patterns": [
    "test_*.py",
    "*.test.js",
    "*.spec.js",
    "node_modules/*"
  ],
  "exclude_dirs": [
    "tests",
    "node_modules",
    ".git",
    "venv",
    "coverage"
  ]
}
```

### Example 2: Data Science Project

```json
{
  "include_patterns": [
    "*.py",
    "*.ipynb",
    "*.md",
    "*.yml",
    "requirements.txt",
    "notebooks/*.ipynb",
    "src/**/*.py",
    "data/*.csv"
  ],
  "exclude_patterns": [
    "test_*.py",
    "*checkpoint*",
    "*.pyc",
    "data/raw/*"
  ],
  "max_file_size_mb": 50
}
```

### Example 3: API Service

```json
{
  "include_patterns": [
    "*.py",
    "*.json",
    "*.yml",
    "*.md",
    "api/**/*.py",
    "models/**/*.py",
    "schemas/**/*.py",
    "requirements.txt",
    "Dockerfile",
    "docker-compose.yml"
  ],
  "exclude_patterns": [
    "test_*.py",
    "*_test.py",
    "*.log"
  ]
}
```

### Conditional Hook Execution

Add conditions to the hook:

```bash
# Only run on main branch
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$CURRENT_BRANCH" != "main" ]; then
    echo "Skipping bundle: not on main branch" >> "$HOOK_OUTPUT_DIR/info.txt"
    exit 0
fi

# Only run if Python files changed
CHANGED_FILES=$(git diff-tree --no-commit-id --name-only -r HEAD)
if ! echo "$CHANGED_FILES" | grep -q "\.py$"; then
    echo "Skipping bundle: no Python files changed" >> "$HOOK_OUTPUT_DIR/info.txt"
    exit 0
fi

# Skip if commit message contains [skip-bundle]
COMMIT_MSG=$(git log -1 --pretty=%B)
if echo "$COMMIT_MSG" | grep -q "\[skip-bundle\]"; then
    echo "Skipping bundle: [skip-bundle] in commit message" >> "$HOOK_OUTPUT_DIR/info.txt"
    exit 0
fi
```

---

## Troubleshooting

### Issue: Hook Doesn't Execute

**Check**:
```bash
# Verify hook exists and is executable
ls -la .git/hooks/post-commit

# Make executable
chmod +x .git/hooks/post-commit

# Test hook manually
./.git/hooks/post-commit
```

### Issue: Files Not Included

**Debug**:
```bash
# List what would be included
python3 bundle_app.py --list-files -c transfer_config.json

# Test specific file
python3 -c "
from bundle_app import ApplicationBundler
bundler = ApplicationBundler('transfer_config.json', verbose=True)
print(bundler.should_include_file('path/to/file.py'))
"

# Check if file is gitignored
git check-ignore -v path/to/file.py
```

### Issue: Pattern Matching Problems

**Common Mistakes**:

```json
// ❌ WRONG: Matches ANY file containing "test"
"exclude_patterns": ["test*.py"]

// ✅ CORRECT: Matches files STARTING with "test_"
"exclude_patterns": ["test_*.py"]

// ❌ WRONG: Will match "my_latest_file.py"
"exclude_patterns": ["*latest*.py"]

// ✅ CORRECT: More specific pattern
"exclude_patterns": ["threede_latest*.py"]
```

### Issue: Bundle Too Large

**Solutions**:

1. **Reduce max file size**:
   ```json
   "max_file_size_mb": 5
   ```

2. **Exclude large directories**:
   ```json
   "exclude_dirs": ["data", "models", "assets"]
   ```

3. **Exclude file types**:
   ```json
   "exclude_patterns": ["*.jpg", "*.png", "*.mp4", "*.weights"]
   ```

### Issue: Hook Takes Too Long

**Optimize**:

1. **Skip unnecessary checks** (remove linting/type checking)
2. **Add early exits** for unchanged files
3. **Use `.git/hooks/pre-push`** instead (runs only on push)
4. **Disable auto-push** (push manually when needed)

### Issue: Encoded File Not Committed

**Check**:
```bash
# View hook output
cat .post-commit-output/bundle.txt

# Check if branch exists
git branch -a | grep encoded-releases

# Check for errors
grep -i "error\|fail" .post-commit-output/*.txt
```

### Issue: Python Module Not Found

**Fix**:
```bash
# Use absolute path to Python
which python3

# Update hook to use correct Python
PYTHON_PATH=$(which python3)
$PYTHON_PATH bundle_app.py -c transfer_config.json
```

---

## Advanced Usage

### Separate Hooks for Different Purposes

You can create multiple configurations:

**`transfer_config_minimal.json`** - Minimal bundle:
```json
{
  "include_patterns": ["*.py"],
  "exclude_patterns": ["test_*.py"],
  "output_dir": "minimal_releases"
}
```

**`transfer_config_full.json`** - Full bundle:
```json
{
  "include_patterns": ["**/*"],
  "exclude_dirs": [".git", "venv"],
  "output_dir": "full_releases"
}
```

Use in hook:
```bash
# Create minimal bundle
python3 bundle_app.py -c transfer_config_minimal.json -o minimal_release.txt

# Create full bundle (monthly)
if [ $(date +%d) -eq 01 ]; then
    python3 bundle_app.py -c transfer_config_full.json -o full_release.txt
fi
```

### Integration with CI/CD

**GitHub Actions** example:

```yaml
name: Create Encoded Release

on:
  push:
    branches: [ main ]

jobs:
  bundle:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Create bundle
        run: |
          uv run python bundle_app.py -c transfer_config.json -o release.txt

      - name: Upload to encoded-releases branch
        run: |
          git config user.name github-actions
          git config user.email github-actions@github.com
          git checkout -b encoded-releases
          git add release.txt
          git commit -m "Encoded release for ${{ github.sha }}"
          git push origin encoded-releases --force
```

### Scheduled Releases

Create releases on a schedule instead of every commit:

**Cron job** (daily at midnight):
```bash
# Add to crontab
0 0 * * * cd /path/to/project && uv run python bundle_app.py -c transfer_config.json
```

**Modified hook** (weekly):
```bash
# Only run on Mondays
DAY_OF_WEEK=$(date +%u)
if [ "$DAY_OF_WEEK" != "1" ]; then
    exit 0
fi
# ... rest of hook
```

### Custom Metadata

Add custom metadata to bundles:

```python
# In bundle_app.py, modify the metadata section:
metadata = {
    "created": datetime.now().isoformat(),
    "files_count": len(files_to_bundle),
    "commit_hash": subprocess.check_output(
        ["git", "rev-parse", "HEAD"]
    ).decode().strip(),
    "branch": subprocess.check_output(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"]
    ).decode().strip(),
    "author": subprocess.check_output(
        ["git", "log", "-1", "--pretty=format:%an"]
    ).decode().strip(),
    "version": "1.0.0",  # Your app version
    "environment": "production",
}
```

---

## Complete Example Setup

Here's a complete, working setup script:

```bash
#!/bin/bash
# setup_bundling_system.sh

set -e

echo "Setting up automated bundling system..."

# Check if in git repo
if [ ! -d .git ]; then
    echo "Error: Not in a git repository"
    exit 1
fi

# Create transfer_config.json if it doesn't exist
if [ ! -f transfer_config.json ]; then
    echo "Creating transfer_config.json..."
    cat > transfer_config.json << 'EOF'
{
  "include_patterns": [
    "*.py",
    "*.json",
    "*.md",
    "requirements.txt"
  ],
  "exclude_patterns": [
    "test_*.py",
    "*_test.py",
    "*.log"
  ],
  "exclude_dirs": [
    "tests",
    "__pycache__",
    ".git",
    "venv"
  ],
  "max_file_size_mb": 10,
  "chunk_size_kb": 5120,
  "output_dir": "encoded_releases",
  "remote_branch": "encoded-releases",
  "auto_push": false
}
EOF
fi

# Ensure bundle_app.py and transfer_cli.py exist
if [ ! -f bundle_app.py ] || [ ! -f transfer_cli.py ]; then
    echo "Error: bundle_app.py or transfer_cli.py not found"
    echo "Please copy these files to the project root first"
    exit 1
fi

# Create post-commit hook
echo "Creating post-commit hook..."
cat > .git/hooks/post-commit << 'HOOKEOF'
#!/usr/bin/bash
# Auto-generated post-commit hook for bundling

PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HOOK_OUTPUT_DIR="$PROJECT_ROOT/.post-commit-output"

rm -rf "$HOOK_OUTPUT_DIR"
mkdir -p "$HOOK_OUTPUT_DIR"

echo "Creating encoded bundle..." > "$HOOK_OUTPUT_DIR/bundle.txt"
cd "$PROJECT_ROOT"

COMMIT_HASH=$(git rev-parse --short HEAD)
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_FILE="release_${COMMIT_HASH}_${TIMESTAMP}.txt"

uv run python bundle_app.py -c transfer_config.json -o "$OUTPUT_FILE" >> "$HOOK_OUTPUT_DIR/bundle.txt" 2>&1

if [ $? -eq 0 ]; then
    echo "✓ Bundle created: $OUTPUT_FILE" >> "$HOOK_OUTPUT_DIR/bundle.txt"
    # Add logic here to commit to encoded-releases branch if desired
else
    echo "✗ Bundle creation failed" >> "$HOOK_OUTPUT_DIR/bundle.txt"
fi

exit 0
HOOKEOF

chmod +x .git/hooks/post-commit

echo "✓ Bundling system setup complete!"
echo ""
echo "Test with:"
echo "  python3 bundle_app.py --list-files -c transfer_config.json"
echo ""
echo "Make a commit to trigger the hook:"
echo "  git add ."
echo "  git commit -m 'Test automated bundling'"
```

Save as `setup_bundling_system.sh` and run:
```bash
chmod +x setup_bundling_system.sh
./setup_bundling_system.sh
```

---

## Summary

This bundling system provides automated, configurable distribution of your application. Key points:

✅ **Automatic**: Runs on every commit
✅ **Configurable**: Fine-grained control via JSON
✅ **Testable**: Verify before committing
✅ **Version-tracked**: Releases correspond to commits
✅ **Transfer-friendly**: Base64 encoding works everywhere

**Best Practices**:
1. Test configuration before committing
2. Start with restrictive patterns, add as needed
3. Monitor bundle sizes
4. Review hook output regularly
5. Use `--list-files` to verify inclusion

**Resources**:
- Pattern matching: Use `^pattern` to anchor at start
- Debugging: Check `.post-commit-output/` directory
- Size optimization: Exclude unnecessary files/dirs
- CI/CD: Adapt hook logic for GitHub Actions/GitLab CI