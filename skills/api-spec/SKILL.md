---
name: api-spec
description: Use when the user pastes/references a Jira API spec ticket they created and describes an endpoint's requirements, and wants the spec written into that ticket. Produces a GAMAPASS-3295-format spec (method/path, authentication, request params, JSON response body, status codes) as ADF and writes it back to the ticket.
---

# API Spec (Jira)

## Overview

The user creates an empty API spec ticket in Jira, references it (by key) and
describes the endpoint requirements in the session. This skill turns that
description into a spec matching the **GAMAPASS-3295** house format and writes
it back into the ticket's description as Atlassian Document Format (ADF).

Reference ticket: `GAMAPASS-3295` — fetch it with the `jira` skill if you need
to see the canonical rendering.

## Workflow

1. **Get the ticket key** from the user (e.g. `GAMAPASS-1234`).
2. **Gather the endpoint details** from the user's requirement description. For
   each endpoint you need: method, path, authentication, request parameters
   and/or body, the JSON response body, and status codes. If anything required
   is missing or ambiguous, ask before generating — do not invent fields.
3. **Build a spec JSON file** (schema below) in the scratchpad.
4. **Dry-run first** to review the ADF, then write back:
   ```bash
   python3 ~/.claude/skills/api-spec/build_spec.py spec.json --dry-run   # review
   python3 ~/.claude/skills/api-spec/build_spec.py spec.json             # writes to ticket
   ```
   The script reads `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN` from the
   environment and PUTs to `/rest/api/3/issue/{ticket}`.
5. **Confirm** the HTTP 204/200 result and give the user the ticket link.

> Writing back overwrites the ticket's description. If the ticket already has
> content you must preserve, fetch it first (`jira` skill) and confirm with the
> user before overwriting.

## New endpoint vs. modifying an existing one

- **New endpoint** → write the full spec: `auth`, `request`, `responseBody`,
  `statusCodes` (the GAMAPASS-3295 shape below).
- **Modifying an existing endpoint** → keep it lean. State that it's an existing
  API and show only what changes. Use:
  - `note` — a paragraph after the method/path, e.g. `"Existing API — this ticket only adds the response fields below; all current fields are unchanged."`
  - `changes` — the added/modified fields, rendered as a single JSON **code block** (not a bullet list). Each entry: `{ "field", "type", "desc", "kind": "added|modified|removed", "example"? }`. The block shows `"field": <example>, // kind: desc` per line; example value is derived from `type` unless `example` is given.
  - Omit `auth`, `request`, `responseBody`, `statusCodes` unless they genuinely change. Every section is optional except method/path.

## The Format (what GAMAPASS-3295 looks like)

Each endpoint renders, in order:

- **API Method and Path:** `[GET] /v1/faq` ← code-formatted `[METHOD] /path`
- **Description** (optional but recommended) — a short paragraph saying what this
  new API does, or what the change accomplishes. Set via the `description` field.
- **Authentication:** **None** (public endpoint — no token required) ← value bold, optional note after
- **API Request** (only if there are params/body)
  - **Query Parameters:** / **Path Parameters:** — bullet list of `` `name` `` (type, optional|required) — description
  - **Request Body:** — JSON code block
- **API Response (Body)** — JSON code block
- **Status Codes** — bullet list of `` `200 OK` `` — description

Use an em dash (`—`) as the separator, matching the original. Multiple
endpoints in one ticket are separated by a horizontal rule.

## Spec JSON Schema

Single endpoint = top-level object; multiple = wrap in `{"ticket","endpoints":[...]}`.

```json
{
  "ticket": "GAMAPASS-1234",
  "method": "GET",
  "path": "/v1/faq",
  "auth": { "value": "None", "note": "(public endpoint — no token required)" },
  "request": {
    "pathParameters":  [ { "name": "id", "type": "string", "required": true, "desc": "..." } ],
    "queryParameters": [ { "name": "page", "type": "integer", "required": false, "desc": "page number, default 1" } ],
    "body": "{\n  \"name\": \"string\"\n}"
  },
  "responseBody": "{\n  \"faqs\": [],\n  \"totalCount\": 0\n}",
  "statusCodes": [
    { "code": "200 OK", "desc": "success" },
    { "code": "400 Bad Request", "desc": "invalid query parameters" },
    { "code": "500 Internal Server Error", "desc": "backend gRPC error" }
  ]
}
```

For a **modification** of an existing endpoint, prefer the lean delta form:

```json
{
  "ticket": "GAMAPASS-3327",
  "method": "POST",
  "path": "/v1/registration/status",
  "note": "Existing API — this ticket only adds the response fields below; all current fields are unchanged.",
  "changes": [
    { "field": "hasPasskey", "type": "boolean", "kind": "added", "desc": "whether the user has at least one passkey registered" },
    { "field": "passkeyPriorityEnabled", "type": "boolean", "kind": "added", "desc": "whether the user has enabled passkey priority" }
  ]
}
```

which renders `changes` as a code block:

```json
{
  "hasPasskey": false,             // added: whether the user has at least one passkey registered
  "passkeyPriorityEnabled": false  // added: whether the user has enabled passkey priority
}
```

- Omit `request` (or any of its sub-keys) when not applicable.
- `responseBody` and `body` are **raw JSON strings** (escaped), rendered as
  `json` code blocks — not nested objects.
- `auth.value` for protected endpoints is typically `Required` with a note like
  `(Bearer token in Authorization header)`.

## Common Mistakes

- **Inventing fields.** If the user didn't specify the response shape or status
  codes, ask. The spec must reflect the real contract.
- **Passing `responseBody` as a JSON object** instead of a string — the script
  expects a raw string so it renders verbatim in a code block.
- **Skipping the dry-run** before overwriting a ticket description.
- **Using a hyphen `-` instead of em dash `—`** in descriptions — breaks format consistency.
