"""Small image checks for the recorded 16:9 Cubie Wars layout (BGR frames)."""

import cv2
import numpy as np
from dataclasses import dataclass
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


def recommended_event(frame, x):
    # The Event card's upper-right thumb uses the same gold shape as the shop.
    # Translate its observed position into the shop detector's price anchor.
    return recommended_item(frame, (x + .06, .315))


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
        # The shop price line can join the refresh highlight on its left.
        # Recover the actual straight vertical border from that attachment.
        if anchor == (.895, .574):
            coverage = tile[by:-by, :round(width*.3)].mean(axis=0)
            straight = np.flatnonzero(coverage > .85)
            if len(straight):
                tile = tile[:, straight[0]:]
                bx = max(2, round(tile.shape[1]*.12))
        # A tutorial frame has continuous yellow on all four edges. Coins,
        # swords, and decorative gold inside a control do not meet this check.
        edges = (tile[:by, bx:-bx].any(axis=0).mean(),
                 tile[-by:, bx:-bx].any(axis=0).mean(),
                 tile[by:-by, :bx].any(axis=1).mean(),
                 tile[by:-by, -bx:].any(axis=1).mean())
        # Start's frame reaches the bottom of the visible game area. A masked
        # UID or the viewport can cut its bottom edge; require the other three.
        clipped_start = anchor == (.895, .84) and y + height >= .965*h
        required = (edges[0], edges[2], edges[3]) if clipped_start else edges
        if min(required) > .7:
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


def blank_board_cells(frame):
    """Return bare board cells, excluding Sheets even when they hold items.

    Calibrated on clean Store captures. The dark board has median brightness
    below 110; Sheet tiles are brighter. Requiring most of the middle patch to
    remain dark also treats a tooltip or another bright obstruction as blocked.
    Read the baseline before picking an item up, not its occluded drag frame.
    """
    if frame is None or frame.size == 0:
        return set()
    h, w = frame.shape[:2]
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    blank = set()
    for row in range(6):
        for col in range(8):
            center_x = (261 + col * 102) * w / 1920
            center_y = (201 + row * 102) * h / 1080
            left, right = round(center_x - 30 * w / 1920), round(center_x + 30 * w / 1920) + 1
            top, bottom = round(center_y - 30 * h / 1080), round(center_y + 30 * h / 1080) + 1
            tile = hsv[top:bottom, left:right, 2]
            if tile.size and np.median(tile) <= 110 and np.mean(tile > 100) < .5:
                blank.add((col, row))
    return blank


@dataclass(frozen=True)
class SheetPlacement:
    rotation: int
    origin: tuple[int, int]
    cells: tuple[tuple[int, int], ...]
    point: tuple[float, float]
    contacts: int


def _sheet_contacts(cells, occupied):
    return sum((col + dx, row + dy) in occupied
               for col, row in cells
               for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)))


def sheet_placements(frame, footprint):
    """Plan complete Sheet footprints and exact cursor centers for each turn."""
    if not footprint:
        return []
    blank = blank_board_cells(frame)
    occupied = {(col, row) for row in range(6) for col in range(8)} - blank
    shape = tuple((int(col), int(row)) for col, row in footprint)
    orientations = set()
    result = []
    for rotation in range(4):
        min_col = min(col for col, row in shape)
        min_row = min(row for col, row in shape)
        normalized = tuple(sorted({(col - min_col, row - min_row) for col, row in shape}))
        if normalized not in orientations:
            orientations.add(normalized)
            max_col = max(col for col, row in normalized)
            max_row = max(row for col, row in normalized)
            for row in range(6 - max_row):
                for col in range(8 - max_col):
                    cells = tuple((col + dx, row + dy) for dx, dy in normalized)
                    if all(cell in blank for cell in cells):
                        # Shop pickup uses the sprite center, so an even-width
                        # Sheet must be aimed between cells, not at one center.
                        point = ((261 + 102 * (col + max_col / 2)) / 1920,
                                 (201 + 102 * (row + max_row / 2)) / 1080)
                        result.append(SheetPlacement(rotation, (col, row), cells,
                                                     point, _sheet_contacts(cells, occupied)))
        shape = tuple((-row, col) for col, row in shape)
    return sorted(result, key=lambda p: (p.rotation, -p.contacts, p.origin[1], p.origin[0]))


def empty_sheet_cell(frame, point):
    x, y = point
    tile = crop(frame, (x - .017, y - .03, x + .017, y + .03))
    if tile.size == 0:
        return False
    hsv = cv2.cvtColor(tile, cv2.COLOR_BGR2HSV)
    purple = cv2.inRange(hsv, (115, 30, 100), (160, 150, 255)) > 0
    tan = cv2.inRange(hsv, (10, 20, 100), (40, 170, 255)) > 0
    gray = cv2.cvtColor(tile, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 45, 100)
    return np.mean(purple | tan) > .9 and np.mean(edges > 0) < .015


