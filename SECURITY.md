# Security Policy

## Supported Versions

Latest minor version receives security updates.

## Reporting a Vulnerability

Email: security@newsbrief.dev (or use GitHub Security Advisories).

Please don't open public issues for security vulnerabilities.

## Scope

- API key leaks in logs/errors
- Auth bypass on webhook endpoint
- Path traversal in plugin system
- Code injection via config

## Out of scope
- Rate limiting LLM providers (provider's responsibility)
- Social engineering on Telegram bot token
