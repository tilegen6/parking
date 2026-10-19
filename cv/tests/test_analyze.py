"""Capture report CLI output, including the nested fields checked by mypy."""

import json

from analyze import _print_report, analyze


def test_empty_report(tmp_path, capsys):
    report = analyze(tmp_path, 10)
    _print_report(report)
    assert report["total_events"] == 0
    assert "Дампов нет" in capsys.readouterr().out


def test_report_fields_duplicates_and_json(tmp_path, capsys):
    for index, second in enumerate([0, 5]):
        capture = tmp_path / str(index)
        capture.mkdir()
        (capture / "summary.json").write_text(
            json.dumps(
                {
                    "plate_number": "123ABC02",
                    "event_time": f"2026-10-20T10:00:{second:02d}+05:00",
                    "direction": "ENTRY",
                    "confidence": 0.95,
                }
            ),
            encoding="utf-8",
        )
    report = analyze(tmp_path, 10)
    _print_report(report)
    output = capsys.readouterr().out
    assert "plate_number   2/2" in output
    assert "123ABC02  +5.0s" in output
    assert report["direction_available"] is True
    assert json.loads(json.dumps(report))["duplicates_found"] == 1
