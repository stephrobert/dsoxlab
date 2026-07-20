"""Tests for the guide URL builder.

The learner reads the course on the trainer's site, in a real browser tab, so
the visit is counted by the site's own analytics. This module only composes the
URL, and the campaign parameters are what make those visits attributable: a link
clicked from a local interface carries `http://localhost:<port>` as referrer at
best, nothing at all at worst.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from dsoxlab.models.lab import LabDefinition, ValidationConfig
from dsoxlab.models.runtime import RuntimeConfig, RuntimeType
from dsoxlab.services import guide_url


def _lab(lab_id: str = "lineinfile", doc_url: str = "https://example.test/guide/") -> LabDefinition:
    return LabDefinition(
        id=lab_id,
        title=lab_id,
        level="l1",
        skills=["s"],
        runtime=RuntimeConfig(type=RuntimeType.SHELL),
        distros=["alma10"],
        doc_url=doc_url,
        validation=ValidationConfig(),
    )


def _params(url: str) -> dict[str, list[str]]:
    return parse_qs(urlparse(url).query)


def test_campaign_defaults_to_the_lab_id() -> None:
    """This is what tells which lab sends readers to which guide."""
    url = guide_url(_lab())
    assert url is not None

    assert _params(url) == {
        "utm_source": ["dsoxlab"],
        "utm_medium": ["lab"],
        "utm_campaign": ["lineinfile"],
    }


def test_a_lab_without_doc_url_yields_none() -> None:
    """An absent field is the caller's business to report, not ours to raise on."""
    assert guide_url(_lab(doc_url="")) is None


def test_existing_query_parameters_are_kept() -> None:
    url = guide_url(_lab(doc_url="https://example.test/guide/?lang=fr"))
    assert url is not None

    assert _params(url)["lang"] == ["fr"]
    assert _params(url)["utm_source"] == ["dsoxlab"]


def test_anchor_survives_so_a_lab_can_target_a_section() -> None:
    url = guide_url(_lab(doc_url="https://example.test/guide/#handlers"))
    assert url is not None

    assert urlparse(url).fragment == "handlers"
    assert _params(url)["utm_campaign"] == ["lineinfile"]


def test_the_page_itself_is_untouched() -> None:
    """Only the query changes: same scheme, host and path."""
    url = guide_url(_lab(doc_url="https://blog.example.test/docs/ansible/collections/"))
    assert url is not None
    parts = urlparse(url)

    assert (parts.scheme, parts.netloc, parts.path) == (
        "https",
        "blog.example.test",
        "/docs/ansible/collections/",
    )


def test_source_and_medium_can_be_overridden() -> None:
    """A web front-end may want to distinguish itself from the CLI."""
    url = guide_url(_lab(), source="dsoxlab-web", medium="lms")
    assert url is not None

    assert _params(url)["utm_source"] == ["dsoxlab-web"]
    assert _params(url)["utm_medium"] == ["lms"]
