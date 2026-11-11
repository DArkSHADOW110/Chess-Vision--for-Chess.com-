"""Same-theme board detection and calibrated template recognition (not a neural model)."""
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import json
import sys

import chess
from PIL import Image, ImageChops, ImageStat

ROOT = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
SYMBOLS = {"pawn": "p", "knight": "n", "bishop": "b", "rook": "r", "queen": "q", "king": "k"}


def pixel_data(image):
    return image.get_flattened_data() if hasattr(image, "get_flattened_data") else image.getdata()


def feature(tile):
    """Ignore colored board/highlight pixels, retaining neutral piece ink."""
    tile = tile.convert("RGB").resize((40, 40), Image.Resampling.BILINEAR)
    values = []
    for index, (r, g, b) in enumerate(pixel_data(tile)):
        x, y = index % 40, index // 40
        coordinate = (x < 7 and y < 15) or (x > 29 and y > 29)
        border = x < 2 or x > 37 or y < 2 or y > 37
        if coordinate or border or max(r, g, b) - min(r, g, b) > 18:
            values.append(0)
        else:
            # Shape + color: dark outlines remain visible, white fills are brighter.
            values.append(95 if (r + g + b) / 3 < 155 else 240)
    out = Image.new("L", (40, 40))
    out.putdata(values)
    return out


def calibrate():
    source = ROOT / "data/processed/starting-position"
    if not source.exists():
        raise FileNotFoundError("The supplied starting-position crops are missing.")
    destination = ROOT / "models/theme"
    destination.mkdir(parents=True, exist_ok=True)
    templates = []
    for path in sorted((source / "squares").glob("*/*.png")):
        label = path.parent.name
        name = f"{label}_{path.stem}.png"
        feature(Image.open(path)).save(destination / name)
        templates.append({"file": name, "label": label})
    board = Image.open(source / "board.png").convert("RGB")
    size = board.width // 8
    colors = []
    for col in (0, 1):
        square = board.crop((col * size, 2 * size, (col + 1) * size, 3 * size))
        colors.append(list(Counter(pixel_data(square)).most_common(1)[0][0]))
    metadata = {"type": "same-theme nearest-template classifier", "neural_training": False,
                "source": "human-labeled starting-position screenshot", "templates": templates, "board_colors": colors}
    (destination / "theme.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


@dataclass
class Recognition:
    board: chess.Board
    confidence: float
    worst_error: float
    uncertain: list
    tiles: dict


class BoardReader:
    def __init__(self):
        path = ROOT / "models/theme/theme.json"
        if not path.exists():
            calibrate()
        self.metadata = json.loads(path.read_text(encoding="utf-8"))
        self.colors = self.metadata["board_colors"]
        self.templates = [(entry["label"], Image.open(path.parent / entry["file"]).copy()) for entry in self.metadata["templates"]]

    def read(self, image, orientation="white"):
        image = image.convert("RGB")
        board = chess.Board(None)
        errors, uncertain, tiles = [], [], {}
        for row in range(8):
            for col in range(8):
                tile = image.crop((round(col*image.width/8), round(row*image.height/8), round((col+1)*image.width/8), round((row+1)*image.height/8)))
                encoded = feature(tile)
                by_class = {}
                for label, template in self.templates:
                    error = ImageStat.Stat(ImageChops.difference(encoded, template)).mean[0] / 255
                    by_class[label] = min(error, by_class.get(label, 1))
                ranked = sorted(by_class.items(), key=lambda item: item[1])
                label, error = ranked[0]
                file = col if orientation == "white" else 7-col
                rank = 7-row if orientation == "white" else row
                square = chess.square(file, rank)
                if label != "empty":
                    color, kind = label.split("_")
                    symbol = SYMBOLS[kind]
                    board.set_piece_at(square, chess.Piece.from_symbol(symbol.upper() if color == "white" else symbol))
                if error > 0.13 or ranked[1][1] - error < 0.007:
                    uncertain.append(chess.square_name(square))
                errors.append(error)
                tiles[square] = tile
        return Recognition(board, 1-sum(errors)/64, max(errors), uncertain, tiles)

    def detect(self, source):
        """Find eight alternating background runs in both axes, then check corners."""
        factor = min(1.0, 1280/source.width)
        image = source.convert("RGB").resize((round(source.width*factor), round(source.height*factor)), Image.Resampling.NEAREST)
        pixels = image.load()

        def kind(pixel):
            for i, color in enumerate(self.colors):
                if max(abs(pixel[j]-color[j]) for j in range(3)) <= 10:
                    return i
            return -1

        def runs(values):
            output = []
            start, old = 0, values[0]
            for i, value in enumerate(values[1:], 1):
                if value != old:
                    output.append((start, i, old))
                    start, old = i, value
            output.append((start, len(values), old))
            return output

        def sequences(line):
            # Browser scaling/antialiasing creates narrow non-background seams.
            line = [run for run in line if not (run[2] == -1 and run[1]-run[0] <= 3)]
            for start in range(len(line)-7):
                group = line[start:start+8]
                widths = [b-a for a, b, _ in group]
                unit = sum(widths)/8
                if unit < 20 or max(abs(w-unit) for w in widths) > max(2, unit*.07):
                    continue
                if any(group[i][2] < 0 or (i and group[i][2] == group[i-1][2]) for i in range(8)):
                    continue
                yield group[0][0], group[-1][1]

        seen = set()
        for y in range(0, image.height, 5):
            for left, right in sequences(runs([kind(pixels[x, y]) for x in range(image.width)])):
                key = (left, right)
                if key in seen:
                    continue
                seen.add(key)
                side = right-left
                for offset in (.94, .07, .87):
                    x = min(image.width-1, round(left + side/8*offset))
                    for top, bottom in sequences(runs([kind(pixels[x, yy]) for yy in range(image.height)])):
                        if abs(bottom-top-side) > 4 or not top <= y < bottom:
                            continue
                        hits = 0
                        for row in range(8):
                            for col in range(8):
                                px = min(image.width-1, round(left+(col+.92)*side/8))
                                py = min(image.height-1, round(top+(row+.06)*(bottom-top)/8))
                                hits += kind(pixels[px, py]) == (row+col) % 2
                        if hits >= 46:
                            return tuple(round(v/factor) for v in (left, top, right, bottom))
        raise ValueError("Board not found. Keep the full green/cream board visible, or use Select board area.")
