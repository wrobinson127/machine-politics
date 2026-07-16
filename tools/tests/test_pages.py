"""Tests for the prose-page layer: approval gating, markdown subset,
and validator coverage of pages."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools import build_site as bs
from tools import validate_content as vc


def test_md_subset_renders():
    html_out = bs.md_to_html(
        "## Head\n\nA **bold** [link](about.html) here.\n\n- one\n- two\n\n### Sub\n\nTail."
    )
    assert "<h2>Head</h2>" in html_out
    assert "<strong>bold</strong>" in html_out
    assert '<a href="about.html">link</a>' in html_out
    assert "<ul><li>one</li><li>two</li></ul>" in html_out
    assert "<h3>Sub</h3>" in html_out
    assert "<p>Tail.</p>" in html_out


def test_md_escapes_html_and_strips_comments():
    html_out = bs.md_to_html("Text <script>x</script>\n\n<!-- FLAG: note -->\n\nMore.")
    assert "<script>" not in html_out
    assert "&lt;script&gt;" in html_out
    assert "FLAG" not in html_out


def test_unapproved_page_falls_back_to_shell():
    pages = {"about": {"meta": {"approved": False, "title": "About"}, "body": "Secret draft prose."}}
    manifest = {"entries": []}
    html_out = bs.prose_page("about", pages, ["Shell line."], preview=False, manifest=manifest)
    assert "Secret draft prose" not in html_out
    assert "Shell line." in html_out
    assert manifest["entries"][0]["rendered"] is False


def test_approved_page_renders():
    pages = {"about": {"meta": {"approved": True, "title": "About"}, "body": "Published prose."}}
    manifest = {"entries": []}
    html_out = bs.prose_page("about", pages, ["Shell line."], preview=False, manifest=manifest)
    assert "Published prose." in html_out
    assert "Shell line." not in html_out
    assert manifest["entries"][0]["approved"] is True


def test_preview_page_renders_with_draft_chip():
    pages = {"about": {"meta": {"approved": False, "title": "About"}, "body": "Draft prose."}}
    manifest = {"entries": []}
    html_out = bs.prose_page("about", pages, ["Shell line."], preview=True, manifest=manifest)
    assert "Draft prose." in html_out
    assert "draft-chip" in html_out


def test_validator_rejects_bad_pages(tmp_path):
    pages = tmp_path / "pages"
    pages.mkdir()
    (tmp_path / "sources.yaml").write_text("sources: []\n", encoding="utf-8")
    rubric_src = Path(__file__).resolve().parents[2] / "content" / "rubric.yaml"
    (tmp_path / "rubric.yaml").write_text(rubric_src.read_text(encoding="utf-8"), encoding="utf-8")
    (pages / "bad.md").write_text(
        "---\ntitle: Bad\napproved: false\n---\nThis state has no policy at all.\n",
        encoding="utf-8",
    )
    (pages / "dash.md").write_text(
        "---\ntitle: Dash\napproved: false\n---\nProse with an em dash — right here.\n",
        encoding="utf-8",
    )
    (pages / "nofm.md").write_text("No front matter here.\n", encoding="utf-8")
    errs = vc.validate(tmp_path).items
    assert any("prohibited claim" in e for e in errs)
    assert any("em dash" in e for e in errs)
    assert any("front matter" in e for e in errs)


def test_real_pages_validate_and_render_in_preview(tmp_path):
    errs = vc.validate().items
    assert errs == []
    manifest = bs.build(tmp_path / "prev", preview=True)
    page_entries = [e for e in manifest["entries"] if e["kind"].startswith("page:")]
    assert {e["kind"] for e in page_entries} == {
        "page:methodology", "page:about", "page:corrections",
    }
    meth = (tmp_path / "prev" / "methodology.html").read_text(encoding="utf-8")
    assert "It records who says what." in meth
    about = (tmp_path / "prev" / "about.html").read_text(encoding="utf-8")
    assert "takes no position" in about


def test_deploy_shows_shells_until_approval(tmp_path):
    manifest = bs.build(tmp_path / "dep", preview=False)
    assert manifest["unapproved_rendered"] == 0
    meth = (tmp_path / "dep" / "methodology.html").read_text(encoding="utf-8")
    # the draft prose must not leak; the shell still carries the neutrality line
    assert "Walker Robinson is the analyst of record" not in meth
    assert "takes no position" in meth
