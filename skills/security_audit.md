# Security Audit Workflow

## When to use
Run this workflow when asked to perform a security audit on a codebase or specific file.

## Workflow
1. Look for hardcoded credentials (API keys, passwords, database URLs).
2. Check for missing validation on user input.
3. Check for SQL injection vulnerabilities.
4. Verify proper use of encryption and hashing.
5. Identify overly permissive file permissions.

## Output
Generate a structured report of vulnerabilities found, categorized by severity (High, Medium, Low), and provide remediation steps.
