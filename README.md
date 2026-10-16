# AppNeta Alarm Connector Generator — Web GUI

A browser-based tool for generating AppNeta alarm connector JSON payloads. Packaged as a Docker/Podman container — no Python installation required on the host.

Functionally equivalent to `generate-connector-cli` but driven by a web form: enter your AppNeta API credentials, select organizations, configure filters, and download ready-to-POST JSON.

---

## Requirements

- Docker or Podman
- Network access to your AppNeta NIS (for API calls proxied through the container)
- A read-only AppNeta API key scoped to the target organization(s)

---

## Quick Start

### Docker

```bash
docker build -t connector-gui .
docker run -d --name connector-gui -p 8443:8080 connector-gui
```

Open `http://localhost:8443` in a browser.

### Podman

```bash
podman build -t connector-gui .
podman run -d --name connector-gui -p 8443:8080 connector-gui
```

Open `http://localhost:8443` in a browser.

---

## Usage

1. **NIS URL** — Enter your AppNeta base URL (e.g. `https://app-01.pm.appneta.com`). The field turns green when a valid `https://` URL is entered.

2. **API Key** — Enter a read-only AppNeta API key. The key is stored only in your browser session and never written to disk or logged.

3. **Org** (optional) — Enter an org name or ID to restrict processing to a specific organization. Leave blank to process all orgs accessible to the key. Multi-org selection is supported for keys that span a parent and child orgs.

4. **Confirm Org / Load Data** — Click to validate the key, discover organizations, and fetch monitoring points, policies, and policy groups. Filter fields become interactive after this step.

5. **Connector Settings** — Enter the connector name, description, and webhook URL. The Authorization header for the webhook is entered here and substituted into the payload.

6. **Include / Exclude Filters** — Select filter criteria using the chip fields. MP Names, MP Types, and Targets support glob patterns in addition to exact selections — type the pattern and press Enter to add it as a chip. Policies, Policy Groups, and Targets use searchable chip fields. Tags use free-form text: `Category:Value` (exact match), `Category` (all tags for that category), or `:Value` (all categories with that value). **Partial specs (`Category` / `:Value`) are script-expanded** — the GUI queries `GET /api/v3/tag` and resolves them to complete `{category, value}` pairs before building the payload. The API itself only accepts full pairs.

7. **Generate Payload** — Click to build the JSON. Each org produces a separate payload shown in an expandable section. The POST URL (`POST {base_url}/api/v4/connector/alarm?orgId=...`) is shown for each org.

8. **Copy / Download** — Use the per-org Copy and Download buttons to export the payload, or use the global Copy All / Download All controls.

---

## Multi-Org Mode

When the key has access to a parent org and its children, selecting multiple orgs activates per-org accordion sections. Each org gets its own:
- Connector name and description
- Include and exclude filter selections

The PUT (connector ID) field is disabled in multi-org mode — connector IDs are org-specific and cannot be shared across organizations.

---

## Include/Exclude Filter Behavior

AppNeta evaluates include and exclude filter blocks independently when deciding whether to forward an alarm to a connector. Understanding how they interact is essential for getting the expected behavior.

### Include is a strict whitelist

If any include filter field is populated, AppNeta uses it as a whitelist: **only alarms from MPs matching the include criteria are forwarded.** Any MP that does not match is silently dropped — regardless of what the exclude filter contains.

Example: selecting `m50 microAppliance` in the **Include → MP Types** checkboxes means only m50 hardware appliance alarms are delivered. All c50, macOS, Windows, and other MP type alarms are dropped, even if nothing in the exclude filter would suppress them.

Leaving all include fields empty means no restriction — all alarms pass through to the exclude stage.

### Exclude is an additive blacklist

Populated exclude fields suppress alarms that match. An alarm matching **any** exclude field is dropped. Non-matching alarms pass through unchanged.

