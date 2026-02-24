"""Tests for the fixer agent: prompt building and CSS extraction."""

import pytest
from unittest.mock import AsyncMock, patch

from agents.fixer import (
    FixerAgent,
    _extract_css_from_response,
)
from schemas.diff_report import DiffRegion, DiffReport, Severity
from services.openai_service import GPTResponse


# --- CSS extraction tests ---

class TestExtractCssFromResponse:
    def test_extract_css_code_block(self):
        response = """Here are the fixes:

```css
.hero-section {
  display: flex;
  width: 1440px;
  height: 600px;
}

.hero-title {
  font-size: 48px;
  color: #1a1a1a;
}
```

These changes should fix the spacing issues."""
        css = _extract_css_from_response(response)
        assert css is not None
        assert ".hero-section" in css
        assert ".hero-title" in css
        assert "display: flex" in css

    def test_extract_generic_code_block(self):
        response = """```
.container {
  padding: 20px;
  margin: 0 auto;
}
```"""
        css = _extract_css_from_response(response)
        assert css is not None
        assert ".container" in css

    def test_extract_inline_css(self):
        response = """.header { background: #fff; }\n.nav { display: flex; }"""
        css = _extract_css_from_response(response)
        assert css is not None
        assert ".header" in css

    def test_no_css_found(self):
        response = "I couldn't determine any CSS changes needed."
        css = _extract_css_from_response(response)
        assert css is None

    def test_empty_response(self):
        css = _extract_css_from_response("")
        assert css is None

    def test_multiple_css_blocks(self):
        response = """Fix 1:
```css
.section-a {
  margin-top: 24px;
}
```

Fix 2 (additional):
```css
.section-b {
  padding: 16px;
}
```"""
        css = _extract_css_from_response(response)
        assert css is not None
        # Should get the first block
        assert ".section-a" in css


# --- Full agent tests with mocked GPT-4 ---

@pytest.mark.asyncio
async def test_fixer_agent_applies_fix():
    """Test that the fixer agent processes a diff report and returns fixed CSS."""
    original_css = """.container {
  display: flex;
  width: 1440px;
  background-color: #ffffff;
}

.header {
  height: 80px;
  padding: 20px;
}"""

    fixed_css_response = """I've analyzed the diff and here are the fixes:

```css
.container {
  display: flex;
  width: 1440px;
  background-color: #f8f8f8;
}

.header {
  height: 80px;
  padding: 20px 40px;
  margin-bottom: 8px;
}
```

The background color was slightly off and the header needed more horizontal padding."""

    html_content = '<div class="container"><header class="header">Hello</header></div>'

    diff_report = DiffReport(
        passed=False,
        pixel_mismatch_percent=3.5,
        ssim_score=0.92,
        regions=[
            DiffRegion(
                x=0, y=0, width=1440, height=80,
                area=200, issue="Header area mismatch",
                severity=Severity.HIGH, mismatch_percent=12.0,
            ),
        ],
    )

    agent = FixerAgent(job_id="test-fix")

    with patch("agents.fixer.call_gpt4", new_callable=AsyncMock) as mock_gpt:
        mock_gpt.return_value = GPTResponse(content=fixed_css_response, finish_reason="stop")
        result = await agent.execute(
            html_content=html_content,
            css_content=original_css,
            diff_report=diff_report,
            iteration=1,
        )

    assert "css" in result
    assert ".container" in result["css"]
    assert "f8f8f8" in result["css"]
    assert "padding: 20px 40px" in result["css"]


@pytest.mark.asyncio
async def test_fixer_agent_handles_failed_extraction():
    """Test that the fixer gracefully handles unextractable responses."""
    agent = FixerAgent(job_id="test-fix-fail")
    original_css = ".test { color: red; }"

    diff_report = DiffReport(
        passed=False,
        pixel_mismatch_percent=2.0,
        ssim_score=0.95,
        regions=[],
    )

    with patch("agents.fixer.call_gpt4", new_callable=AsyncMock) as mock_gpt:
        mock_gpt.return_value = GPTResponse(content="I couldn't determine specific CSS fixes needed.", finish_reason="stop")
        result = await agent.execute(
            html_content="<div>test</div>",
            css_content=original_css,
            diff_report=diff_report,
            iteration=1,
        )

    # Should return original CSS when extraction fails
    assert result["css"] == original_css


@pytest.mark.asyncio
async def test_fixer_agent_tracks_history():
    """Test that the fixer tracks fix iteration history."""
    agent = FixerAgent(job_id="test-fix-history")

    css_response = """```css
.test { color: blue; }
```"""

    diff_report = DiffReport(
        passed=False,
        pixel_mismatch_percent=5.0,
        ssim_score=0.90,
        regions=[
            DiffRegion(
                x=0, y=0, width=100, height=100,
                area=50, issue="Color mismatch",
                severity=Severity.MEDIUM, mismatch_percent=5.0,
            ),
        ],
    )

    with patch("agents.fixer.call_gpt4", new_callable=AsyncMock) as mock_gpt:
        mock_gpt.return_value = GPTResponse(content=css_response, finish_reason="stop")

        # Iteration 1
        await agent.execute(
            html_content="<div>test</div>",
            css_content=".test { color: red; }",
            diff_report=diff_report,
            iteration=1,
        )

        # Iteration 2
        diff_report.pixel_mismatch_percent = 3.0
        await agent.execute(
            html_content="<div>test</div>",
            css_content=".test { color: blue; }",
            diff_report=diff_report,
            iteration=2,
        )

    history = agent.fix_history
    assert len(history) == 2
    assert history[0]["iteration"] == 1
    assert history[0]["mismatch_before"] == 5.0
    assert history[1]["iteration"] == 2
    assert history[1]["mismatch_before"] == 3.0


@pytest.mark.asyncio
async def test_fixer_prompt_includes_scores_and_css():
    """Test that the fixer prompt includes SSIM/mismatch scores and current CSS."""
    agent = FixerAgent(job_id="test-focus")

    diff_report = DiffReport(
        passed=False,
        pixel_mismatch_percent=8.0,
        ssim_score=0.85,
        regions=[
            DiffRegion(
                x=0, y=0, width=200, height=100,
                area=500, issue="Background color wrong",
                severity=Severity.HIGH, mismatch_percent=25.0,
            ),
        ],
    )

    captured_prompt = None

    async def capture_prompt(system_prompt, user_prompt, **kwargs):
        nonlocal captured_prompt
        captured_prompt = user_prompt
        return GPTResponse(content="```css\n.test { color: red; }\n```", finish_reason="stop")

    with patch("agents.fixer.call_gpt4", side_effect=capture_prompt):
        await agent.execute(
            html_content="<div>test</div>",
            css_content=".test { color: blue; }",
            diff_report=diff_report,
            iteration=1,
        )

    assert captured_prompt is not None
    assert "0.8500" in captured_prompt  # SSIM score
    assert "8.00%" in captured_prompt    # Pixel mismatch
    assert ".test { color: blue; }" in captured_prompt  # Current CSS included
