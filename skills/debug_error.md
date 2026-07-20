# Debug Error Workflow

## When to use
Run this workflow when given a specific error message or stack trace to solve.

## Workflow
1. Read the exact error message.
2. Search the codebase for the file and line number mentioned.
3. Understand the state that leads to the error.
4. Formulate a hypothesis for why the state is invalid.
5. Propose a code change to fix the bug.

## Output
A clear explanation of the bug and the exact diff to fix it.
