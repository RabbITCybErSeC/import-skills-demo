# import-skills-demo

This repository now includes an importable PR review skill prompt.

## Pull Request Review Skill (web-fetchable)

- Skill file: `skills/pull-request-review-skill.md`
- Intended use: give an AI agent strict instructions for pull request reviews.

### Import via web fetching

When this repo is hosted (for example on GitHub), fetch the raw file URL and import it into your agent skill system.

Example raw URL pattern:

```text
https://raw.githubusercontent.com/<owner>/<repo>/<branch>/skills/pull-request-review-skill.md
```

Then use your agent platform's web-fetch/import flow with that URL.
