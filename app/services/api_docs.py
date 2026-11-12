"""Contextual API-spec provider.

Endpoints are derived LIVE from the app's own OpenAPI schema + route dependencies, so the 'API Documentation'
tab inside every admin module can never drift from the real API. Request/response examples come from Pydantic
`json_schema_extra` examples where present, otherwise they are synthesised from the JSON schema.
"""
import json
from typing import Any

from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.schemas.docs import EndpointDoc, ModuleDocs, ModuleSummary, ParamDoc

MODULES: dict[str, str] = {
    "auth": "Login, token refresh and API key generation.",
    "properties": "Hotels, resorts and houseboats; units/cabins with custom-icon facilities.",
    "dashboard": "Visual resort grid / houseboat layout with live status, plus an SSE stream.",
    "pricing": "Weekday, weekend and seasonal/holiday pricing rules and stay quotes.",
    "bookings": "Availability, 10-minute holds, full/partial payment confirmation, cancellation.",
    "partners": "B2B / MoU partners, commissions, ledger statements and the partner portal.",
    "payouts": "Partner payout requests and admin approval.",
    "cms": "Headless CMS: company info, blogs, events, galleries, pages, announcements.",
    "channel": "Reseller channel: let other businesses sell your rooms (agreements, commission per night), or sell other businesses' rooms yourself (find rooms, hold, confirm, your bookings), the commission book (statements, mark paid, confirm received, dispute) and cancellation requests with refund rules. For your own website as a reseller: create an API key with the scopes channel:read and channel:book (API access page), then: GET /channel/agreements to find your agreement ids, GET /channel/properties, GET /channel/availability, POST /channel/hold, POST /channel/confirm, GET /channel/bookings, and GET /channel/bookings/{id}/cancel-quote then POST /channel/bookings/{id}/cancel-request to cancel.",
    "customers": "Customers (CRM): everyone who booked or wrote in, with booking figures, tags, notes, filters and a CSV download. Staff only; never available to public API keys.",
    "packages": "Ready-made trips with a 'starting from' price. Websites read published ones; one call turns a package into a dated, published event.",
    "events": "Dated trips agencies sell (usually made from a package). Websites read published, upcoming events. Not the same as the website news 'events' in the cms module.",
    "event_bookings": "Seat bookings on events. A website: POST /events/{id}/hold (customer details, seats; seats held 10 minutes), POST /event-bookings/status/{ref}/proof (screenshot of the manual payment), POST /event-bookings/status/{ref}/payment (method, amount, transaction id), GET /event-bookings/status/{ref} (progress). Keep the `token` from the hold and send it as X-Booking-Token. The business then confirms or rejects the payment in the console. API key needs the scope events:book. Staff-side calls (list, confirm, reject, cancel) need a signed-in user.",
    "business": "The business profile: licence, owner, TIN/BIN, bank and mobile banking accounts, booking rules. Console use (GET/PUT need a signed-in person; saving is admin only). A website reads GET /business/public (scope cms:read) to show the logo, licence, contact details and the accounts customers may pay into.",
    "vendors": "Vendors by place (resorts, restaurants, guides, chander gari, jeep, CNG) and their own rates. Staff only; never public.",
    "budgets": "Event budget calculator: saved cost estimates with margin, per-person price and copies. Staff only; never public.",
    "staff": "Staff accounts and what each person may do. Admins only; console use.",
    "reports": "Business overview numbers: bookings, money collected, occupancy, arrivals, partner sales.",
    "media": "Media library: upload photos and videos, add video links, search, tag and delete.",
    "affiliate": "Public short-link redirect that sets the encrypted attribution cookie.",
    "docs": "This documentation provider.",
}

_UUID_EX = "00000000-0000-0000-0000-000000000000"


