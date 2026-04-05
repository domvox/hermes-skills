# hermes-skills

Reusable skills for [Hermes Agent](https://github.com/NousResearch/hermes-agent) by Nous Research.

## Skills

### [bitwarden](bitwarden/SKILL.md)

Bitwarden Secrets Manager CLI (`bws`) integration. Read, list, and inject secrets into env vars and dotenv files. Uses native `bws run` for secret injection — no workarounds.

- Verified against [official Bitwarden CLI docs](https://bitwarden.com/help/secrets-manager-cli/)
- Stateless auth (no session management needed)
- Rate limiting awareness with state file config

### [skill-autoresearch](skill-autoresearch/SKILL.md)

Automated evaluation and improvement loop for skills and code. Iteratively optimizes instruction artifacts (SKILL.md, prompts) and executable artifacts (scripts, validators) using frozen benchmarks and structured evaluation.

- Dual mode: instruction (LLM judge) and code (deterministic tests)
- Cross-run archive with transfer learning
- Self-modification with constitutional safety rules
- External verification step for tools/APIs referenced in targets

Inspired by [Karpathy's autoresearch](https://x.com/karpathy/status/1886192184808149383), adapted for AI agent artifacts.

## Installation

Copy the skill directory into your Hermes skills folder:

```bash
# Single skill
cp -r bitwarden/ ~/.hermes/skills/bitwarden/

# All skills
cp -r */ ~/.hermes/skills/
```

## License

MIT