Example: selecting `macOS` in **Exclude → MP Types** drops all macOS agent alarms while passing m50, c50, Windows, and all other types unchanged.

Leaving all exclude fields empty suppresses nothing.

### Exclude overrides include

If an MP passes the include filter but also matches an exclude rule, the alarm is **dropped**. Exclude always wins.

This lets you select a broad class of MPs with include and carve out specific MPs with exclude. For example: including all c50 containers via **MP Types** while excluding one specific c50 by name via **MP Names** — the named MP is still suppressed even though its type would otherwise pass the include filter.

### Combined include and exclude — evaluation order

AppNeta applies filters in sequence:

1. **Include filter** — MPs not matching the include criteria are dropped
2. **Exclude filter** — MPs matching any exclude rule are dropped from what remains
3. Alarms that survive both stages are forwarded to the webhook

### MP type filter values

The **MP Types** chip field is pre-populated with a static list sourced from `GET /v4/monitoringPoint` across AppNeta platform hosts, then merged with the org's live device types at load time. The values use AppNeta's full display names:

| Type string | Device |
|---|---|
| `m20 microAppliance` | AppNeta m20 hardware appliance |
| `m22 microAppliance` | AppNeta m22 hardware appliance |
| `m25 microAppliance` | AppNeta m25 hardware appliance |
| `m30 microAppliance` | AppNeta m30 hardware appliance |
| `m35 microAppliance` | AppNeta m35 hardware appliance |
| `m50 microAppliance` | AppNeta m50 hardware appliance |
| `m70 microAppliance` | AppNeta m70 hardware appliance |
| `r40 rackAppliance` | AppNeta r40 rack appliance |
| `r45 rackAppliance` | AppNeta r45 rack appliance |
| `r90 rackAppliance` | AppNeta r90 rack appliance |
| `r1000 rackAppliance` | AppNeta r1000 rack appliance |
| `v30 virtualAppliance` | AppNeta v30 virtual appliance |
| `v35-KVM virtualAppliance` | AppNeta v35 virtual appliance (KVM hypervisor) |
| `v35-VMware virtualAppliance` | AppNeta v35 virtual appliance (VMware hypervisor) |
| `c50 Container` | AppNeta c50 container agent (Docker/Podman/Kubernetes) |
| `cpe40 Container` | AppNeta cpe40 container agent |
| `macOS` | AppNeta software agent on macOS |
| `Windows` | AppNeta software agent on Windows |
| `Global Monitoring Point` | AppNeta global monitoring point |
| `NetOps Data Collector` | AppNeta NetOps data collector |

Note: r-series appliances use the `rackAppliance` category suffix, not `microAppliance`. The v35 virtual appliance is differentiated by hypervisor into two separate type strings.

AppNeta treats macOS and Windows software agents as two distinct types. If you want to filter on both, select both. The short code `n10` is not a valid filter value.

**Important:** The `monitoringPointType` filter matches AppNeta's **agent classification**, not the `MP Type` tag delivered in the alarm webhook payload. An MP running a c50 agent on an m50 hardware box will match the `"c50 Container"` filter, but its alarm payload will carry `"MP Type: m50"` in the tags. Do not use the alarm payload's MP Type tag to predict which filter value will match — check the MP's agent type in the AppNeta UI instead.

---

## Glob Patterns

The **MP Names**, **MP Types**, and **Targets** filter fields accept glob patterns in addition to exact values. To add a glob pattern: type it into the chip field input and press **Enter**. Glob chips are displayed in orange monospace to distinguish them from selected items.

Supported wildcards:

| Character | Meaning | Example | Matches |
|---|---|---|---|
| `*` | Any sequence of characters | `ac*` | `acme-m50`, `ac-lab-01` |
| `**` | Same as `*` for flat strings (no path separators in MP names) | `sw**` | Same as `ac*` |
| `?` | Exactly one character | `?v-trident` | `sv-trident`, `av-trident` |
| `!` | **No effect** — does not exclude anything, does not exclude anything | `!acme-m50` | Nothing — passes through unchanged, as if `!acme-m50` weren't in the list at all |
| `+` | One or more characters (not reliably supported; prefer `*`) | `ac+` | Intended: names starting with ac |

