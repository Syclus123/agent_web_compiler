# Output Schema Reference

This document describes the complete output schema of agent-web-compiler. All types are Pydantic models with explicit versioning.

**Schema version:** `0.1.0`

## AgentDocument

The top-level compiled output object. Every compilation produces exactly one `AgentDocument`.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `schema_version` | `str` | yes | `"0.1.0"` | Schema version for compatibility |
| `doc_id` | `str` | yes | — | Unique identifier (`sha256:<hex>`) |
| `source_type` | `SourceType` | yes | — | Type of source document |
| `source_url` | `str?` | no | `null` | Source URL if fetched from web |
| `source_file` | `str?` | no | `null` | Source file path if read from disk |
| `title` | `str` | yes | `""` | Document title |
| `lang` | `str?` | no | `null` | Detected language code (e.g. `"en"`) |
| `fetched_at` | `datetime` | yes | now (UTC) | When the source was fetched |
| `compiled_at` | `datetime` | yes | now (UTC) | When compilation completed |
| `blocks` | `list[Block]` | yes | `[]` | Semantic content blocks |
| `canonical_markdown` | `str` | yes | `""` | Canonical markdown rendering |
| `actions` | `list[Action]` | yes | `[]` | Interactive affordances |
| `site_profile` | `SiteProfile?` | no | `null` | Site template metadata |
| `quality` | `Quality` | yes | (defaults) | Quality indicators |
| `debug` | `dict` | yes | `{}` | Debug metadata |

### Computed fields

| Field | Type | Description |
|---|---|---|
| `block_count` | `int` | `len(blocks)` |
| `action_count` | `int` | `len(actions)` |

### Methods

| Method | Signature | Description |
|---|---|---|
| `make_doc_id` | `(content: str \| bytes) -> str` | Generate deterministic doc ID |
| `get_blocks_by_type` | `(block_type: str) -> list[Block]` | Filter blocks by type |
| `get_main_content` | `(min_importance: float = 0.3) -> list[Block]` | Blocks above importance threshold |
| `summary_markdown` | `(max_blocks: int = 20) -> str` | Short markdown summary of top blocks |

### SourceType

| Value | Description |
|---|---|
| `html` | HTML webpage |
| `pdf` | Native PDF |
| `docx` | Word document |
| `api` | API response |
| `image_pdf` | Scanned/image PDF (OCR required) |

## Block

A semantic content block — the fundamental unit of compiled content.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `id` | `str` | yes | — | Unique identifier (e.g. `"b_001"`) |
| `type` | `BlockType` | yes | — | Semantic type |
| `text` | `str` | yes | — | Plain text content |
| `html` | `str?` | no | `null` | Original HTML if preserved |
| `section_path` | `list[str]` | yes | `[]` | Heading hierarchy path |
| `order` | `int` | yes | `0` | Position in reading order (0-indexed) |
| `importance` | `float` | yes | `0.5` | Salience score [0.0, 1.0] |
| `level` | `int?` | no | `null` | Heading level (1–6) for heading blocks |
| `metadata` | `dict` | yes | `{}` | Type-specific metadata |
| `provenance` | `Provenance?` | no | `null` | Origin tracking |
| `children` | `list[Block]` | yes | `[]` | Nested blocks (e.g. list items) |

### BlockType

| Value | Description | Example |
|---|---|---|
| `heading` | Section heading | `<h1>`, `<h2>`, etc. |
| `paragraph` | Body text | `<p>` content |
| `list` | Ordered or unordered list | `<ul>`, `<ol>` |
| `table` | Data table | `<table>` with rows/columns |
| `code` | Code block | `<pre><code>` |
| `quote` | Block quotation | `<blockquote>` |
| `figure_caption` | Figure caption | `<figcaption>` |
| `image` | Image reference | `<img>` |
| `product_spec` | Product specification | Spec tables, feature lists |
| `review` | User review | Review cards, ratings |
| `faq` | FAQ entry | Question/answer pairs |
| `form_help` | Form help text | Input labels, instructions |
| `metadata` | Page metadata | `<meta>` tags, structured data |
| `unknown` | Unclassified content | Fallback type |

### Block metadata examples

**Table block:**
```json
{
  "row_count": 5,
  "col_count": 3,
  "headers": ["Name", "Type", "Description"]
}
```

**Code block:**
```json
{
  "language": "python",
  "line_count": 12
}
```

**Heading block:**
```json
{
  "level": 2
}
```

### Importance scoring

The `importance` field is a float from 0.0 to 1.0:

| Range | Meaning | Examples |
|---|---|---|
| 0.8–1.0 | Critical content | Main headings, primary content |
| 0.5–0.8 | Important content | Body paragraphs, data tables |
| 0.3–0.5 | Supporting content | Sidebars, related links |
| 0.0–0.3 | Low value / noise | Boilerplate, footers, cookie notices |

## Action

