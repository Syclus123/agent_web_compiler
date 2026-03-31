# Benchmark Fixtures

Each fixture consists of a pair of files:

- **`<name>.html`** — A realistic HTML page (200-500 lines) with both content and noise.
- **`<name>.json`** — A spec describing the expected outputs for evaluation.

## JSON Spec Format

```json
{
  "name": "fixture_name",
  "description": "What this fixture tests",
  "source_type": "html",
  "html_file": "fixture_name.html",
  "expected": {
    "headings": ["Expected", "Heading", "Texts"],
    "min_blocks": 5,
    "min_tables": 0,
    "min_code_blocks": 0,
    "key_phrases": ["important text that must be preserved"],
    "expected_actions": [
      {"type": "navigate", "label_contains": "Home"}
    ],
    "noise_phrases": ["cookie", "subscribe"],
    "main_action_label": "Search"
  }
}
```

## Fixtures

| Fixture | Description |
|---------|-------------|
| `blog_article` | Blog post with header, footer, sidebar, article, and code |
| `product_page` | E-commerce product page with specs table, reviews, and actions |
| `docs_page` | Documentation page with navigation, headings, and code samples |
| `search_results` | Search results page with pagination |
| `academic_paper` | Academic paper with abstract, sections, references, and tables |

## Running

```bash
awc bench run --fixtures-dir bench/tasks
```
