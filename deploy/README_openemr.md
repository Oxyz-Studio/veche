# OpenEMR local stack (for node-identity de-risk captures)

## What this is
`docker-compose.openemr.yml` brings up OpenEMR + MariaDB with auto-setup so it
self-initializes. Screenshots are captured by `../scripts/capture_openemr.py`.

## Run
```bash
docker compose -f deploy/docker-compose.openemr.yml up -d
# wait ~3-6 min for self-init, poll http://localhost:8080
./.venv/bin/python scripts/capture_openemr.py   # writes PNGs to ./captures/
```

- URL: http://localhost:8080
- Creds: admin / pass   (set via OE_USER / OE_PASS in the compose env)
- MySQL: host=mysql user=openemr pass=openemr root=root

## BLOCKER encountered 2026-06-27
Docker Hub **blob/layer CDN download is throttled to ~1.3 KB/s** on this network
(http 200 but near-zero throughput). Manifests, auth, registry API, and general
internet (github.com at ~742 KB/s) all work fine — only container-image blob
downloads stall. Verified the same throttle on `mariadb`, `alpine`, `openemr`,
and the `mirror.gcr.io` mirror. The ~2.5 GB openemr image cannot be pulled in any
reasonable time. Everything else is proven ready (compose validates, chromium
installed, playwright imports, capture script written) — re-run the two commands
above once blob throughput recovers.