Compound patterns combining multiple wildcards are also accepted: `a*-m?0` matches `acme-m50`.

For **MP Types**, glob patterns can match across the full type string including the category suffix:

```
* microAppliance    → all hardware appliances (m20 through m70)
*Container          → c50 Container and cpe40 Container
m*                  → m50 microAppliance and macOS (both start with m — be specific)
```

For **Targets**, glob patterns match against the target hostname or URL:

```
*.example.com       → any subdomain of example.com
10.0.*              → any host in the 10.0.0.0/8 range (prefix match)
```

Glob patterns are passed to the AppNeta API as-is — the connector filter engine interprets them. The GUI does not expand or validate glob syntax.

---

## Dedicated ID Fields

Each filter block's **Advanced** section has three numeric-only fields: **MP IDs**, **Policy IDs**, and **Policy Group IDs**. Use these when you already know a resource's numeric ID and want to be unambiguous about it, instead of typing the ID into the corresponding name field.

- Typed input is restricted to digits — non-numeric characters are stripped as you type, and pasted/free-typed text that isn't purely numeric is rejected.
- The autocomplete dropdown shows the numeric ID first, with the resource's name as a smaller secondary label, so you can confirm you've picked the right one while searching. Selecting an entry stores its ID, not its name.
- These fields don't validate against the live org — an ID with no matching resource is accepted silently, same as the CLI's equivalent fields.
- **Don't combine an ID and a name for the same resource in one filter block.** When both are present for the same MP/policy/group, the API's response can show the resource's v3 (org-scoped) ID instead of the v4 global ID that was submitted. The filter is applied using the submitted ID, so this only affects what you see when reviewing the payload.

---

## UPDATE vs CREATE Mode

When a connector ID is entered, the tool operates in **UPDATE mode**: the output JSON includes `"id"` and is suitable for `PUT /api/v4/connector/alarm?orgId=<id>`. Only one org may be selected in UPDATE mode.

Without a connector ID, the tool operates in **CREATE mode**: output is suitable for `POST /api/v4/connector/alarm?orgId=<id>`.

---

## Webhook Targets

The connector delivers alarm payloads to any HTTPS endpoint that accepts POST. Common enterprise targets and their required auth patterns:

| Target | Webhook URL pattern | Auth header | Notes |
|---|---|---|---|
| **Splunk HEC** | `https://<host>:8088/services/collector/raw` | `Authorization: Splunk <token>` | Use NONE auth type — Splunk rejects `Bearer` |
| **ServiceNow** | `https://<instance>.service-now.com/api/<ns>/<api>/<resource>` | `Authorization: Basic <base64>` | URL is customer-defined (Scripted REST API) |
| **OpsGenie** | `https://api.opsgenie.com/v2/alerts` | `Authorization: GenieKey <key>` | EU: `api.eu.opsgenie.com` |
| **Datadog Logs** | `https://http-intake.logs.datadoghq.com/api/v2/logs` | `DD-API-KEY: <key>` | Region-specific URL — confirm your Datadog site |
| **Microsoft Teams** | `https://prod-*.logic.azure.com/workflows/...` | None (auth is `sig=` in URL) | Power Automate workflow; legacy `webhook.office.com` URLs retired March 2026 |
| **PagerDuty** | `https://events.pagerduty.com/v2/enqueue` | — | **Requires middleware** — `routing_key` must be in the JSON body; AppNeta connectors cannot inject body fields. Use MuleSoft, Azure Logic Apps, Workato, or a Lambda/Function as an intermediary. |

