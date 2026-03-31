# agent.json Specification (Draft v0.1.0)

> A proposed standard for agent-readable web content metadata.

## Overview

`agent.json` is a machine-readable manifest that declares what an agent can **see** and **do** on a website. It sits alongside existing standards:

| Standard | Audience | Purpose |
|---|---|---|
| `robots.txt` | Crawlers | What to index |
| `sitemap.xml` | Search engines | Page discovery |
| `llms.txt` | Language models | What a site is about |
| **`agent.json`** | **Autonomous agents** | **What an agent can do** |

While `robots.txt` controls access and `llms.txt` provides context, `agent.json` describes **content structure**, **available actions**, and **navigation paths** — everything an agent needs to interact with a site efficiently.

## File Location

Place `agent.json` at the root of your site:

```
https://example.com/agent.json
```

## Format

```json
{
  "agent_json_version": "0.1.0",
  "site": "example.com",
  "generated_by": "agent-web-compiler/0.3.0",
  "generated_at": "2026-03-31T12:00:00Z",
  "pages": [
    {
      "url": "/products",
      "title": "Products",
      "content": {
        "block_types": {"heading": 5, "paragraph": 12, "table": 1},
        "main_topics": ["pricing", "features", "comparison"],
        "key_entities": ["$99.99", "2026-03-15"]
      },
      "actions": [
        {"type": "submit", "role": "search", "fields": ["q"]},
        {"type": "navigate", "role": "next_page", "target": "/products?page=2"},
        {"type": "click", "role": "add_to_cart", "selector": ".btn-cart"}
      ],
      "navigation": {
        "reachable_pages": ["/products/1", "/products/2", "/cart"]
      }
    }
  ],
  "site_structure": {
    "template_elements": ["header", "footer", "sidebar"],
    "common_actions": ["search", "login", "navigate"]
  }
}
```

## Top-Level Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `agent_json_version` | string | Yes | Spec version (semver). Currently `"0.1.0"`. |
| `site` | string | Yes | Domain or base URL of the site. |
| `generated_by` | string | No | Tool that generated the file. |
| `generated_at` | string | No | ISO 8601 timestamp. |
| `pages` | array | Yes | List of page descriptors. |
| `site_structure` | object | No | Site-level template and action patterns. |

## Page Object

Each entry in `pages` describes one URL.

### `content`

Summarizes what the page contains without reproducing the full content.

| Field | Type | Description |
|---|---|---|
| `block_types` | `{string: int}` | Count of each semantic block type (heading, paragraph, table, code, etc.). |
| `main_topics` | `string[]` | Heading texts or topic labels. |
| `key_entities` | `string[]` | Notable entities: prices, dates, names, identifiers. |

### `actions`

Each action describes something an agent can do on the page.

| Field | Type | Description |
|---|---|---|
| `type` | string | Action type: `click`, `submit`, `navigate`, `input`, `select`, `toggle`, `upload`, `download`. |
| `role` | string | Semantic role: `search`, `login`, `add_to_cart`, `next_page`, etc. |
| `label` | string | Human-readable label. |
| `selector` | string | CSS selector to target the element. |
| `fields` | `string[]` | Required input fields (for forms). |
| `target` | string | Target URL (for navigation actions). |

### `navigation`

| Field | Type | Description |
|---|---|---|
| `reachable_pages` | `string[]` | URLs reachable from this page via actions. |
| `graph` | object | Optional navigation graph (from AWC's nav graph builder). |

## `site_structure`

Describes patterns common across the site.

| Field | Type | Description |
|---|---|---|
| `template_elements` | `string[]` | Common template regions: `header`, `footer`, `sidebar`. |
| `common_actions` | `string[]` | Action roles available across most pages. |

## Generating agent.json

### From a single page

```python
from agent_web_compiler.api.compile import compile_url
from agent_web_compiler.standards.agent_json import generate_agent_json

doc = compile_url("https://example.com/products")
print(generate_agent_json(doc))
```

### From multiple pages (site-level)

```python
from agent_web_compiler.standards.agent_json import generate_agent_json_from_batch

docs = [compile_url(url) for url in urls]
print(generate_agent_json_from_batch(docs, site_url="https://example.com"))
```

### Parsing

```python
from agent_web_compiler.standards.agent_json import parse_agent_json

spec = parse_agent_json(open("agent.json").read())
for page in spec.pages:
    print(page.url, page.content["block_types"])
```

## Design Principles

1. **Declarative, not imperative.** Describe what exists, not how to use it.
2. **Additive evolution.** New fields are optional; old parsers ignore them.
3. **Generated, not hand-written.** Tools like AWC produce agent.json automatically.
4. **Complementary.** Works alongside robots.txt, sitemap.xml, and llms.txt.
5. **Agent-first.** Optimized for autonomous agents, not search engines or humans.

## Versioning

The `agent_json_version` field follows semver:

- **Patch** (0.1.x): Clarifications, no schema changes.
- **Minor** (0.x.0): New optional fields.
- **Major** (x.0.0): Breaking changes (field removal or type changes).

Parsers should ignore unknown fields for forward compatibility.

## Status

This is a **draft specification** (v0.1.0). The format will evolve based on real-world agent usage patterns. Feedback and contributions are welcome.
