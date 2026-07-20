# Analyze Logs Workflow

## When to use
Run this workflow when asked to analyze server logs, stack traces, or error dumps.

## Workflow
1. Identify the time window of the failure.
2. Filter out routine noise (INFO/DEBUG lines).
3. Pinpoint the root cause Exception or ERROR line.
4. Correlate the error with specific code files.

## Output
A summary of what caused the crash and recommendations for a fix.
