import re

from cage_vision.markers import write_marker_pdf


def test_marker_pdf_structure(tmp_path, cfg):
    pdf = write_marker_pdf(cfg, tmp_path / "m.pdf").read_bytes()
    assert pdf.startswith(b"%PDF-1.4") and pdf.rstrip().endswith(b"%%EOF")
    assert b"/Count 4" in pdf
    assert len(re.findall(rb"/MediaBox \[0 0 612 792\]", pdf)) == 4   # US letter, one page per marker
    # xref offsets must point at the objects they claim to
    xref = int(pdf[pdf.rindex(b"startxref") + 9:].split()[0])
    entries = pdf[xref:].split(b"\n")[3:3 + 11]
    for n, e in enumerate(entries, start=1):
        off = int(e.split()[0])
        assert pdf[off:].startswith(b"%d 0 obj" % n)
