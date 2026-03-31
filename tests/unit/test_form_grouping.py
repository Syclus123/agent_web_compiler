"""Tests for form field grouping in ActionExtractor."""

from __future__ import annotations

import pytest

from agent_web_compiler.core.action import ActionType
from agent_web_compiler.core.config import CompileConfig
from agent_web_compiler.extractors.action_extractor import ActionExtractor


@pytest.fixture
def extractor() -> ActionExtractor:
    return ActionExtractor()


@pytest.fixture
def config() -> CompileConfig:
    return CompileConfig()


class TestFormFieldGrouping:
    """Tests for the form grouping post-processing step."""

    def test_search_form_grouped_into_single_submit(self, extractor, config):
        """A search form with text input + submit should become one composite action."""
        html = """<html><body>
            <form id="search-form" action="/search">
                <input type="text" name="q" placeholder="Search..." />
                <input type="submit" value="Search" />
            </form>
        </body></html>"""
        actions = extractor.extract(html, config)
        # Should have one composite SUBMIT action, no standalone INPUT
        submits = [a for a in actions if a.type == ActionType.SUBMIT]
        inputs = [a for a in actions if a.type == ActionType.INPUT]
        assert len(submits) == 1
        assert len(inputs) == 0
        submit = submits[0]
        assert submit.label == "Search"
        assert submit.group == "form"
        assert "q" in submit.required_fields
        assert submit.value_schema is not None
        assert submit.value_schema["q"] == "text"

    def test_login_form_grouped(self, extractor, config):
        """A login form with username + password + submit should become one action."""
        html = """<html><body>
            <form id="login-form" action="/login">
                <input type="text" name="username" placeholder="Username" />
                <input type="password" name="password" placeholder="Password" />
                <input type="submit" value="Log In" />
            </form>
        </body></html>"""
        actions = extractor.extract(html, config)
        submits = [a for a in actions if a.type == ActionType.SUBMIT]
        inputs = [a for a in actions if a.type == ActionType.INPUT]
        assert len(submits) == 1
        assert len(inputs) == 0
        submit = submits[0]
        assert submit.role == "login"
        assert "username" in submit.required_fields
        assert "password" in submit.required_fields
        assert submit.value_schema is not None
        assert submit.value_schema["username"] == "text"
        assert submit.value_schema["password"] == "password"

    def test_standalone_input_kept(self, extractor, config):
        """An input not inside any form should remain as a standalone action."""
        html = """<html><body>
            <input type="text" name="standalone" placeholder="Standalone field" />
        </body></html>"""
        actions = extractor.extract(html, config)
        inputs = [a for a in actions if a.type == ActionType.INPUT]
        assert len(inputs) == 1
        assert inputs[0].label == "Standalone field"

    def test_form_without_submit_keeps_individual_actions(self, extractor, config):
        """A form without a submit button should keep individual input actions."""
        html = """<html><body>
            <form id="no-submit">
                <input type="text" name="field1" placeholder="Field 1" />
                <input type="text" name="field2" placeholder="Field 2" />
            </form>
        </body></html>"""
        actions = extractor.extract(html, config)
        inputs = [a for a in actions if a.type == ActionType.INPUT]
        assert len(inputs) == 2

    def test_link_inside_form_kept(self, extractor, config):
        """Navigate actions inside forms should be kept (not merged)."""
        html = """<html><body>
            <form id="myform" action="/submit">
                <input type="text" name="q" placeholder="Search" />
                <a href="/help">Help</a>
                <input type="submit" value="Go" />
            </form>
        </body></html>"""
        actions = extractor.extract(html, config)
        navigates = [a for a in actions if a.type == ActionType.NAVIGATE]
        assert len(navigates) == 1
        assert navigates[0].label == "Help"

    def test_composite_action_has_form_selector(self, extractor, config):
        """The composite action's selector should point to the form element."""
        html = """<html><body>
            <form id="myform" action="/go">
                <input type="text" name="q" placeholder="Query" />
                <input type="submit" value="Submit" />
            </form>
        </body></html>"""
        actions = extractor.extract(html, config)
        submits = [a for a in actions if a.type == ActionType.SUBMIT]
        assert len(submits) == 1
        assert submits[0].selector == "#myform"

    def test_composite_priority_is_max(self, extractor, config):
        """The composite action should use the max priority of its controls."""
        html = """<html><body>
            <form id="f1">
                <input type="text" name="q" placeholder="Search" />
                <input type="submit" value="Go" />
            </form>
        </body></html>"""
        actions = extractor.extract(html, config)
        submits = [a for a in actions if a.type == ActionType.SUBMIT]
        assert len(submits) == 1
        # Submit has priority 0.9, input has 0.6 — max should be 0.9
        assert submits[0].priority == 0.9

    def test_composite_confidence_is_max(self, extractor, config):
        """The composite action should use the max confidence of its controls."""
        html = """<html><body>
            <form id="f1">
                <input type="text" aria-label="Search query" name="q" />
                <input type="submit" value="Go" />
            </form>
        </body></html>"""
        actions = extractor.extract(html, config)
        submits = [a for a in actions if a.type == ActionType.SUBMIT]
        assert len(submits) == 1
        # aria-label gives 0.9 confidence
        assert submits[0].confidence >= 0.9

    def test_select_in_form_merged(self, extractor, config):
        """Select elements in a form with submit should be merged."""
        html = """<html><body>
            <form id="filter-form">
                <select name="category" title="Category">
                    <option>All</option><option>Books</option>
                </select>
                <input type="submit" value="Filter" />
            </form>
        </body></html>"""
        actions = extractor.extract(html, config)
        selects = [a for a in actions if a.type == ActionType.SELECT]
        submits = [a for a in actions if a.type == ActionType.SUBMIT]
        assert len(selects) == 0
        assert len(submits) == 1
        assert "category" in submits[0].required_fields
        assert submits[0].value_schema["category"] == "select"

    def test_multiple_forms_grouped_independently(self, extractor, config):
        """Two separate forms should produce two composite actions."""
        html = """<html><body>
            <form id="form1">
                <input type="text" name="q" placeholder="Search" />
                <input type="submit" value="Search" />
            </form>
            <form id="form2" action="/login">
                <input type="text" name="user" placeholder="Username" />
                <input type="password" name="pass" placeholder="Password" />
                <input type="submit" value="Login" />
            </form>
        </body></html>"""
        actions = extractor.extract(html, config)
        submits = [a for a in actions if a.type == ActionType.SUBMIT]
        assert len(submits) == 2
        labels = {s.label for s in submits}
        assert "Search" in labels
        assert "Login" in labels

    def test_provenance_on_composite_action(self, extractor, config):
        """Composite action should have provenance pointing to the form."""
        config_with_prov = CompileConfig(include_provenance=True)
        html = """<html><body>
            <form id="prov-form">
                <input type="text" name="q" placeholder="Query" />
                <input type="submit" value="Go" />
            </form>
        </body></html>"""
        actions = extractor.extract(html, config_with_prov)
        submits = [a for a in actions if a.type == ActionType.SUBMIT]
        assert len(submits) == 1
        assert submits[0].provenance is not None
        assert submits[0].provenance.dom is not None
        assert submits[0].provenance.dom.element_tag == "form"

    def test_button_in_form_triggers_grouping(self, extractor, config):
        """A <button> (CLICK type) inside a form should also trigger grouping."""
        html = """<html><body>
            <form id="btn-form">
                <input type="text" name="q" placeholder="Search" />
                <button type="submit">Go</button>
            </form>
        </body></html>"""
        actions = extractor.extract(html, config)
        # The button is CLICK type, which triggers grouping
        # The input should be merged; result should have one composite SUBMIT
        submits = [a for a in actions if a.type == ActionType.SUBMIT]
        inputs = [a for a in actions if a.type == ActionType.INPUT]
        assert len(submits) == 1
        assert len(inputs) == 0
        assert "q" in submits[0].required_fields
