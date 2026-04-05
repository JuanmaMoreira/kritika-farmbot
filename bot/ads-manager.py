import uiautomator2 as u2
import time
import re

GAME_PACKAGE = "com.gamevil.kritikamobile.android.google.global.normal"
DEVICE_ID = "GIGET4NNZ9CIOJKN"
DEBUG = True
KEYWORDS = ["close", "skip", "dismiss", "continue"]


# ----------------------------
# Utils
# ----------------------------

def in_ad(d):
    try:
        pkg = d.app_current()["package"]
        log(f"[CTX] package actual: {pkg}")
        return pkg != GAME_PACKAGE
    except Exception:
        return True

def log(msg, force=False):
    if not DEBUG and not force:
        return

    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def parse_bounds(bounds_str):
    nums = list(map(int, re.findall(r'\d+', bounds_str)))
    if len(nums) != 4:
        return None
    return nums  # x1, y1, x2, y2


def get_center(bounds):
    x1, y1, x2, y2 = bounds
    return (x1 + x2) // 2, (y1 + y2) // 2


# ----------------------------
# Detection
# ----------------------------

def find_close_candidates(d):
    nodes = d.xpath('//*[@content-desc or @text]')
    candidates = []

    for node in nodes.all():
        desc = (node.attrib.get("content-desc") or "").lower()
        text = (node.attrib.get("text") or "").lower()
        combined = desc + " " + text

        if not any(k in combined for k in KEYWORDS):
            continue

        bounds_str = node.attrib.get("bounds")
        if not bounds_str:
            continue

        bounds = parse_bounds(bounds_str)
        if not bounds:
            continue

        cx, cy = get_center(bounds)

        candidates.append({
            "label": combined.strip(),
            "center": (cx, cy),
            "bounds": bounds
        })

    return candidates


# ----------------------------
# Scoring
# ----------------------------

def score_candidate(c, screen_width, screen_height):
    x, y = c["center"]

    # preferimos arriba + derecha
    score = 0
    score += x / screen_width
    score += (1 - y / screen_height)

    return score


# ----------------------------
# Action
# ----------------------------

def try_close_ad(d, screen_width, screen_height):
    candidates = find_close_candidates(d)

    if not candidates:
        log("[AD] No candidates found")
        return False

    log(f"[AD] Candidates: {[c['label'] for c in candidates]}")

    best = max(
        candidates,
        key=lambda c: score_candidate(c, screen_width, screen_height)
    )

    x, y = best["center"]

    log(f"[AD] Clicking: '{best['label']}' @ ({x},{y})")

    d.click(x, y)

    return True


# ----------------------------
# Main test loop
# ----------------------------

def main():
    d = u2.connect(DEVICE_ID)

    info = d.info
    width = info["displayWidth"]
    height = info["displayHeight"]

    print(f"Resolución detectada: {width}x{height}")

    input("Abrí una ad y presioná ENTER para empezar el test...")

    start = time.time()
    timeout = 90  # segundos

    log("Iniciando loop de ads", force=True)

    while time.time() - start < timeout:

        if not in_ad(d):
            log("[AD] Salimos de contexto de ad → fin del loop", force=True)
            break

        success = try_close_ad(d, width, height)

        if success:
            time.sleep(2)
        else:
            time.sleep(1)

    log("Fin del test", force=True)


if __name__ == "__main__":
    main()