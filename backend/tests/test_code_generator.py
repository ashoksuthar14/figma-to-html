"""Tests for the code generator agent: prompt building and response parsing."""

import pytest
from unittest.mock import AsyncMock, patch

from agents.code_generator import (
    CodeGeneratorAgent,
    _build_font_list,
    _extract_html_css,
    _node_to_summary,
    _post_process_css,
    _post_process_html,
)
from schemas.design_spec import (
    Bounds,
    Color,
    DesignNode,
    DesignSpec,
    Fill,
    Layout,
    Metadata,
    Style,
    TextInfo,
    TextSegment,
)
from schemas.layout_plan import LayoutDecision, LayoutPlan, LayoutStrategy


# --- Response parsing tests ---

class TestExtractHtmlCss:
    def test_extract_markdown_blocks(self):
        response = """Here is the code:

```html
<div class="container">
  <h1>Hello</h1>
</div>
```

```css
.container {
  display: flex;
}
```

That's the output."""
        html, css = _extract_html_css(response)
        assert '<div class="container">' in html
        assert "<h1>Hello</h1>" in html
        assert ".container" in css
        assert "display: flex" in css

    def test_extract_with_body_tags(self):
        response = """<body>
<div class="main">Content</div>
</body>"""
        html, css = _extract_html_css(response)
        assert '<div class="main">Content</div>' in html

    def test_extract_style_tags(self):
        response = """<style>
.test { color: red; }
</style>
<div class="test">Hello</div>"""
        html, css = _extract_html_css(response)
        assert ".test" in css
        assert "color: red" in css

    def test_empty_response(self):
        html, css = _extract_html_css("")
        assert html == ""
        assert css == ""

    def test_only_html(self):
        response = """```html
<div>Solo HTML</div>
```"""
        html, css = _extract_html_css(response)
        assert "<div>Solo HTML</div>" in html

    def test_nested_code_blocks(self):
        response = """```html
<div class="outer">
  <div class="inner">
    <p>Nested</p>
  </div>
</div>
```

```css
.outer {
  display: flex;
  flex-direction: column;
}
.inner {
  padding: 16px;
}
```"""
        html, css = _extract_html_css(response)
        assert "outer" in html
        assert "inner" in html
        assert ".outer" in css
        assert ".inner" in css


# --- Post-processing tests ---

class TestPostProcessHtml:
    def test_strips_doctype(self):
        html = '<!DOCTYPE html><html><head><title>Test</title></head><body><div>Content</div></body></html>'
        result = _post_process_html(html)
        assert "<!DOCTYPE" not in result
        assert "<html>" not in result
        assert "<body>" not in result
        assert "<div>Content</div>" in result

    def test_preserves_content(self):
        html = '<div class="container"><p>Hello World</p></div>'
        result = _post_process_html(html)
        assert result == html


class TestPostProcessCss:
    def test_adds_box_sizing_reset(self):
        css = ".container { display: flex; }"
        result = _post_process_css(css)
        assert "box-sizing: border-box" in result
        assert ".container" in result

    def test_preserves_existing_box_sizing(self):
        css = "* { box-sizing: border-box; }\n.container { display: flex; }"
        result = _post_process_css(css)
        # Should not duplicate
        assert result.count("box-sizing") == 1


# --- Node summary tests ---

