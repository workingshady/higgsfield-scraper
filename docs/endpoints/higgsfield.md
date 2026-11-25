# Higgsfield: endpoint docs index

This is the per-site entry point that the `reverse-engineer-site` skill expects. The content lives in:

| Doc | What's in it |
|---|---|
| [`../REVERSE_ENGINEERING.md`](../REVERSE_ENGINEERING.md) | All findings: stack, method, JS evidence, plan-set logic, geo pricing, cost shapes, verification, change monitoring |
| [`../ENDPOINTS.md`](../ENDPOINTS.md) | Every endpoint: params, auth, response structure, meaning of each field, which output entity it becomes |
| [`../ENDPOINT_FIELDS.md`](../ENDPOINT_FIELDS.md) | Auto-generated list of every JSON path with types and examples (`python scripts/gen_endpoint_fields.py`) |
| [`../higgsfield.postman_collection.json`](../higgsfield.postman_collection.json) | Postman collection (public + auth folders) |
| [`../../CLI.md`](../../CLI.md) | How to run the scraper: every option and combination |

Quick facts (2026-11-25): 5 public JSON endpoints and 4 login-only. All prices are in USD.
`plan_set_key=ps_a3` = the US price list. The country is detected from the IP and cannot be overridden.
