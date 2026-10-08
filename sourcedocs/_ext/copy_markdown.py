"""Export resolved documentation as Markdown and expose a whole-page copy button."""

import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from sphinx.application import Sphinx


def export_markdown(app: Sphinx, exception: Optional[Exception]) -> None:
    """Generate Markdown alongside successful HTML builds, including autodoc content."""
    if exception is not None or app.builder.format != "html":
        return
    output = Path(app.outdir) / "_markdown"
    command = [
        sys.executable,
        "-m",
        "sphinx",
        "-b",
        "markdown",
        "-E",
        "-a",
        "-c",
        str(app.confdir),
        "-d",
        str(Path(app.doctreedir) / "markdown"),
        "-D",
        "extensions=sphinx.ext.autodoc,sphinx.ext.napoleon,sphinx_markdown_builder",
    ]
    if app.warningiserror:
        command.append("-W")
    subprocess.run([*command, str(app.srcdir), str(output)], check=True)


def page_context(app: Sphinx, pagename: str, templatename: str, context: Dict[str, Any], doctree: Any) -> None:
    """Only offer Markdown copying on pages backed by a documentation source."""
    if app.builder.format == "html" and doctree is not None:
        context["markdown_page"] = f"_markdown/{pagename}.md"


def setup(app: Sphinx) -> Dict[str, Any]:
    """Register export and page-context hooks for HTML documentation."""
    app.add_js_file("copy-markdown.js")
    app.connect("html-page-context", page_context)
    app.connect("build-finished", export_markdown)
    return {"version": "1.0", "parallel_read_safe": True, "parallel_write_safe": True}
