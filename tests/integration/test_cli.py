"""I6: the command-line app from arguments to printed answer and exit code."""
import json

from ashaway.cli import EXIT_OK, EXIT_REJECTED, main
from ashaway.risk import DISCLAIMER


def test_I6_assess_prints_a_full_answer_in_words(make_assessor, capsys):
    code = main(["assess", "rhodes", "2023-07-18", "2023-07-24"], assessor=make_assessor())
    out = capsys.readouterr().out
    assert code == EXIT_OK
    for expected in ("Rhodes, 2023-07-18 to 2023-07-24", "HIGH:", "Risk per day", "Main reasons", "[FORECAST]", "[OBSERVATION]", DISCLAIMER):
        assert expected in out


def test_I6_json_output_can_be_parsed(make_assessor, capsys):
    code = main(["assess", "rhodes", "2023-07-18", "2023-07-24", "--json"], assessor=make_assessor())
    result = json.loads(capsys.readouterr().out)
    assert code == EXIT_OK
    assert result["level"] == "high"
    assert result["start"] == "2023-07-18"
    assert result["evidence"][0]["kind"] == "forecast"


def test_I6_unsupported_place_is_refused_with_the_reason(make_assessor, capsys):
    code = main(["assess", "atlantis", "2023-07-18", "2023-07-24"], assessor=make_assessor())
    captured = capsys.readouterr()
    assert code == EXIT_REJECTED
    assert "not a supported destination" in captured.err
    assert "HIGH" not in captured.out and "LOW" not in captured.out


def test_I6_winter_dates_are_refused_with_the_reason(make_assessor, capsys):
    code = main(["assess", "rhodes", "2023-12-01", "2023-12-03"], assessor=make_assessor())
    assert code == EXIT_REJECTED
    assert "May to October" in capsys.readouterr().err


def test_I6_failed_weather_feed_still_answers_honestly(make_assessor, capsys):
    code = main(["assess", "rhodes", "2023-07-18", "2023-07-24"], assessor=make_assessor(down=["weather"]))
    out = capsys.readouterr().out
    assert code == EXIT_OK
    assert "INSUFFICIENT EVIDENCE" in out and "Risk per day" not in out and DISCLAIMER in out


def test_I6_compare_prints_one_row_per_destination(make_assessor, capsys):
    code = main(["compare", "rhodes", "chania", "2023-07-18", "2023-07-24"], assessor=make_assessor())
    out = capsys.readouterr().out
    assert code == EXIT_OK
    assert "Rhodes" in out and "Chania" in out and "Evidence age" in out


def test_I6_compare_refuses_a_single_destination(make_assessor, capsys):
    code = main(["compare", "rhodes", "2023-07-18", "2023-07-24"], assessor=make_assessor())
    assert code == EXIT_REJECTED
    assert "at least two" in capsys.readouterr().err


def test_I6_places_lists_the_supported_destinations(capsys):
    assert main(["places"]) == EXIT_OK
    assert "Rhodes" in capsys.readouterr().out.splitlines()
