"""Small image checks for the recorded 16:9 Cubie Wars layout (BGR frames)."""

import cv2
import numpy as np
from functools import lru_cache
from pathlib import Path


def crop(frame, region):
    h, w = frame.shape[:2]
    x, y, right, bottom = region
    return frame[round(y * h):round(bottom * h), round(x * w):round(right * w)]


def green_check(frame, x, y):
    hsv = cv2.cvtColor(crop(frame, (x - .015, y - .022, x + .015, y + .022)), cv2.COLOR_BGR2HSV)
    return float(np.mean(cv2.inRange(hsv, (35, 60, 110), (90, 255, 255)) > 0)) > .2


def grid_points():
    # 8 x 6 cells, calibrated against the Store screen, not combat's smaller board.
    return [( (261 + col * 102) / 1920, (201 + row * 102) / 1080)
            for row in range(6) for col in range(8)]


def empty_sheet_cell(frame, point):
    x, y = point
    tile = crop(frame, (x - .017, y - .03, x + .017, y + .03))
    if tile.size == 0:
        return False
    hsv = cv2.cvtColor(tile, cv2.COLOR_BGR2HSV)
    purple = cv2.inRange(hsv, (115, 30, 100), (160, 150, 255)) > 0
    gray = cv2.cvtColor(tile, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 45, 100)
    return np.mean(purple) > .9 and np.mean(edges > 0) < .015


def placement_points(frame, sheet=False):
    points = grid_points()
    free = [p for p in points if empty_sheet_cell(frame, p)]
    if not sheet:
        return free
    # Expansion needs a blank board cell. Try near existing sheets first to
    # preserve a contiguous book, then all remaining cells. Ghosts verify fit.
    return sorted((p for p in points if p not in free),
                  key=lambda p: min(((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2
                                     for q in free), default=0))


def preview_counts(before, held):
    # Include the margin and Storage area: a tall rotated item can have a green
    # cell inside the book but red collision cells beyond the book's border.
    region = (.065, .095, .575, .97)
    old = crop(before, region)
    new = crop(held, region)
    if old.shape != new.shape:
        return 0, 0
    changed = np.max(cv2.absdiff(old, new), axis=2) > 25
    hsv = cv2.cvtColor(new, cv2.COLOR_BGR2HSV)
    green = cv2.inRange(hsv, (55, 35, 100), (95, 150, 255))
    red = cv2.inRange(hsv, (0, 95, 130), (12, 255, 255)) | cv2.inRange(hsv, (160, 95, 130), (179, 255, 255))

    def rectangles(mask):
        mask = (mask.astype(bool) & changed).astype(np.uint8)
        _, _, stats, _ = cv2.connectedComponentsWithStats(mask)
        minimum = max(12, round(held.shape[1] * 18 / 1920))
        return sum(int(area) for x, y, width, height, area in stats[1:]
                   if width >= minimum and height >= minimum and area / (width * height) > .2)

    return rectangles(green), rectangles(red)


def valid_preview(before, held):
    green, red = preview_counts(before, held)
    return green > held.shape[0] * held.shape[1] * .00015 and red == 0


def yellow_button(frame, point):
    x, y = point
    tile = crop(frame, (x - .035, y - .012, x + .035, y + .012))
    hsv = cv2.cvtColor(tile, cv2.COLOR_BGR2HSV)
    return np.mean(cv2.inRange(hsv, (15, 70, 140), (40, 255, 255)) > 0) > .3


def recipe_available(frame, y):
    tile = crop(frame, (.035, y - .028, .079, y + .028))
    hsv = cv2.cvtColor(tile, cv2.COLOR_BGR2HSV)
    return np.mean((hsv[:, :, 2] > 150) & (hsv[:, :, 1] > 45)) > .25


def capacity_tag(frame, point):
    x, y = point
    tile = crop(frame, (x - .008, y - .018, x + .008, y + .018))
    hsv = cv2.cvtColor(tile, cv2.COLOR_BGR2HSV)
    return np.mean(cv2.inRange(hsv, (85, 60, 70), (110, 255, 255)) > 0) > .2


@lru_cache(maxsize=1)
def _check_template():
    path = Path(__file__).resolve().parents[3] / "assets" / "cubie_wars" / "claimed_check.png"
    template = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if template is None:
        raise RuntimeError("Missing Cubie Wars claimed-check asset")
    return template


def white_check(frame, point):
    x, y = point
    tile = crop(frame, (x - .045, y - .055, x + .045, y + .055))
    mask = (np.min(tile, axis=2) > 220).astype(np.uint8) * 255
    template = _check_template()
    # Normalize to the same game UI scale before comparing the opaque tick.
    mask = cv2.resize(mask, (173, 119), interpolation=cv2.INTER_NEAREST)
    for scale in (.85, 1.0, 1.15):
        target = cv2.resize(template, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
        if cv2.minMaxLoc(cv2.matchTemplate(mask, target, cv2.TM_CCOEFF_NORMED))[1] > .72:
            return True
    return False
