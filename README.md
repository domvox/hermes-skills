# hermes-skills

Reusable skills for [Hermes Agent](https://github.com/NousResearch/hermes-agent) by Nous Research.

## Skills

### [bitwarden](bitwarden/SKILL.md)

Bitwarden Secrets Manager CLI (`bws`) integration. Read, list, and inject secrets into env vars and dotenv files. Uses native `bws run` for secret injection — no workarounds.

- Verified against [official Bitwarden CLI docs](https://bitwarden.com/help/secrets-manager-cli/)
- Stateless auth (no session management needed)
- Rate limiting awareness with state file config
- Dependency declarations for automated verification

### [email-himalaya](email-himalaya/SKILL.md)

Email management via himalaya CLI with Bitwarden-backed authentication. Composition skill that chains bitwarden → himalaya for secure email access.

- Depends on bitwarden skill for secret retrieval
- Composition test: BWS → password → himalaya → email list
- Full auth flow without plaintext passwords

### [skill-autoresearch](skill-autoresearch/SKILL.md)

Automated evaluation and improvement loop for skills and code. Iteratively optimizes instruction artifacts (SKILL.md, prompts) and executable artifacts (scripts, validators) using frozen benchmarks and structured evaluation.

- Dual mode: instruction (LLM judge) and code (deterministic tests)
- Cross-run archive with pattern reuse
- Self-modification with constitutional safety rules
- External verification step for tools/APIs referenced in targets
- Mandatory PII and secrets scanning in every eval plan
- **Dependency verification and composition testing** (v0.7.0)

Inspired by [Karpathy's autoresearch](https://x.com/karpathy/status/1886192184808149383), adapted for AI agent artifacts.

## Skill Graph

Skills can declare dependencies on tools, env vars, other skills, and define composition tests in their frontmatter:

```yaml
dependencies:
  skills: [bitwarden]
  tools: [himalaya, himalaya-password]
  env: [BWS_ACCESS_TOKEN]
  verify:
    - cmd: "himalaya --version"
      expect: "himalaya"
  compositions:
    - name: "bws-to-himalaya-auth"
      steps:
        - cmd: "himalaya-password | wc -c"
          expect_gt: 10
        - cmd: "himalaya envelope list 2>&1 | grep -c '|'"
          expect_gt: 0
```

Run `tools/skill-graph-test` to verify all dependencies and compositions:

```bash
python3 tools/skill-graph-test           # test all skills
python3 tools/skill-graph-test bitwarden # test one skill
```

## Installation

Copy the skill directory into your Hermes skills folder:

```bash
# Single skill
cp -r bitwarden/ ~/.hermes/skills/bitwarden/

# All skills
cp -r */ ~/.hermes/skills/

# Install test tool
install tools/skill-graph-test ~/.local/bin/
```

## License

MIT
