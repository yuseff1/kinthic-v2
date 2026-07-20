# Git & GitHub Integration Skill

## Description
This skill provides a structured, safe, and professional git workflow for managing branches, tracking status, making conventional commits, pushing code, and creating pull requests.

## Workflow

### 1. Pre-Flight Status Check
Before changing any code or creating branches:
*   Run `git status` and `git diff` to verify the starting state and identify uncommitted work.
*   Check the active branch name.

### 2. Branch Management
*   Always create a new branch for a new task. Do not commit directly to `main` or `master`.
*   Branch naming convention:
    *   `feat/short-feature-description` (for new features)
    *   `fix/short-bug-description` (for bug fixes)
    *   `chore/task-description` (for non-code updates, tests, or config changes)
*   Command to switch: `git checkout -b <branch_name>`

### 3. Verification Before Commit
*   Verify that the code compiles successfully and that all relevant unit tests pass before staging changes.
*   Do not commit broken code.

### 4. Committing Changes
*   Stage modified files using: `git add <file_path>`
*   Commit staged changes following the **Conventional Commits** specification:
    *   `feat: add support for text file attachments`
    *   `fix: resolve KeyError when parsing image payload`
    *   `docs: update walkthrough with metrics endpoints details`
    *   `test: add unit tests for RRF memory blending`
    *   `chore: update dependencies in pyproject.toml`
*   Command: `git commit -m "<type>: <description>"`

### 5. Pushing & Pull Requests
*   Push the branch to the remote origin:
    *   `git push -u origin <branch_name>`
*   When creating or proposing a Pull Request, prepare a clear description:
    *   **Summary**: What was changed and why.
    *   **Verification**: How changes were tested.
    *   **Linked Issues**: Reference any issues resolved by this PR.
