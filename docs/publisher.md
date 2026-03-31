# Agent Publisher Toolkit

## Overview

The Agent Publisher Toolkit helps website owners generate **agent-friendly files** that declare their content, actions, and navigation to AI agents — shifting from "agents scrape my site" to "I publish for agents."

Think of it as the next step beyond `robots.txt` and `llms.txt`:

| File | What it tells agents |
|------|---------------------|
| `robots.txt` | What you're allowed to crawl |
| `llms.txt` | What this site is about (text overview) |
| **`agent.json`** | What content exists + what actions are possible |
| **`content.json`** | Block-level content feed (structured, not HTML) |
| **`actions.json`** | Interactive capabilities (forms, buttons, downloads) |
| **`agent-sitemap.xml`** | Agent-optimized sitemap with content metadata |
| **`agent-feed.json`** | What changed since your last visit (delta feed) |

## Quick Start

```python
from agent_web_compiler import SitePublisher

publisher = SitePublisher(
    site_name="My Documentation",
    site_url="https://docs.example.com",
    site_description="API documentation for the Example platform",
)

# Option 1: Crawl a site automatically
publisher.crawl_site("https://docs.example.com/", max_pages=50)

# Option 2: Add pre-compiled pages
publisher.add_page(compiled_doc)

# Generate all files
publisher.generate_all("output/agent-publish/")
```

This creates:
```
output/agent-publish/
├── llms.txt
├── agent.json
├── content.json
├── actions.json
├── agent-sitemap.xml
└── agent-feed.json    (if previous snapshot provided)
```

### CLI

```bash
# Crawl a site and generate all agent-friendly files
awc publish site https://docs.example.com/ -o output/ --max-pages 50

# Generate from local files
awc publish files ./docs/*.html -o output/ --site-name "My Docs"

# Preview what a single page would produce
awc publish preview https://example.com/api
```

## Generated Files

### /llms.txt

A concise overview following the [llms.txt](https://llmstxt.org/) convention:

```
# Example Documentation

> API documentation for the Example platform

## Main Sections
- [API Reference](https://docs.example.com/api): REST API endpoints and parameters
- [Authentication](https://docs.example.com/auth): OAuth and API key setup
- [Guides](https://docs.example.com/guides): Step-by-step tutorials

## Capabilities
- Search documentation
- Download API specs
- Navigate between sections

## Key Pages
- [API Reference](https://docs.example.com/api): 42 blocks, 7 actions
- [Authentication](https://docs.example.com/auth): 15 blocks, 3 actions
```

### /agent.json

The central manifest — declares content structure + actions:

```json
{
  "agent_json_version": "0.1.0",
  "site": "docs.example.com",
  "generated_by": "agent-web-compiler/0.7.0",
  "pages": [
    {
      "url": "/api",
      "title": "API Reference",
      "content": {
        "block_types": {"heading": 5, "paragraph": 12, "table": 3, "code": 8},
        "main_topics": ["Authentication", "Endpoints", "Rate Limits"]
      },
      "actions": [
        {"type": "submit", "role": "submit_search", "fields": ["q"]},
        {"type": "navigate", "role": "next_page", "target": "/api?page=2"}
      ]
    }
  ]
}
```

### /content.json

Block-level content feed — agents can consume structured content without parsing HTML:

```json
{
  "version": "0.1.0",
  "pages": [
    {
      "url": "/api",
      "title": "API Reference",
      "blocks": [
        {
          "id": "b_001",
          "type": "heading",
          "text": "Authentication",
          "section_path": ["API Reference", "Authentication"],
          "importance": 0.9
        }
      ]
    }
  ]
}
```

### /actions.json

Capability advertisement — what agents can DO:

```json
{
  "version": "0.1.0",
  "capabilities": ["search", "download", "navigate"],
  "actions": [
    {
      "id": "search_docs",
      "type": "submit",
      "label": "Search Documentation",
      "url": "/api",
      "role": "submit_search",
      "fields": [{"name": "q", "type": "text", "required": true}]
    }
  ]
}
```

### /agent-sitemap.xml

Agent-optimized sitemap with content metadata:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<agent-sitemap xmlns="https://agent-web-compiler.dev/sitemap/0.1">
  <page>
    <url>https://docs.example.com/api</url>
    <title>API Reference</title>
    <blocks>42</blocks>
    <actions>7</actions>
    <content-types>heading,paragraph,table,code</content-types>
    <importance>0.9</importance>
    <last-compiled>2026-03-31T12:00:00Z</last-compiled>
  </page>
</agent-sitemap>
```

### /agent-feed.json

Delta feed — what changed since last visit:

```json
{
  "version": "0.1.0",
  "since": "2026-03-30T00:00:00Z",
  "changes": [
    {
      "url": "/api",
      "change_type": "updated",
      "blocks_added": 3,
      "blocks_removed": 1,
      "summary": "Updated rate limits section"
    }
  ]
}
```

## Integration with agent-web-compiler

The publisher uses the compiler as its **reverse engine**:

```
Existing Website (HTML)
        │
        ▼
  agent-web-compiler (compile)
        │
        ▼
  AgentDocuments (semantic blocks + actions)
        │
        ▼
  Agent Publisher Toolkit (publish)
        │
        ├── /llms.txt
        ├── /agent.json
        ├── /content.json
        ├── /actions.json
        ├── /agent-sitemap.xml
        └── /agent-feed.json
```

Website owners don't need to manually author these files — the compiler auto-generates them from existing content, and publishers can fine-tune before deploying.

## Why This Matters

This shifts the web from **"agents scrape human pages"** to **"websites publish for agents."**

- `robots.txt` told crawlers what NOT to do
- `llms.txt` tells LLMs what a site IS
- **Agent Publisher files tell agents what they CAN DO**

If adopted, this becomes a new web standard — and agent-web-compiler is the reference implementation.