def placement_points(frame, sheet=False):
    points = grid_points()
    free = [p for p in points if empty_sheet_cell(frame, p)]
    if not sheet:
        return free
    # An item-free Sheet cell is still occupied for Sheet expansion. This
    # fallback ranks only truly bare cells; known shapes use sheet_placements.
    blank = blank_board_cells(frame)
    occupied = {(col, row) for row in range(6) for col in range(8)} - blank
    cells = sorted(blank, key=lambda cell: (-_sheet_contacts((cell,), occupied), cell[1], cell[0]))
    return [((261 + col * 102) / 1920, (201 + row * 102) / 1080)
            for col, row in cells]


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


def valid_sheet_preview(before, held, plan, cursor_point):
    """Verify an aligned Sheet ghost whose opaque sprite hides most green.

    The whole footprint must fit the unheld board. Four *new* orange corners
    must follow the commanded cursor, while new green remains in at least two
    planned cells. Orange alone, a stale frame, or a thin red collision is not
    placement evidence. The caller separately verifies held state and stability.
    """
    if (before is None or held is None or before.shape != held.shape
            or not before.size or not plan.cells):
        return False
    cells = set(plan.cells)
    if any(not (0 <= col < 8 and 0 <= row < 6) for col, row in cells):
        return False
    if not cells <= blank_board_cells(before):
        return False
    h, w = held.shape[:2]
    sx, sy = w / 1920, h / 1080
    area_scale = sx * sy
    changed = np.max(cv2.absdiff(before, held), axis=2) > 25
    hsv = cv2.cvtColor(held, cv2.COLOR_BGR2HSV)
    green = (cv2.inRange(hsv, (55, 35, 100), (95, 150, 255)) > 0) & changed
    orange = (cv2.inRange(hsv, (10, 70, 160), (40, 255, 255)) > 0) & changed
    red = ((cv2.inRange(hsv, (0, 95, 130), (12, 255, 255)) > 0)
           | (cv2.inRange(hsv, (160, 95, 130), (179, 255, 255)) > 0)) & changed

    # Include Storage and book margins so a collision outside the board cannot
    # be hidden by green evidence inside it. Preserve thin red strips too.
    _, _, stats, _ = cv2.connectedComponentsWithStats(
        crop(red.astype(np.uint8), (.065, .095, .575, .97)))
    for _, _, width, height, area in stats[1:]:
        axes = (width / sx, height / sy)
        if max(axes) >= 18 and min(axes) >= 2 and area >= 30 * area_scale:
            return False

    def patch(mask, x0, y0, x1, y1):
        left, top, right, bottom = map(round, (x0, y0, x1, y1))
        if left < 0 or top < 0 or right > w or bottom > h:
            return None
        return mask[top:bottom, left:right]

    cols, rows = zip(*cells)
    half_width = 51 * (max(cols) - min(cols) + 1) + 3
    half_height = 51 * (max(rows) - min(rows) + 1) + 3
    cx, cy = cursor_point[0] * w, cursor_point[1] * h
    for dx in (-half_width, half_width):
        for dy in (-half_height, half_height):
            x, y = cx + dx * sx, cy + dy * sy
            corner = patch(orange, x - 23 * sx, y - 23 * sy,
                           x + 23 * sx, y + 23 * sy)
            if corner is None or np.count_nonzero(corner) < 50 * area_scale:
                return False

    # A Rapier Sheet's own sprite is green. Only exposed preview around the
    # sprite proves legality; never use the dragged Sheet's body as evidence.
    # Two native pixels also exclude sprite-color bleed after resizing.
    body_left = max(0, round(cx - (half_width - 1) * sx))
    body_right = min(w, round(cx + (half_width - 1) * sx))
    body_top = max(0, round(cy - (half_height - 1) * sy))
    body_bottom = min(h, round(cy + (half_height - 1) * sy))
    green[body_top:body_bottom, body_left:body_right] = False

    local = np.zeros((h, w), np.uint8)
    green_cells = 0
    for col, row in cells:
        x, y = (261 + col * 102) * sx, (201 + row * 102) * sy
        cell = patch(green, x - 51 * sx, y - 51 * sy,
                     x + 51 * sx, y + 51 * sy)
        if cell is None:
            return False
        if np.count_nonzero(cell) >= 20 * area_scale:
            green_cells += 1
        left, top = round(x - 51 * sx), round(y - 51 * sy)
        local[top:top + cell.shape[0], left:left + cell.shape[1]] = cell
    if (green_cells < min(2, len(cells))
            or np.count_nonzero(local) < 80 * area_scale):
        return False
    _, _, stats, _ = cv2.connectedComponentsWithStats(local)
    return any(max(width / sx, height / sy) >= 35 and area >= 50 * area_scale
               for _, _, width, height, area in stats[1:])


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
