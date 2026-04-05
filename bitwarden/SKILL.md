---
name: bitwarden
description: Set up and use Bitwarden Secrets Manager CLI (bws). Use when reading, listing, or injecting secrets into env vars and dotenv files.
version: 1.5.0
author: DomKo
license: MIT
dependencies:
  tools: [bws]
  env: [BWS_ACCESS_TOKEN]
  verify:
    - cmd: "bws --version"
      expect: "bws"
    - cmd: "bws secret list 2>&1 | head -1"
      expect: "["
metadata:
  hermes:
    tags: [security, secrets, bitwarden, bws, cli]
    category: security
setup:
  help: "Create a machine account at https://vault.bitwarden.com → Secrets Manager → Machine Accounts"
  collect_secrets:
    - env_var: BWS_ACCESS_TOKEN
      prompt: "Bitwarden Secrets Manager Access Token"
      provider_url: "https://bitwarden.com/help/machine-accounts/"
      secret: true
---

# Bitwarden Secrets Manager CLI

Use this skill when the user wants secrets managed through Bitwarden Secrets Manager instead of plaintext env vars or files.

## Requirements

- Bitwarden organization with Secrets Manager enabled
- `bws` CLI installed
- Machine account access token (`BWS_ACCESS_TOKEN`)

## Installation

```bash
# Download from https://github.com/bitwarden/sdk-sm/releases
# Find the latest bws-vX.Y.Z release, download the linux-x64 archive
unzip bws-*.zip
install bws ~/.local/bin/bws
bws --version  # verify
```

## When to Use

- Read secrets from Bitwarden Secrets Manager
- List secrets in a project
- Run commands with secrets injected as env vars
- Export secrets to dotenv format

## Authentication

Set `BWS_ACCESS_TOKEN` in the Hermes `.env` file (the skill will prompt for this on first load).

`bws` is fully stateless — each call authenticates via the env var. No session management, no signin flow, no tmux workaround needed.

```bash
export BWS_ACCESS_TOKEN="0.your-token-here"
bws secret list  # verify — should list secrets
```

## Common Operations

### Run a command with secrets injected

Preferred method — `bws run` injects all accessible secrets as env vars:

```bash
bws run -- 'echo $SECRET_NAME'
bws run --project-id <id> -- 'npm run start'
bws run --no-inherit-env -- './my-script.sh'  # clean env, secrets only
```

Secret key names become env var names. If keys are not POSIX-compliant (spaces, special chars), use `--uuids-as-keynames` to use secret UUIDs instead.

### List secrets

```bash
bws secret list
bws secret list <project-id>
```

### Read a single secret by ID

```bash
bws secret get <secret-id>
```

### Export secrets to dotenv format

```bash
bws secret list --output env > /tmp/secrets.env
```

### Output formats

`bws` supports `--output` with: `json` (default), `yaml`, `table`, `tsv`, `env`, `none`.

## Guardrails

- Never print raw secret values back to user unless they explicitly request the value.
- Prefer `bws run` for injecting secrets into commands. Use dotenv export only for bulk sync.
- If a secret is needed once, use `bws run` — do not write to disk.
- Manage secrets (create/update/delete) through the Bitwarden web vault, not CLI. The CLI supports these operations but vault provides audit trail and approval flow.

## Performance Note

Multiple rapid `bws` calls may hit rate limits. To reduce this, enable state files which cache auth tokens:

```bash
bws config state-dir ~/.config/bws/state
```

When possible, use a single `bws run` call instead of multiple `bws secret get` calls.

## Troubleshooting

- `Missing access token` → `BWS_ACCESS_TOKEN` not exported or empty.
- `bws: command not found` → binary not in PATH. Check `~/.local/bin/` or `/usr/local/bin/`.
- `Unauthorized` → token expired or revoked. Regenerate in Bitwarden web vault.
- Empty output from `bws secret list` → machine account has no project access. Check vault permissions.
- Non-POSIX key names in `bws run` → use `--uuids-as-keynames` flag.

## References

- https://bitwarden.com/help/secrets-manager-cli/
- https://bitwarden.com/help/machine-accounts/
