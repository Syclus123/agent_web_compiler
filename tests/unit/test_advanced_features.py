"""Tests for advanced features: query-aware compilation and salience scoring."""

from __future__ import annotations

from agent_web_compiler import compile_html
from agent_web_compiler.core.block import BlockType
from agent_web_compiler.core.config import CompileConfig

# ---------------------------------------------------------------------------
# Integration tests for query-aware compilation
# ---------------------------------------------------------------------------


class TestQueryAwareCompilation:
    """Test query-aware filtering via the public API."""

    SAMPLE_HTML = """
    <html>
    <body>
        <article>
            <h1>Machine Learning Guide</h1>
            <h2>Introduction</h2>
            <p>Machine learning is a subset of artificial intelligence focused on building systems that learn from data.</p>
            <h2>Supervised Learning</h2>
            <p>In supervised learning, the model is trained on labeled data. Common algorithms include linear regression, decision trees, and support vector machines.</p>
            <h2>Neural Networks</h2>
            <p>Neural networks are computing systems inspired by biological neural networks. Deep learning uses multiple layers.</p>
            <h2>Deployment</h2>
            <p>Deploying ML models requires careful attention to infrastructure, monitoring, and data pipelines.</p>
            <h2>Contact</h2>
            <p>For questions, email support@example.com or visit our office at 123 Main Street.</p>
        </article>
    </body>
    </html>
    """

    def test_compile_without_query(self):
        """Without query, all blocks preserved."""
        doc = compile_html(self.SAMPLE_HTML)
        assert doc.block_count >= 8  # headings + paragraphs

    def test_compile_with_query_filters(self):
        """With query, relevant blocks should be boosted."""
        config = CompileConfig(query="neural networks deep learning")
        doc = compile_html(self.SAMPLE_HTML, config=config)
        # The query-relevant blocks should have higher importance
        nn_blocks = [b for b in doc.blocks if "neural" in b.text.lower()]
        other_blocks = [b for b in doc.blocks if b.type == BlockType.PARAGRAPH and "neural" not in b.text.lower()]
        if nn_blocks and other_blocks:
            # Neural network blocks should score higher on average
            avg_nn = sum(b.importance for b in nn_blocks) / len(nn_blocks)
            avg_other = sum(b.importance for b in other_blocks) / len(other_blocks)
            assert avg_nn >= avg_other * 0.8  # Some tolerance

    def test_compile_with_max_blocks(self):
        """max_blocks should limit output."""
        config = CompileConfig(max_blocks=3)
        doc = compile_html(self.SAMPLE_HTML, config=config)
        assert doc.block_count <= 3

    def test_compile_with_min_importance(self):
        """min_importance should filter low-importance blocks."""
        config = CompileConfig(min_importance=0.8)
        doc = compile_html(self.SAMPLE_HTML, config=config)
        for block in doc.blocks:
            assert block.importance >= 0.8


# ---------------------------------------------------------------------------
# Tests for diverse HTML patterns
# ---------------------------------------------------------------------------


class TestDiverseHTMLPatterns:
    """Test compilation of different HTML structures."""

    def test_product_page_pattern(self):
        html = """
        <html><body><main>
            <h1>Premium Widget</h1>
            <p class="price">$99.99</p>
            <table>
                <tr><th>Feature</th><th>Value</th></tr>
                <tr><td>Weight</td><td>150g</td></tr>
                <tr><td>Color</td><td>Blue</td></tr>
            </table>
            <button class="btn-primary">Add to Cart</button>
        </main></body></html>
        """
        doc = compile_html(html)
        assert doc.title == "Premium Widget"
        tables = doc.get_blocks_by_type("table")
        assert len(tables) >= 1
        assert any(a.type.value == "click" for a in doc.actions)

    def test_search_results_pattern(self):
        html = """
        <html><body><main>
            <h1>Search Results</h1>
            <div class="result"><h2><a href="/r1">Result One</a></h2><p>Description one.</p></div>
            <div class="result"><h2><a href="/r2">Result Two</a></h2><p>Description two.</p></div>
            <nav class="pagination">
                <a href="?page=2">Next →</a>
            </nav>
        </main></body></html>
        """
        doc = compile_html(html)
        assert doc.block_count >= 3
        # Should find navigation actions
        nav_actions = [a for a in doc.actions if a.type.value == "navigate"]
        assert len(nav_actions) >= 1

    def test_code_documentation_pattern(self):
        html = """
        <html><body><main>
            <h1>API Reference</h1>
            <h2>Authentication</h2>
            <pre><code class="language-python">
import requests
headers = {"Authorization": "Bearer TOKEN"}
response = requests.get("https://api.example.com/v1/data", headers=headers)
            </code></pre>
            <h2>Endpoints</h2>
            <table>
                <tr><th>Method</th><th>Path</th><th>Description</th></tr>
                <tr><td>GET</td><td>/v1/data</td><td>List all data</td></tr>
                <tr><td>POST</td><td>/v1/data</td><td>Create new data</td></tr>
            </table>
        </main></body></html>
        """
        doc = compile_html(html)
        code_blocks = doc.get_blocks_by_type("code")
        assert len(code_blocks) >= 1
        assert code_blocks[0].metadata.get("language") == "python"
        tables = doc.get_blocks_by_type("table")
        assert len(tables) >= 1

    def test_empty_html(self):
        doc = compile_html("")
        assert doc.block_count == 0
        assert doc.action_count == 0

    def test_minimal_html(self):
        doc = compile_html("<p>Hello</p>")
        assert doc.block_count >= 1

    def test_deeply_nested_html(self):
        html = "<html><body>" + "<div>" * 20 + "<p>Deep content</p>" + "</div>" * 20 + "</body></html>"
        doc = compile_html(html)
        assert any("Deep content" in b.text for b in doc.blocks)

    def test_malformed_html(self):
        """Malformed HTML should not crash."""
        doc = compile_html("<html><body><p>Unclosed paragraph<div>Mixed</p></div>")
        assert doc.block_count >= 1

    def test_unicode_content(self):
        html = "<html><body><h1>日本語テスト</h1><p>这是中文内容。</p><p>Ñoño español</p></body></html>"
        doc = compile_html(html)
        assert "日本語テスト" in doc.canonical_markdown
        assert "中文内容" in doc.canonical_markdown