def example_for(schema: dict, comps: dict, depth: int = 0) -> Any:
    if depth > 6 or not isinstance(schema, dict):
        return None
    if "$ref" in schema:
        return example_for(comps.get(schema["$ref"].split("/")[-1], {}), comps, depth + 1)
    if "example" in schema:
        return schema["example"]
    if schema.get("examples"):
        return schema["examples"][0]
    if schema.get("default") is not None:
        return schema["default"]
    if "enum" in schema:
        return schema["enum"][0]
    if "const" in schema:
        return schema["const"]
    for key in ("anyOf", "oneOf"):
        if key in schema:
            options = [o for o in schema[key] if o.get("type") != "null"]
            return example_for(options[0], comps, depth + 1) if options else None
    if "allOf" in schema:
        return example_for(schema["allOf"][0], comps, depth + 1)
    t = schema.get("type")
    if t == "object" or "properties" in schema:
        return {k: example_for(v, comps, depth + 1) for k, v in schema.get("properties", {}).items()}
    if t == "array":
        item = example_for(schema.get("items", {}), comps, depth + 1)
        return [] if item is None else [item]
    if t == "string":
        return {"uuid": _UUID_EX, "date": "2026-12-24", "date-time": "2026-12-24T10:00:00Z",
                "email": "user@example.com"}.get(schema.get("format"), "string")
    if t == "integer":
        return schema.get("minimum", 1)
    if t == "number":
        return 0.0
    if t == "boolean":
        return True
    return None


def _scopes(route: APIRoute) -> list[str]:
    found: list[str] = []

    def walk(dep):
        scopes = getattr(dep.call, "__scopes__", None)
        if scopes:
            found.extend(scopes)
        for d in dep.dependencies:
            walk(d)
    walk(route.dependant)
    return sorted(set(found))


def _json_schema(content: dict | None) -> dict | None:
    return ((content or {}).get("application/json") or {}).get("schema")


def snippets(method: str, url: str, body: Any, public: bool) -> dict[str, str]:
    hdr = {"Content-Type": "application/json"} if body is not None else {}
    if not public:
        hdr = {"X-API-KEY": "YOUR_API_KEY", "X-API-SECRET": "YOUR_API_SECRET", **hdr}
    payload = json.dumps(body, indent=2) if body is not None else None

    curl = [f'curl -X {method} "{url}"'] + [f'  -H "{k}: {v}"' for k, v in hdr.items()]
    if payload:
        curl.append(f"  -d '{json.dumps(body)}'")

    fetch = (f'const res = await fetch("{url}", {{\n  method: "{method}",\n  headers: {json.dumps(hdr, indent=4)},\n'
             + (f"  body: JSON.stringify({payload}),\n" if payload else "") + "});\nconst data = await res.json();")
    axios = (f'import axios from "axios";\n\nconst {{ data }} = await axios.request({{\n  method: "{method.lower()}",\n'
             f'  url: "{url}",\n  headers: {json.dumps(hdr, indent=4)},\n'
             + (f"  data: {payload},\n" if payload else "") + "});")
    py = (f'import requests\n\nres = requests.request(\n    "{method}",\n    "{url}",\n    headers={json.dumps(hdr, indent=4)},\n'
          + (f"    json={payload},\n" if payload else "") + ")\nres.raise_for_status()\nprint(res.json())")
    return {"curl": " \\\n".join(curl), "javascript_fetch": fetch, "javascript_axios": axios, "python_requests": py}


def upload_snippets(url: str, fields: list[str]) -> dict[str, str]:
    """multipart/form-data endpoints (file uploads) need a form, not a JSON body."""
    extra = [f for f in fields if f != "file"]
    curl = f'curl -X POST "{url}" \\\n  -H "X-API-KEY: YOUR_API_KEY" \\\n  -H "X-API-SECRET: YOUR_API_SECRET" \\\n  -F "file=@photo.jpg"' \
        + "".join(f' \\\n  -F "{f}=..."' for f in extra)
    form_js = "".join(f'form.append("{f}", "...");\n' for f in extra)
    fetch = (f'const form = new FormData();\nform.append("file", fileInput.files[0]);\n{form_js}'
             f'const res = await fetch("{url}", {{\n  method: "POST",\n  headers: {{ "X-API-KEY": "YOUR_API_KEY", "X-API-SECRET": "YOUR_API_SECRET" }},\n'
             "  body: form,   // the browser sets the multipart Content-Type for you\n});\nconst data = await res.json();")
    axios = (f'import axios from "axios";\n\nconst form = new FormData();\nform.append("file", fileInput.files[0]);\n{form_js}'
             f'const {{ data }} = await axios.post("{url}", form, {{\n  headers: {{ "X-API-KEY": "YOUR_API_KEY", "X-API-SECRET": "YOUR_API_SECRET" }},\n}});')
    data = "{" + ", ".join(f'"{f}": "..."' for f in extra) + "}"
    py = (f'import requests\n\nwith open("photo.jpg", "rb") as f:\n    res = requests.post(\n        "{url}",\n'
          f'        headers={{"X-API-KEY": "YOUR_API_KEY", "X-API-SECRET": "YOUR_API_SECRET"}},\n        files={{"file": f}},\n        data={data},\n    )\nres.raise_for_status()\nprint(res.json())')
    return {"curl": curl, "javascript_fetch": fetch, "javascript_axios": axios, "python_requests": py}