class TestNodeToSummary:
    def test_basic_node_summary(self):
        node = DesignNode(
            id="1:1",
            name="Header",
            type="FRAME",
            bounds=Bounds(x=0, y=0, width=1440, height=80),
        )
        plan = LayoutPlan()
        plan.set_decision(LayoutDecision(
            node_id="1:1",
            strategy=LayoutStrategy.FLEX,
            flex_direction="row",
        ))
        summary = _node_to_summary(node, plan)
        assert "FRAME" in summary
        assert "Header" in summary
        assert "1:1" in summary
        assert "flex" in summary

    def test_text_node_summary(self):
        node = DesignNode(
            id="1:2",
            name="Title",
            type="TEXT",
            bounds=Bounds(x=10, y=10, width=200, height=30),
            text=TextInfo(
                characters="Welcome to our site",
                segments=[TextSegment(
                    characters="Welcome to our site",
                    font_family="Inter",
                    font_size=24,
                    font_weight=700,
                )],
            ),
        )
        plan = LayoutPlan()
        summary = _node_to_summary(node, plan)
        assert "Welcome to our site" in summary
        assert "Inter" in summary
        assert "24" in summary

    def test_style_summary(self):
        node = DesignNode(
            id="1:3",
            name="Button",
            type="RECTANGLE",
            bounds=Bounds(x=0, y=0, width=120, height=40),
            style=Style(
                fills=[Fill(type="SOLID", color=Color(r=0.0, g=0.5, b=1.0))],
                opacity=0.9,
            ),
        )
        plan = LayoutPlan()
        summary = _node_to_summary(node, plan)
        assert "bg:" in summary
        assert "opacity: 0.9" in summary


# --- Font list extraction ---

class TestBuildFontList:
    def test_extract_fonts(self):
        spec = DesignSpec(
            root=DesignNode(
                id="1:1",
                name="Root",
                type="FRAME",
                children=[
                    DesignNode(
                        id="1:2",
                        name="Text1",
                        type="TEXT",
                        text=TextInfo(
                            characters="Hello",
                            segments=[TextSegment(font_family="Inter")],
                        ),
                    ),
                    DesignNode(
                        id="1:3",
                        name="Text2",
                        type="TEXT",
                        text=TextInfo(
                            characters="World",
                            segments=[TextSegment(font_family="Roboto")],
                        ),
                    ),
                ],
            ),
            fonts_used=["Inter"],
        )
        fonts = _build_font_list(spec)
        assert "Inter" in fonts
        assert "Roboto" in fonts


# --- Full agent test with mocked GPT-4 ---

@pytest.mark.asyncio
async def test_code_generator_agent():
    """Test the full agent with a mocked GPT-4 response."""
    gpt_response = """Here is the generated code:

```html
<div class="hero-section">
  <h1 class="hero-title">Welcome</h1>
  <p class="hero-subtitle">Build something great</p>
</div>
```

```css
.hero-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 1440px;
  height: 600px;
  background-color: #ffffff;
}

.hero-title {
  font-family: 'Inter', sans-serif;
  font-size: 48px;
  font-weight: 700;
  color: #1a1a1a;
}

.hero-subtitle {
  font-family: 'Inter', sans-serif;
  font-size: 18px;
  font-weight: 400;
  color: #666666;
  margin-top: 16px;
}
```"""

    spec = DesignSpec(
        root=DesignNode(
            id="1:1",
            name="Hero Section",
            type="FRAME",
            bounds=Bounds(width=1440, height=600),
            layout=Layout(mode="VERTICAL", item_spacing=16),
            children=[
                DesignNode(
                    id="1:2",
                    name="Hero Title",
                    type="TEXT",
                    bounds=Bounds(x=0, y=200, width=400, height=60),
                    text=TextInfo(
                        characters="Welcome",
                        segments=[TextSegment(
                            characters="Welcome",
                            font_family="Inter",
                            font_size=48,
                            font_weight=700,
                        )],
                    ),
                ),
            ],
        ),
    )

    plan = LayoutPlan()
    plan.set_decision(LayoutDecision(
        node_id="1:1",
        strategy=LayoutStrategy.FLEX,
        flex_direction="column",
        justify_content="center",
        align_items="center",
    ))

    agent = CodeGeneratorAgent(job_id="test-gen")

    from services.openai_service import GPTResponse
    with patch("agents.code_generator.call_gpt4", new_callable=AsyncMock) as mock_gpt:
        mock_gpt.return_value = GPTResponse(content=gpt_response, finish_reason="stop")
        result = await agent.execute(design_spec=spec, layout_plan=plan)

    assert "html" in result
    assert "css" in result
    assert "hero-section" in result["html"]
    assert ".hero-section" in result["css"]
    assert "box-sizing" in result["css"]
    # Verify HTML is post-processed (no DOCTYPE)
    assert "<!DOCTYPE" not in result["html"]
