"""Tests for ActionExtractor."""

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


class TestActionExtractor:
    # ---- Button extraction ----

    def test_button_click(self, extractor, config):
        html = '<html><body><button id="btn">Click Me</button></body></html>'
        actions = extractor.extract(html, config)
        assert len(actions) >= 1
        btn = [a for a in actions if a.type == ActionType.CLICK]
        assert len(btn) >= 1
        assert btn[0].label == "Click Me"

    # ---- Link extraction ----

    def test_link_navigate(self, extractor, config):
        html = '<html><body><a href="/about">About Us</a></body></html>'
        actions = extractor.extract(html, config)
        nav = [a for a in actions if a.type == ActionType.NAVIGATE]
        assert len(nav) >= 1
        assert nav[0].label == "About Us"

    def test_link_download(self, extractor, config):
        html = '<html><body><a href="/file.pdf" download>Download PDF</a></body></html>'
        actions = extractor.extract(html, config)
        dl = [a for a in actions if a.type == ActionType.DOWNLOAD]
        assert len(dl) >= 1
        assert dl[0].label == "Download PDF"

    # ---- Input extraction ----

    def test_text_input(self, extractor, config):
        html = '<html><body><input type="text" placeholder="Enter name" /></body></html>'
        actions = extractor.extract(html, config)
        inputs = [a for a in actions if a.type == ActionType.INPUT]
        assert len(inputs) >= 1
        assert inputs[0].label == "Enter name"

    def test_textarea(self, extractor, config):
        html = '<html><body><textarea placeholder="Write here"></textarea></body></html>'
        actions = extractor.extract(html, config)
        inputs = [a for a in actions if a.type == ActionType.INPUT]
        assert len(inputs) >= 1
        assert inputs[0].label == "Write here"

    # ---- Select extraction ----

    def test_select(self, extractor, config):
        html = """<html><body>
            <select title="Choose color">
                <option>Red</option><option>Blue</option>
            </select>
        </body></html>"""
        actions = extractor.extract(html, config)
        selects = [a for a in actions if a.type == ActionType.SELECT]
        assert len(selects) >= 1
        assert selects[0].label == "Choose color"

    # ---- Toggle (checkbox/radio) ----

    def test_checkbox_toggle(self, extractor, config):
        html = '<html><body><input type="checkbox" title="Accept terms" /></body></html>'
        actions = extractor.extract(html, config)
        toggles = [a for a in actions if a.type == ActionType.TOGGLE]
        assert len(toggles) >= 1
        assert "Accept terms" in toggles[0].label

    def test_radio_toggle(self, extractor, config):
        html = '<html><body><input type="radio" title="Option A" /></body></html>'
        actions = extractor.extract(html, config)
        toggles = [a for a in actions if a.type == ActionType.TOGGLE]
        assert len(toggles) >= 1

    # ---- Upload ----

    def test_file_input_upload(self, extractor, config):
        html = '<html><body><input type="file" title="Upload file" /></body></html>'
        actions = extractor.extract(html, config)
        uploads = [a for a in actions if a.type == ActionType.UPLOAD]
        assert len(uploads) >= 1

    # ---- Hidden elements skipped ----

    def test_hidden_elements_skipped(self, extractor, config):
        html = '<html><body><button style="display:none">Hidden</button><button id="visible">Visible</button></body></html>'
        actions = extractor.extract(html, config)
        labels = [a.label for a in actions]
        assert "Hidden" not in labels
        assert "Visible" in labels

    def test_hidden_attribute_skipped(self, extractor, config):
        html = '<html><body><button hidden>Hidden</button><button>Visible</button></body></html>'
        actions = extractor.extract(html, config)
        labels = [a.label for a in actions]
        assert "Hidden" not in labels
        assert "Visible" in labels

    # ---- Empty labels skipped ----

    def test_empty_labels_skipped(self, extractor, config):
        html = '<html><body><button></button><button>Real Button</button></body></html>'
        actions = extractor.extract(html, config)
        assert all(a.label for a in actions)
        labels = [a.label for a in actions]
        assert "Real Button" in labels

    # ---- Label extraction sources ----

    def test_label_from_aria_label(self, extractor, config):
        html = '<html><body><button aria-label="Close dialog">X</button></body></html>'
        actions = extractor.extract(html, config)
        btn = [a for a in actions if a.type == ActionType.CLICK][0]
        assert btn.label == "Close dialog"

    def test_label_from_title(self, extractor, config):
        html = '<html><body><button title="Save document">S</button></body></html>'
        actions = extractor.extract(html, config)
        btn = [a for a in actions if a.type == ActionType.CLICK][0]
        assert btn.label == "Save document"

    def test_label_from_placeholder(self, extractor, config):
        html = '<html><body><input type="text" placeholder="Search..." /></body></html>'
        actions = extractor.extract(html, config)
        inp = [a for a in actions if a.type == ActionType.INPUT][0]
        assert inp.label == "Search..."

    def test_label_from_text_content(self, extractor, config):
        html = '<html><body><button>Submit Form</button></body></html>'
        actions = extractor.extract(html, config)
        btn = [a for a in actions if a.type == ActionType.CLICK][0]
        assert btn.label == "Submit Form"

    # ---- Role inference ----

    def test_search_role(self, extractor, config):
        html = '<html><body><input type="text" name="search" placeholder="Search" /></body></html>'
        actions = extractor.extract(html, config)
        inp = [a for a in actions if a.type == ActionType.INPUT][0]
        assert inp.role is not None
        assert "search" in inp.role.lower()

    def test_login_role(self, extractor, config):
        html = """<html><body>
            <form action="/login">
                <input type="text" name="username" placeholder="Username" />
                <input type="submit" value="Log In" />
            </form>
        </body></html>"""
        actions = extractor.extract(html, config)
        submit = [a for a in actions if a.type == ActionType.SUBMIT]
        assert len(submit) >= 1
        assert submit[0].role == "login"

    def test_pagination_role(self, extractor, config):
        html = '<html><body><a href="/page/2">Next</a></body></html>'
        actions = extractor.extract(html, config)
        nav = [a for a in actions if a.type == ActionType.NAVIGATE]
        assert len(nav) >= 1
        assert nav[0].role == "next_page"

    # ---- Priority scoring ----

    def test_priority_scoring(self, extractor, config):
        html = """<html><body>
            <input type="submit" value="Submit" />
            <a href="/about">About</a>
        </body></html>"""
        actions = extractor.extract(html, config)
        submit = [a for a in actions if a.type == ActionType.SUBMIT][0]
        navigate = [a for a in actions if a.type == ActionType.NAVIGATE][0]
        # Submit should have higher priority than generic navigate
        assert submit.priority > navigate.priority

    # ---- Deduplication ----

    def test_deduplication_by_selector(self, extractor, config):
        html = '<html><body><button id="btn">Click</button><button id="btn">Click</button></body></html>'
        actions = extractor.extract(html, config)
        # Since both have the same id selector, should be deduplicated
        selectors = [a.selector for a in actions]
        assert len(selectors) == len(set(selectors))

    # ---- Sorting ----

    def test_sorted_by_priority_descending(self, extractor, config):
        html = """<html><body>
            <a href="/page">Link</a>
            <input type="submit" value="Submit" />
            <button>Click me</button>
        </body></html>"""
        actions = extractor.extract(html, config)
        priorities = [a.priority for a in actions]
        assert priorities == sorted(priorities, reverse=True)

    # ---- Hidden input type skipped ----

    def test_hidden_input_type_skipped(self, extractor, config):
        html = '<html><body><input type="hidden" name="csrf" value="token123" /></body></html>'
        actions = extractor.extract(html, config)
        assert len(actions) == 0
