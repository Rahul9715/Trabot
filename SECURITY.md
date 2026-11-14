# Security policy

This is an early-stage trading software prototype. Do not deploy it with funded broker credentials or enable live trading.

## Secrets
- Keep all credentials in local environment variables or an appropriate secret manager.
- Never commit `.env`, OAuth access/refresh tokens, API keys, client secrets, private keys, account identifiers, or broker session files.
- If a credential is accidentally committed, revoke/rotate it immediately; deleting the file in a later commit does not make the secret safe.

## Reporting
Report suspected vulnerabilities privately to the repository owner. Do not include real trading credentials, personal account data, or live order identifiers in public issues.

## Current limitations
The application is not production-hardened. Authentication/authorisation, broker lifecycle reconciliation, resilient recovery, deployment hardening, and independent security review remain outstanding. See `README.md` and `REVIEW_REPORT.md`.
