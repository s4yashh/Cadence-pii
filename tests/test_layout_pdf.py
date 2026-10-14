"""Scanned-PDF visual draft keeps page geometry and discards original image objects."""
from cadence_pii.layout_pdf import redact_scanned_pdf_for_review
from cadence_pii.models import FileResult, Status


def test_visual_pdf_rebuilds_page_with_painted_raster(make_scanned_pdf, tmp_path):
    import pymupdf

    source = make_scanned_pdf(["Contact: mira@example.com"])
    result = FileResult(filename=source.name, status=Status.REVIEW_REQUIRED)
    target = tmp_path / "visual_review.pdf"
    stats = redact_scanned_pdf_for_review(source, result, target)
    with pymupdf.open(source) as original, pymupdf.open(target) as review:
        assert len(original) == len(review) == 1
        assert original[0].rect == review[0].rect
        assert not review[0].get_text().strip()  # no hidden source text layer
        assert len(review[0].get_images()) == 1
    assert stats["pages"] == 1
    assert stats["painted_regions"] >= 1