An interactive affordance — something an agent can do on the page.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `id` | `str` | yes | — | Unique identifier (e.g. `"a_search_submit"`) |
| `type` | `ActionType` | yes | — | Type of interaction |
| `label` | `str` | yes | — | Human-readable label |
| `selector` | `str?` | no | `null` | CSS selector to target the element |
| `role` | `str?` | no | `null` | Semantic role |
| `value_schema` | `dict?` | no | `null` | Expected value schema for inputs |
| `required_fields` | `list[str]` | yes | `[]` | Required fields for form actions |
| `confidence` | `float` | yes | `0.5` | Identification confidence [0.0, 1.0] |
| `priority` | `float` | yes | `0.5` | Estimated importance [0.0, 1.0] |
| `state_effect` | `StateEffect?` | no | `null` | Predicted side effects |
| `provenance` | `Provenance?` | no | `null` | Origin tracking |
| `group` | `str?` | no | `null` | Action group |

### ActionType

| Value | Description |
|---|---|
| `click` | Clickable button or element |
| `input` | Text input field |
| `select` | Dropdown or select element |
| `toggle` | Checkbox, radio, or toggle switch |
| `upload` | File upload control |
| `download` | Download trigger |
| `navigate` | Link navigation |
| `submit` | Form submission |

### StateEffect

Predicted side effects of executing an action.

| Field | Type | Default | Description |
|---|---|---|---|
| `may_navigate` | `bool` | `false` | May cause page navigation |
| `may_open_modal` | `bool` | `false` | May open a modal or dialog |
| `may_download` | `bool` | `false` | May trigger a file download |
| `target_url` | `str?` | `null` | Target URL if known |

### Action groups

Actions are grouped by function:

| Group | Description |
|---|---|
| `navigation` | Page navigation links |
| `search` | Search inputs and buttons |
| `form` | Data entry forms |
| `auth` | Login, signup, logout |
| `commerce` | Add to cart, checkout |
| `social` | Share, like, follow |
| `media` | Play, pause, volume |

## Provenance

Links a compiled artifact (block or action) back to its original source location.

| Field | Type | Description |
|---|---|---|
| `dom` | `DOMProvenance?` | DOM tree origin |
| `page` | `PageProvenance?` | Page/viewport origin |
| `screenshot` | `ScreenshotProvenance?` | Screenshot region origin |
| `source_url` | `str?` | URL of the source document |
| `raw_html` | `str?` | Original raw HTML snippet (debug only) |

### DOMProvenance

| Field | Type | Description |
|---|---|---|
| `dom_path` | `str` | CSS-style path (e.g. `"html>body>main>article>p:nth-child(3)"`) |
| `element_tag` | `str?` | HTML tag name (e.g. `"p"`, `"h2"`, `"button"`) |
| `element_id` | `str?` | HTML `id` attribute |
| `element_classes` | `list[str]` | HTML class list |

### PageProvenance

| Field | Type | Description |
|---|---|---|
| `page` | `int?` | Page number (1-indexed, for PDFs) |
| `bbox` | `list[float]?` | Bounding box `[x1, y1, x2, y2]` in page coordinates |
| `char_range` | `list[int]?` | Character offset range `[start, end]` in source text |

### ScreenshotProvenance

| Field | Type | Description |
|---|---|---|
| `screenshot_region_id` | `str?` | Region identifier |
| `screenshot_bbox` | `list[float]?` | Bounding box `[x1, y1, x2, y2]` in pixel coordinates |

## Quality

Quality indicators for the compilation.

| Field | Type | Default | Description |
|---|---|---|---|
| `parse_confidence` | `float` | `1.0` | Overall confidence [0.0, 1.0] |
| `ocr_used` | `bool` | `false` | Whether OCR was needed |
| `dynamic_rendered` | `bool` | `false` | Whether browser rendering was used |
| `block_count` | `int` | `0` | Total blocks extracted |
| `action_count` | `int` | `0` | Total actions extracted |
| `warnings` | `list[str]` | `[]` | Machine-readable warning messages |

### Warning messages

Warnings are short, machine-readable strings:

| Warning | Meaning |
|---|---|
| `table_parse_degraded` | Table extraction was lossy |
| `ocr_low_confidence` | OCR confidence below threshold |
| `dynamic_content_detected` | Page likely has JS-rendered content |
| `boilerplate_dominant` | Most content appears to be boilerplate |
| `encoding_repaired` | Character encoding was auto-repaired |
| `empty_main_content` | No meaningful content blocks found |

## SiteProfile

Site-level template metadata for boilerplate detection.

| Field | Type | Description |
|---|---|---|
| `site` | `str` | Domain name |
| `template_signature` | `str?` | Hash of template structure |
| `header_selectors` | `list[str]` | CSS selectors for header regions |
| `footer_selectors` | `list[str]` | CSS selectors for footer regions |
| `sidebar_selectors` | `list[str]` | CSS selectors for sidebar regions |
| `main_content_selectors` | `list[str]` | CSS selectors for main content |
| `noise_patterns` | `list[str]` | Known noise patterns |

