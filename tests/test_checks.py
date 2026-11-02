from pathlib import Path

import pytest
from conftest import single, write_cards

from slides2anki.checks import p_two_sided, p_upper
from slides2anki.prep import prep
from slides2anki.validate import validate
from slides2anki.workspace import Workspace


@pytest.fixture
def ws(workspace: Path) -> Workspace:
    prep(w := Workspace(workspace))
    return w


def messages(ws: Workspace) -> list[str]:
    return [i.message for i in validate(ws).issues]


def test_poisson_binomial() -> None:
    assert p_upper([0.25] * 4, 0) == pytest.approx(1.0)
    assert p_upper([0.25] * 4, 4) == pytest.approx(0.25**4)
    assert p_two_sided([0.5] * 10, 5) == pytest.approx(1.0)


def test_balanced_deck_passes(ws: Workspace) -> None:
    cards = [single(i, "ABCD"[i % 4]) for i in range(12)]
    for i, card in enumerate(cards):
        card["options"][i % 4] = "a slightly longer correct option"
        card["options"][(i + 1) % 4] = "an even much longer distractor option"
    write_cards(ws.root, cards)
    assert messages(ws) == []


def test_answer_position_bias(ws: Workspace) -> None:
    write_cards(ws.root, [single(i, "A") for i in range(12)])
    assert any("A is correct in 12/12" in m for m in messages(ws))


def test_longest_correct_bias(ws: Workspace) -> None:
    cards = [single(i, "ABCD"[i % 4]) for i in range(12)]
    for i, card in enumerate(cards):
        card["options"][i % 4] = "the clearly longest and most detailed option"
    write_cards(ws.root, cards)
    assert any("longest option is correct in 12/12" in m for m in messages(ws))


def test_integrity(ws: Workspace) -> None:
    card = single(1, "B", pages=[9], figure=7)
    write_cards(ws.root, [card, single(1)], source_hash="0" * 16)
    found = " | ".join(messages(ws))
    assert "stale" in found
    assert "id used 2 times" in found
    assert "exceed 4 slides" in found


def test_schema_errors(ws: Workspace) -> None:
    write_cards(ws.root, [single(1, "E"), {"id": "Bad Id", "type": "open", "question": "?"}])
    found = " | ".join(messages(ws))
    assert "cards[0]" in found
    assert "cards[1].id" in found
    assert "cards[1].answer" in found


def test_custom_check(ws: Workspace) -> None:
    (ws.checks / "no_q1.py").write_text(
        "from slides2anki import Issue, check\n"
        "@check('no-q1')\n"
        "def no_q1(ctx):\n"
        "    for cf, card in ctx.cards():\n"
        "        if card.id == 'q1':\n"
        "            yield Issue('q1 is forbidden', cf.label, card.id)\n"
    )
    write_cards(ws.root, [single(1)])
    assert "q1 is forbidden" in messages(ws)


def test_custom_check_survives_reload(ws: Workspace) -> None:
    test_custom_check(ws)
    assert "q1 is forbidden" in messages(ws)
