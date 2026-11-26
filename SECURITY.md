# Security policy

Please report vulnerabilities privately through GitHub: **Security → Report a vulnerability** on this repository
(a private security advisory). Do not open a public issue for a security problem.

In scope: the daily-challenge API (`server/api.py`) and the static site (`web/`). The data files are public statistics.

The challenge server keeps its secret key and SQLite database in `var/` on the server only; nothing secret is in this
repository. If you run your own copy, `api.py serve` creates a fresh secret on first start.
