"""Regression coverage for complete Sheet footprints on the recorded board."""

from dataclasses import FrozenInstanceError
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from src.task.cubie_wars.vision import (
    blank_board_cells, empty_sheet_cell, grid_points, placement_points,
    sheet_placements,
)


FIXTURES = Path(__file__).parent / 'images' / 'cubie_wars' / 'sheet_geometry'
EXPECTED = json.loads((FIXTURES / 'board_expected.json').read_text(encoding='utf-8'))
GEOMETRY = json.loads((FIXTURES / 'geometry.json').read_text(encoding='utf-8'))
HP_BREAD = next(item['cells'] for item in GEOMETRY['sheets'] if item['name'] == 'HP Bread Sheet')


def board(width=1920):
    image = cv2.imread(str(FIXTURES / 'board.png'))
    return cv2.resize(image, (width, round(width * 9 / 16)))


@pytest.mark.parametrize('width', (1280, 1600, 1920))
def test_real_board_distinguishes_blank_board_from_occupied_sheets(width):
    expected = {tuple(cell) for cell in EXPECTED['blank_cells']}
    actual = blank_board_cells(board(width))
    assert actual == expected
    assert len(actual) == 28
    assert 48 - len(actual) == 20
    # These hold swords, but cannot receive another Sheet over the sword.
    assert {(3, 2), (4, 1), (4, 2), (3, 3), (4, 3), (4, 4)}.isdisjoint(actual)


@pytest.mark.parametrize('width', (1280, 1600, 1920))
def test_hp_bread_fits_are_complete_and_use_half_cell_cursor_centers(width):
    image = board(width)
    plans = sheet_placements(image, HP_BREAD)
    expected_origins = {(fit['rotation'], tuple(fit['top_left']))
                        for fit in EXPECTED['hp_bread_fits']}
    assert len(plans) == 5
    assert {(plan.rotation, plan.origin) for plan in plans} == expected_origins
    blank = blank_board_cells(image)
    for plan in plans:
        assert len(plan.cells) == 6
        assert set(plan.cells) <= blank
        assert all(0 <= col < 8 and 0 <= row < 6 for col, row in plan.cells)
    best = next(plan for plan in plans if plan.rotation == 0 and plan.origin == (1, 3))
    assert best.point == pytest.approx((414 / 1920, 609 / 1080))
    assert best.contacts == 4  # Two top edges and two right edges touch old Sheets.
    assert plans[0] == best
    assert [plan.rotation for plan in plans] == sorted(plan.rotation for plan in plans)


def test_sheet_plans_are_immutable():
    plan = sheet_placements(board(), HP_BREAD)[0]
    with pytest.raises(FrozenInstanceError):
        plan.rotation = 2
    assert isinstance(plan.cells, tuple)
    assert all(isinstance(cell, tuple) for cell in plan.cells)


def test_fallback_sheet_points_exclude_all_existing_sheets_and_rank_contacts():
    image = board()
    points = placement_points(image, sheet=True)
    expected = {((261 + col * 102) / 1920, (201 + row * 102) / 1080)
                for col, row in blank_board_cells(image)}
    assert set(points) == expected
    assert len(points) == 28
    assert (567 / 1920, 405 / 1080) not in points
    occupied = {(col, row) for row in range(6) for col in range(8)} - blank_board_cells(image)
    contact_counts = []
    for x, y in points:
        col, row = round((x * 1920 - 261) / 102), round((y * 1080 - 201) / 102)
        contact_counts.append(sum((col + dx, row + dy) in occupied
                                  for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))))
    assert contact_counts == sorted(contact_counts, reverse=True)


def test_item_branch_still_uses_only_item_free_existing_sheet_cells():
    image = board()
    assert placement_points(image) == [point for point in grid_points() if empty_sheet_cell(image, point)]
    assert set(placement_points(image)).isdisjoint(placement_points(image, sheet=True))


@pytest.mark.parametrize('item', GEOMETRY['sheets'], ids=lambda item: item['name'])
def test_all_twelve_sheet_shapes_enumerate_normalized_rotations_without_duplicates(item):
    # Empty synthetic board isolates shape geometry from image recognition.
    image = np.full((1080, 1920, 3), 75, np.uint8)
    plans = sheet_placements(image, item['cells'])
    seen = set()
    rotations = set()
    for plan in plans:
        assert len(plan.cells) == len(item['cells'])
        assert all(0 <= col < 8 and 0 <= row < 6 for col, row in plan.cells)
        assert plan.contacts == 0  # A standalone fit is allowed for preview verification.
        signature = frozenset(plan.cells)
        assert signature not in seen
        seen.add(signature)
        rotations.add(plan.rotation)
        shape = [tuple(cell) for cell in item['cells']]
        for _ in range(plan.rotation):
            shape = [(-row, col) for col, row in shape]
        left, top = min(col for col, row in shape), min(row for col, row in shape)
        normalized = {(col - left, row - top) for col, row in shape}
        assert {(col - plan.origin[0], row - plan.origin[1]) for col, row in plan.cells} == normalized
    count = len(item['cells'])
    if count == 6:
        assert len(plans) == 58
        assert rotations == {0, 1}
    elif count == 3:
        assert len(plans) == 68
        assert rotations == {0, 1}
    elif count == 2:
        assert len(plans) == 82
        assert rotations == {0, 1}
    elif item['name'] in ('Blazing Flame Sheet', 'Boom Boom Pow Sheet'):
        assert len(plans) == 116
        assert rotations == {0, 1, 2, 3}
    else:
        assert len(plans) == 35
        assert rotations == {0}


def test_six_disconnected_blank_cells_do_not_fit_a_six_cell_sheet():
    image = np.full((1080, 1920, 3), 180, np.uint8)
    cells = {(0, 0), (2, 0), (4, 0), (6, 0), (0, 2), (2, 2)}
    for col, row in cells:
        x, y = 261 + col * 102, 201 + row * 102
        image[y - 31:y + 32, x - 31:x + 32] = 75
    assert blank_board_cells(image) == cells
    assert sheet_placements(image, HP_BREAD) == []


def test_unknown_bright_obstruction_is_blocked_not_used_as_blank_space():
    image = board()
    x, y = 261, 507  # Formerly a blank cell at (0, 3).
    image[y - 35:y + 36, x - 35:x + 36] = 220
    assert (0, 3) not in blank_board_cells(image)
    assert all((0, 3) not in plan.cells for plan in sheet_placements(image, HP_BREAD))


def test_empty_unknown_footprint_has_no_plans():
    assert sheet_placements(board(), ()) == []