def _params(op: dict, where: str, comps: dict) -> list[ParamDoc]:
    return [ParamDoc(name=p["name"], required=p.get("required", False),
                     type=(p.get("schema", {}).get("type") or p.get("schema", {}).get("format") or "string"),
                     description=p.get("description"))
            for p in op.get("parameters", []) if p.get("in") == where]


def iter_routes():
    """Yield (full_path, APIRoute). Walks our own routers instead of app.routes because recent FastAPI
    versions wrap included routers lazily, which hides them from app.routes."""
    from app.api import public
    from app.api.v1.router import API_PREFIX, MODULE_ROUTERS
    for router in MODULE_ROUTERS:
        for r in router.routes:
            if isinstance(r, APIRoute):
                yield API_PREFIX + r.path_format, r
    for r in public.router.routes:
        if isinstance(r, APIRoute):
            yield r.path_format, r


def build_module_docs(app: FastAPI, module: str, base_url: str) -> ModuleDocs | None:
    if module not in MODULES:
        return None
    spec = app.openapi()
    comps = spec.get("components", {}).get("schemas", {})
    endpoints: list[EndpointDoc] = []
    for full_path, route in iter_routes():
        if module not in (route.tags or []):
            continue
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            op = spec["paths"].get(full_path, {}).get(method.lower())
            if not op:
                continue
            path_params = _params(op, "path", comps)
            url_path = full_path
            for p in path_params:
                url_path = url_path.replace("{" + p.name + "}", _UUID_EX if "id" in p.name else f"<{p.name}>")
            body = example_for(_json_schema((op.get("requestBody") or {}).get("content")) or {}, comps) \
                if op.get("requestBody") else None
            ok = next((c for c in op.get("responses", {}) if c.startswith("2")), "200")
            resp = example_for(_json_schema(op["responses"].get(ok, {}).get("content")) or {}, comps)
            scopes = _scopes(route)
            qp = _params(op, "query", comps)
            required_q = "&".join(f"{p.name}=<{p.name}>" for p in qp if p.required)
            url = f"{base_url}{url_path}" + (f"?{required_q}" if required_q else "")
            public = not scopes
            form = ((op.get("requestBody") or {}).get("content") or {}).get("multipart/form-data")
            snip = snippets(method, url, body, public)
            if form:
                ref = (form.get("schema") or {}).get("$ref", "").rsplit("/", 1)[-1]
                fields = list((comps.get(ref, {}).get("properties") or {}).keys())
                snip = upload_snippets(url, fields)
                body = {f: ("(the file)" if f == "file" else "...") for f in fields}
            endpoints.append(EndpointDoc(
                method=method, path=full_path, summary=op.get("summary"), description=op.get("description"),
                required_scopes=scopes, auth="PUBLIC" if public else "X-API-KEY + X-API-SECRET, or Bearer JWT",
                path_params=path_params, query_params=qp, request_body_example=body,
                response_status=int(ok), response_example=resp, snippets=snip))
    return ModuleDocs(module=module, description=MODULES[module], base_url=base_url,
                      auth_headers={"X-API-KEY": "<tenant api key>", "X-API-SECRET": "<tenant api secret>"},
                      endpoints=endpoints)


def list_modules(app: FastAPI) -> list[ModuleSummary]:
    counts: dict[str, int] = {m: 0 for m in MODULES}
    for _, route in iter_routes():
        for tag in route.tags or []:
            if tag in counts:
                counts[tag] += len(route.methods - {"HEAD", "OPTIONS"})
    return [ModuleSummary(module=m, description=d, endpoint_count=counts[m]) for m, d in MODULES.items()]
