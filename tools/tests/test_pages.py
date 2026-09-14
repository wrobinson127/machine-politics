"""Tests for the prose-page layer: approval gating, markdown subset,
and validator coverage of pages."""

import html as html_lib
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import config
from tools import build_site as bs
from tools import validate_content as vc


def test_rubric_page_renders_every_authored_field(tmp_path):
    """The rubric page is the load-bearing credibility document, so nothing
    written into rubric.yaml may silently fail to reach it. This caught two
    real regressions: worked_examples and the whole instrument_authorship
    block rendering nowhere, then a later clause dropped by an allowlist of
    key names. Guards against a third."""
    bs.build(tmp_path / "dep", preview=False)
    raw = (tmp_path / "dep" / "rubric.html").read_text(encoding="utf-8")
    # Unescape before comparing. The renderer escapes apostrophes to &#x27;,
    # so a raw-text probe reports a false absence for any sentence containing
    # one, which is most of them.
    page_text = " ".join(html_lib.unescape(raw).split())
    rubric = bs.load_yaml(config.RUBRIC_YAML)

    auth = rubric.get("instrument_authorship") or {}
    assert auth, "fixture expects the authorship rule present"
    for key, value in auth.items():
        if not isinstance(value, str):
            continue
        probe = " ".join(value.split())[:60]
        assert probe in page_text, (
            f"instrument_authorship.{key} never reaches rubric.html"
        )

    for ex in rubric.get("worked_examples") or []:
        assert f'href="state/{ex["state"]}.html"' in raw
        probe = " ".join(str(ex.get("why", "")).split())[:60]
        assert probe in page_text, (
            f"worked example {ex['state']} never reaches rubric.html"
        )


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


def test_md_rejects_unsafe_link_schemes():
    html_out = bs.md_to_html("A [bad](javascript:alert(1)) and a [good](about.html) link.")
    assert "javascript" not in html_out
    assert '<a href="about.html">good</a>' in html_out


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


def test_deploy_never_renders_unapproved_prose(tmp_path, monkeypatch):
    """The gate, tested on the mechanism rather than on today's editorial
    state. This used to assert that the real methodology page was a shell,
    which stopped being true the moment the analyst approved it (2026-08-24)
    and would need rewriting after every future approval. Instead: unapprove a
    copy of the page, point the loader at it, and prove the prose does not
    reach the deploy artifact while the shell's neutrality line still does."""
    # Copy the whole content tree, not just pages/. Everything else that
    # resolves through CONTENT_DIR (tour, endorsements, sponsorships, eras)
    # returns empty when its file is missing, so a partial copy silently
    # builds a degenerate site and makes the unapproved_rendered assertion
    # below vacuous.
    work = tmp_path / "content"
    shutil.copytree(config.CONTENT_DIR, work)
    page = work / "pages" / "methodology.md"
    text = page.read_text(encoding="utf-8")
    assert "approved: true" in text, "fixture expects the live page approved"
    page.write_text(text.replace("approved: true", "approved: false", 1),
                    encoding="utf-8")
    monkeypatch.setattr(config, "CONTENT_DIR", work)

    manifest = bs.build(tmp_path / "dep", preview=False)
    assert manifest["unapproved_rendered"] == 0
    # Guard the vacuity directly: the instrument and tour layers must be
    # present in this build, or the gate assertions below prove nothing.
    kinds = {str(e["kind"]).split(":")[0] for e in manifest["entries"]}
    assert {"tour", "endorsement_instrument", "sponsorship_record"} <= kinds
    meth = (tmp_path / "dep" / "methodology.html").read_text(encoding="utf-8")
    assert "Walker Robinson makes every judgment call" not in meth
    assert "takes no position" in meth


def test_deploy_renders_approved_prose(tmp_path):
    """The other half of the gate: once approved, the prose does ship."""
    manifest = bs.build(tmp_path / "dep", preview=False)
    assert manifest["unapproved_rendered"] == 0
    meth = (tmp_path / "dep" / "methodology.html").read_text(encoding="utf-8")
    assert "Walker Robinson makes every judgment call" in meth
    assert "takes no position" in meth
