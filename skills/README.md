# Kinthic Skills

Skills are the fastest way to extend Kinthic's capabilities.

Drop a Markdown file into `~/.kinthic/skills/`, restart Kinthic, and the agent can use that workflow guidance during reasoning.

This **`README.md` is contributor documentation only**—the loader skips files whose stem is `README`, so this page is never injected into the agent prompt as a skill.

## Skill format

Each skill is a plain Markdown file with:

1. A clear title.
2. A trigger or usage description.
3. Short numbered rules the agent should follow.
4. Concrete output expectations when useful.

Example:

```markdown
# Repo Researcher

When asked to research a repository:
1. Identify the main architecture areas first.
2. Call out one risk or contradiction if present.
3. Suggest one safe next step and ask before acting.
```

## Contribution rules

- Keep skills focused on one repeatable job.
- Prefer clear operator-safe steps over vague advice.
- Avoid secrets, credentials, or environment-specific assumptions.
- If a skill implies risky actions, require explicit approval language.
- Add an example prompt in the PR description so maintainers can test it quickly.

## Submit your first skill in 5 minutes

1. Copy one of the existing skills in your skills directory.
2. Rename it for the workflow you want to add.
3. Rewrite the title and numbered steps.
4. Test it locally with `kinthic` or `kinthic web`.
5. Open a PR or use the `Skill request` issue template if you want feedback first.
