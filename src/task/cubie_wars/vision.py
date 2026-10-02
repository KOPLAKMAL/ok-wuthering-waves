"""Small image checks for the recorded 16:9 Cubie Wars layout (BGR frames)."""

import cv2
import numpy as np
from functools import lru_cache
from pathlib import Path


def crop(frame, region):
    h, w = frame.shape[:2]
    x, y, right, bottom = region
    return frame[round(y * h):round(bottom * h), round(x * w):round(right * w)]


def stage_label_frame(frame):
    # Selected labels are brown on pale gold, unlike the white unselected text.
    # Keep three channels because the ONNX detector requires an H x W x 3 input.
    return cv2.cvtColor(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)


def number_frame(frame):
    # A one-pixel crop-width difference made the live 61 x 44 coin crop yield
    # no detection. Actually enlarge small numbers; target_height only scales
    # down in the framework. These OCR callers consume names, not coordinates.
    return cv2.resize(frame, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)


@lru_cache(maxsize=1)
def _thumb_template():
    path = Path(__file__).resolve().parents[3] / 'assets' / 'cubie_wars' / 'recommended_thumb.png'
    template = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if template is None:
        raise RuntimeError('Missing Cubie Wars recommended-thumb asset')
    return template


@lru_cache(maxsize=1)
def _native_thumb_template():
    path = Path(__file__).resolve().parents[3] / 'assets' / 'cubie_wars' / 'recommended_thumb_native.png'
    template = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if template is None:
        raise RuntimeError('Missing Cubie Wars native recommended-thumb asset')
    return template


def recommended_item(frame, point):
    x, y = point
    # Each recommendation thumb sits above the price badge's right edge.
    tile = crop(frame, (x+.023, y-.070, x+.057, y-.020))
    hsv = cv2.cvtColor(tile, cv2.COLOR_BGR2HSV)
    # Native game captures have a smaller, sharper thumb than the recording.
    # Close tiny antialiasing gaps and search sizes, retaining the shape check
    # so the gold price-badge edge is not mistaken for a recommendation.
    # The stricter mask removes the brown outline's antialiasing at 1280px.
    for saturation in (65, 80):
        gold = cv2.inRange(hsv, (15, saturation, 150), (40, 255, 255))
        gold = cv2.resize(gold, (65, 54), interpolation=cv2.INTER_NEAREST)
        gold = cv2.morphologyEx(gold, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
        for reference in (_thumb_template(), _native_thumb_template()):
            for scale in (.65, .7, .75, .8, .85, .9, .95, 1, 1.05, 1.1, 1.15):
                template = cv2.resize(reference, None, fx=scale, fy=scale,
                                      interpolation=cv2.INTER_NEAREST)
                if cv2.minMaxLoc(cv2.matchTemplate(gold, template, cv2.TM_CCOEFF_NORMED))[1] > .78:
                    return True
    return False


def possible_recommendation(frame, point):
    """Recognize an unresolved gold mark so it cannot cause blind rerolls."""
    x, y = point
    tile = crop(frame, (x+.023, y-.070, x+.057, y-.020))
    mask = cv2.inRange(cv2.cvtColor(tile, cv2.COLOR_BGR2HSV), (15, 65, 150), (40, 255, 255))
    mask = cv2.resize(mask, (65, 54), interpolation=cv2.INTER_NEAREST)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    _, _, stats, _ = cv2.connectedComponentsWithStats(mask)
    return any(1 < left and 1 < top and left+width < 64 and top+height < 50
               and 12 <= width <= 40 and 14 <= height <= 40
               and area/(width*height) > .4
               for left, top, width, height, area in stats[1:])


def spotlight_target(frame, anchor):
    """Find the bright rounded yellow tutorial border near its known control."""
    h, w = frame.shape[:2]
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (15, 80, 160), (40, 255, 255))
    candidates = []
    for contour in cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
        x, y, width, height = cv2.boundingRect(contour)
        if not (.035*w < width < .65*w and .025*h < height < .8*h):
            continue
        center = ((x + width/2)/w, (y + height/2)/h)
        if abs(center[0]-anchor[0]) > .06 or abs(center[1]-anchor[1]) > .07:
            continue
        if not (x < anchor[0]*w < x+width and y < anchor[1]*h < y+height):
            continue
        tile = mask[y:y+height, x:x+width] > 0
        bx, by = max(2, round(width*.12)), max(2, round(height*.12))
        # A tutorial frame has continuous yellow on all four edges. Coins,
        # swords, and decorative gold inside a control do not meet this check.
        edges = (tile[:by, bx:-bx].any(axis=0).mean(),
                 tile[-by:, bx:-bx].any(axis=0).mean(),
                 tile[by:-by, :bx].any(axis=1).mean(),
                 tile[by:-by, -bx:].any(axis=1).mean())
        if min(edges) > .7:
            # The speed highlight also encloses Pause. Click the observed
            # control inside the verified border, not the rectangle's center.
            candidates.append((width*height, anchor))
    return max(candidates, default=(0, None))[1]


def green_check(frame, x, y):
    # Stay close to the circular badge so a one-pixel OCR baseline shift does
    # not dilute its green fill with the surrounding purple stage card.
    hsv = cv2.cvtColor(crop(frame, (x - .012, y - .018, x + .012, y + .018)), cv2.COLOR_BGR2HSV)
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