## JSON Examples

### Minimal AgentDocument

```json
{
  "schema_version": "0.1.0",
  "doc_id": "sha256:a1b2c3d4e5f67890",
  "source_type": "html",
  "source_url": "https://example.com",
  "title": "Example Domain",
  "lang": "en",
  "fetched_at": "2026-03-30T12:00:00Z",
  "compiled_at": "2026-03-30T12:00:01Z",
  "blocks": [
    {
      "id": "b_001",
      "type": "heading",
      "text": "Example Domain",
      "section_path": [],
      "order": 0,
      "importance": 0.9,
      "level": 1,
      "metadata": {},
      "provenance": {
        "dom": {
          "dom_path": "html>body>div>h1",
          "element_tag": "h1",
          "element_id": null,
          "element_classes": []
        }
      },
      "children": []
    },
    {
      "id": "b_002",
      "type": "paragraph",
      "text": "This domain is for use in illustrative examples in documents.",
      "section_path": ["Example Domain"],
      "order": 1,
      "importance": 0.7,
      "level": null,
      "metadata": {},
      "provenance": {
        "dom": {
          "dom_path": "html>body>div>p",
          "element_tag": "p",
          "element_id": null,
          "element_classes": []
        }
      },
      "children": []
    }
  ],
  "canonical_markdown": "# Example Domain\n\nThis domain is for use in illustrative examples in documents.",
  "actions": [
    {
      "id": "a_001",
      "type": "navigate",
      "label": "More information...",
      "selector": "a[href='https://www.iana.org/domains/example']",
      "role": "navigate",
      "confidence": 0.95,
      "priority": 0.6,
      "state_effect": {
        "may_navigate": true,
        "may_open_modal": false,
        "may_download": false,
        "target_url": "https://www.iana.org/domains/example"
      },
      "provenance": {
        "dom": {
          "dom_path": "html>body>div>p>a",
          "element_tag": "a",
          "element_id": null,
          "element_classes": []
        }
      },
      "group": "navigation"
    }
  ],
  "quality": {
    "parse_confidence": 0.98,
    "ocr_used": false,
    "dynamic_rendered": false,
    "block_count": 2,
    "action_count": 1,
    "warnings": []
  },
  "block_count": 2,
  "action_count": 1,
  "debug": {}
}
```

### Block with table metadata

```json
{
  "id": "b_015",
  "type": "table",
  "text": "| Name | Type | Default |\n| mode | str | balanced |\n| render | str | off |",
  "section_path": ["Configuration", "Options"],
  "order": 15,
  "importance": 0.75,
  "metadata": {
    "row_count": 3,
    "col_count": 3,
    "headers": ["Name", "Type", "Default"]
  },
  "provenance": {
    "dom": {
      "dom_path": "html>body>main>section:nth-child(2)>table",
      "element_tag": "table",
      "element_id": "config-table",
      "element_classes": ["data-table"]
    },
    "page": {
      "char_range": [1024, 1200]
    }
  },
  "children": []
}
```

### Action with form submission

```json
{
  "id": "a_search_submit",
  "type": "submit",
  "label": "Search",
  "selector": "form#search button[type='submit']",
  "role": "submit_search",
  "value_schema": {
    "type": "object",
    "properties": {
      "q": { "type": "string", "description": "Search query" }
    }
  },
  "required_fields": ["q"],
  "confidence": 0.92,
  "priority": 0.85,
  "state_effect": {
    "may_navigate": true,
    "may_open_modal": false,
    "may_download": false,
    "target_url": null
  },
  "provenance": {
    "dom": {
      "dom_path": "html>body>header>form#search>button",
      "element_tag": "button",
      "element_id": null,
      "element_classes": ["btn", "btn-primary"]
    }
  },
  "group": "search"
}
```

### PDF block with page provenance

```json
{
  "id": "b_042",
  "type": "paragraph",
  "text": "We trained the model on 1.5T tokens using a context window of 128k.",
  "section_path": ["Methods", "Training Setup"],
  "order": 42,
  "importance": 0.8,
  "metadata": {},
  "provenance": {
    "page": {
      "page": 7,
      "bbox": [72.0, 340.5, 540.0, 365.2],
      "char_range": [14200, 14268]
    },
    "source_url": null
  },
  "children": []
}
```

## Schema Versioning

The `schema_version` field follows semantic versioning:

- **Patch** (0.1.0 → 0.1.1): Bug fixes, no field changes
- **Minor** (0.1.0 → 0.2.0): New optional fields added (backward compatible)
- **Major** (0.x → 1.0): Breaking changes to required fields or structure

The current version is `0.1.0` (alpha). The schema will stabilize at `1.0.0`.

**Compatibility rules:**
- New optional fields may be added in minor versions
- Existing fields will not be removed or renamed without a major version bump
- Consumers should ignore unknown fields for forward compatibility
- The `schema_version` field is always present and always the first field