**Auth type note:** Nearly every platform requires **NONE** for the auth type, with the credential passed via a custom header. AppNeta's built-in BEARER type (`Authorization: Bearer <token>`) only works if the endpoint is explicitly configured to accept that format. Most platforms use non-standard prefixes (`Splunk`, `GenieKey`, `Api-Token`) or non-standard header names (`DD-API-KEY`).

---

## Security Notes

- API keys and webhook credentials are transmitted to the container over localhost only and are never written to disk or logged.
- All AppNeta API calls are proxied through the container — the browser does not contact the AppNeta NIS directly (CORS restriction).
- Input fields are protected against CRLF injection — control characters in connector names, header values, and webhook URLs are rejected.
- Webhook credential fields are suppressed from password managers (`data-1p-ignore`, `data-lpignore`).

---

## Deployment Notes

The container runs gunicorn with 2 workers on port 8080. The host port (`-p 8443:8080` in the examples above) can be changed to any available port.

For persistent deployment behind a reverse proxy or with iptables DNAT, ensure the container is started with `--restart unless-stopped` (Docker) or a systemd unit (Podman):

### Docker (persistent)

```bash
docker run -d --name connector-gui --restart unless-stopped -p 8443:8080 connector-gui
```

### Podman (persistent via systemd)

```bash
podman generate systemd --name connector-gui --restart-policy=always > ~/.config/systemd/user/connector-gui.service
systemctl --user enable --now connector-gui
```

---

## API Endpoints Used

All API calls are proxied through the `/api/lookup` endpoint on the container. The browser never contacts the AppNeta NIS directly.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/v4/organization` | Discover orgs |
| `GET` | `/v4/monitoringPoint?orgId=<id>` | MP names and types for filter chips |
| `GET` | `/v4/monitoringPolicy?orgId=<id>` | Policy names |
| `GET` | `/v4/monitoringPolicyGroup?orgId=<id>` | Policy group names |

The tool never POSTs or PUTs to AppNeta — it generates JSON only. Submit payloads manually via the AppNeta UI, API client, or curl.

---

## Files

| File | Purpose |
|---|---|
| `app.py` | Flask entry point — mounts Blueprint, redirects `/` to connector UI |
| `connector_app.py` | Flask Blueprint — form routes, payload generation, lookup proxy |
| `lib/` | Business logic shared with CLI: client, resolution, payload, validation |
| `templates/connector.html` | Single-page UI (~2300 lines) |
| `templates/base.html` | Navbar and page shell |
| `static/` | Static assets (favicon) |
| `Dockerfile` | Build config — python:3.11-slim base, gunicorn WSGI |
| `docker-compose.yml` | Single-service compose for local dev and SE deployment |
| `requirements.txt` | flask, gunicorn — only two external deps |
| `test/` | Unit tests — run with `python3 -m pytest test/` (install `flask` and `pytest` first) |

## CLI Companion

The GUI generates connector JSON interactively. For workflows that go beyond one-off generation, use the CLI (`generate-connector-cli/`):

| Need | Use |
|---|---|
| Interactive, one-off connector generation | **This tool (GUI)** |
| Version-controlled TOML configs checked into git | CLI |
| Scripted or bulk connector generation | CLI |
| Backup before a PUT update (auto-written before every merge) | CLI |
| Convert an existing connector JSON to a TOML config | CLI — `support/json_to_toml.py` |
| Recover from a bad connector ID (revert a PUT) | CLI — backup JSON + `json_to_toml.py` |

---

## See Also

- [`../generate-connector-cli/README.md`](../generate-connector-cli/README.md) — CLI equivalent (stdlib-only Python, no container required)
- [AppNeta alarm connectors — TechDocs](https://techdocs.broadcom.com/us/en/ca-enterprise-software/it-operations-management/appneta/GA/alarms-set-up/alarms-connectors.html)
- [AppNeta REST API v4 reference](https://techdocs.broadcom.com/us/en/ca-enterprise-software/it-operations-management/appneta/GA/integrate/api/api-v4.html)
