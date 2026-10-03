from pathlib import Path

import cv2
import pytest

from src.task.cubie_wars.vision import (
    SheetPlacement, valid_sheet_preview, preview_counts,
)


FIXTURES = Path(__file__).parent / 'images/cubie_wars/thin_preview'
PLAN = SheetPlacement(0, (6, 0), ((6, 0), (7, 0), (6, 1), (7, 1)),
                      (924 / 1920, 252 / 1080), 2)
CURSOR = (948 / 1920, 268 / 1080)


def frames(name='positive', size=(1920, 1080)):
    return [cv2.resize(cv2.imread(str(FIXTURES / f'{name}_{part}_native.png')), size)
            for part in ('before', 'held')]


@pytest.mark.parametrize('size', [(1280, 720), (1920, 1080), (2560, 1440)])
def test_real_occluded_sheet_has_aligned_corners_and_thin_green(size):
    before, held = frames(size=size)
    assert valid_sheet_preview(before, held, PLAN, CURSOR)


def test_real_occluded_sheet_explains_original_detector_failure():
    before, held = frames()
    assert preview_counts(before, held) == (287, 0)
    assert 287 < held.shape[0] * held.shape[1] * .00015


@pytest.mark.parametrize('size', [(1280, 720), (1920, 1080), (2560, 1440)])
def test_real_sheet_held_below_board_is_not_a_legal_preview(size):
    before, held = frames('negative', size)
    assert not valid_sheet_preview(before, held, PLAN, CURSOR)


def test_stale_sheet_frame_has_no_new_evidence():
    _, held = frames()
    assert not valid_sheet_preview(held, held.copy(), PLAN, CURSOR)


def test_wrong_cursor_does_not_match_held_sheet_corners():
    before, held = frames()
    assert not valid_sheet_preview(before, held, PLAN, (CURSOR[0] - 102 / 1920, CURSOR[1]))


def test_orange_corners_alone_do_not_prove_legal_placement():
    before, held = frames()
    hsv = cv2.cvtColor(held, cv2.COLOR_BGR2HSV)
    green = cv2.inRange(hsv, (55, 35, 100), (95, 150, 255)) > 0
    held[green] = before[green]
    assert not valid_sheet_preview(before, held, PLAN, CURSOR)


@pytest.mark.parametrize('size', [(1280, 720), (1920, 1080), (2560, 1440)])
def test_green_sheet_sprite_body_is_not_preview_evidence(size):
    before, held = frames()
    hsv = cv2.cvtColor(held, cv2.COLOR_BGR2HSV)
    orange = cv2.inRange(hsv, (10, 70, 160), (40, 255, 255)) > 0
    body_only = before.copy()
    body_only[orange] = held[orange]
    # Preserve the actual four orange corners, but provide only sprite green.
    body_only[166:370, 846:1050] = (160, 200, 100)
    held = body_only
    before, held = [cv2.resize(frame, size) for frame in (before, held)]
    assert not valid_sheet_preview(before, held, PLAN, CURSOR)


def test_one_cell_green_does_not_prove_whole_sheet():
    before, held = frames()
    hsv = cv2.cvtColor(held, cv2.COLOR_BGR2HSV)
    green = cv2.inRange(hsv, (55, 35, 100), (95, 150, 255)) > 0
    green[:252] = False
    held[green] = before[green]
    assert not valid_sheet_preview(before, held, PLAN, CURSOR)


def test_occupied_planned_cell_rejects_otherwise_aligned_ghost():
    before, held = frames()
    before[170:232, 842:904] = (160, 120, 180)
    assert not valid_sheet_preview(before, held, PLAN, CURSOR)


@pytest.mark.parametrize('size', [(1280, 720), (1920, 1080), (2560, 1440)])
def test_thin_red_collision_in_storage_vetoes_green_and_corners(size):
    before, held = frames()
    # Four pixels wide is deliberately too thin for the generic red detector.
    held[850:890, 700:704] = (30, 30, 220)
    before, held = [cv2.resize(frame, size) for frame in (before, held)]
    assert not valid_sheet_preview(before, held, PLAN, CURSOR)


def test_outside_board_plan_cannot_be_accepted():
    before, held = frames()
    plan = SheetPlacement(0, (7, 0), ((7, 0), (8, 0), (7, 1), (8, 1)), PLAN.point, 2)
    assert not valid_sheet_preview(before, held, plan, CURSOR)


def test_missing_corner_is_not_a_complete_aligned_ghost():
    before, held = frames()
    held[135:185, 820:870] = before[135:185, 820:870]
    assert not valid_sheet_preview(before, held, PLAN, CURSOR)


def test_empty_plan_is_rejected():
    before, held = frames()
    plan = SheetPlacement(0, (6, 0), (), PLAN.point, 2)
    assert not valid_sheet_preview(before, held, plan, CURSOR)
