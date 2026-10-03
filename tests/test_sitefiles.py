"""Saving a site's baseline/target keeps the previous copy and creates the site folder."""

from cage_vision.sitefiles import write_keeping_previous


def test_first_write_creates_folder_and_no_backup(tmp_path):
    p = write_keeping_previous(tmp_path / "sites" / "newsite" / "cage_target.json", "A")
    assert p.read_text(encoding="utf-8") == "A"
    assert not (p.parent / "backups").exists()


def test_overwrite_keeps_previous_copy(tmp_path):
    target = tmp_path / "baseline.json"
    write_keeping_previous(target, "old")
    write_keeping_previous(target, "new")
    assert target.read_text(encoding="utf-8") == "new"
    kept = list((tmp_path / "backups").glob("baseline_*.json"))
    assert len(kept) == 1 and kept[0].read_text(encoding="utf-8") == "old"
