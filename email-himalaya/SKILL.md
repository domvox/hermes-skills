---
name: email-himalaya
description: Email management via himalaya CLI with Bitwarden-backed authentication.
version: 1.0.0
author: DomKo
license: MIT
dependencies:
  skills: [bitwarden]
  tools: [himalaya, himalaya-password]
  env: [BWS_ACCESS_TOKEN]
  verify:
    - cmd: "himalaya --version"
      expect: "himalaya"
    - cmd: "himalaya-password 2>&1 | wc -c"
      expect_gt: 10
  compositions:
    - name: "bws-to-himalaya-auth"
      description: "BWS provides password to himalaya via himalaya-password wrapper"
      steps:
        - cmd: "himalaya-password | wc -c"
          expect_gt: 10
        - cmd: "himalaya envelope list 2>&1 | grep -c '|'"
          expect_gt: 0
metadata:
  hermes:
    tags: [email, himalaya, bitwarden, composition]
    category: communication
---

# Email via Himalaya + Bitwarden

This skill extends the built-in himalaya skill with Bitwarden-backed authentication.

## Dependencies

- **bitwarden** skill — provides `BWS_ACCESS_TOKEN` and secret retrieval
- **himalaya-password** wrapper — fetches IMAP/SMTP password from BWS
- **himalaya** CLI — email operations

## Authentication Flow

```
BWS_ACCESS_TOKEN → bws secret list → <EMAIL_PASSWORD_SECRET> → himalaya auth.cmd
```

The `himalaya-password` script in `~/.local/bin/` handles this chain.

## Composition Test

To verify the full chain works:

```bash
# 1. BWS returns password
himalaya-password | wc -c  # should be > 10

# 2. Himalaya connects and lists emails
himalaya envelope list | head -3  # should show email table
```

## Usage

All standard himalaya commands work. See built-in himalaya skill for full reference.
