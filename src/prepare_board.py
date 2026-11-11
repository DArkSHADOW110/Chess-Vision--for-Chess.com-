"""Crop an explicitly labeled board image; does not infer pieces or game state."""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

NAMES = dict(zip("pnbrqk", ("pawn", "knight", "bishop", "rook", "queen", "king")))


def parse_placement(placement):
    rows = []
    for rank in placement.split("/"):
        row = []
        for token in rank:
            if token in "12345678":
                row.extend(["empty"] * int(token))
            elif token.lower() in NAMES:
                row.append(("white_" if token.isupper() else "black_") + NAMES[token.lower()])
            else:
                raise ValueError(f"Invalid placement token: {token}")
        if len(row) != 8:
            raise ValueError("Each rank must contain eight squares")
        rows.append(row)
    if len(rows) != 8:
        raise ValueError("Placement must contain eight ranks")
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--box", nargs=4, type=int, required=True, metavar=("LEFT", "TOP", "RIGHT", "BOTTOM"))
    parser.add_argument("--placement", required=True, help="FEN piece placement only; supplied by a human")
    parser.add_argument("--orientation", choices=["white", "black"], default="white")
    parser.add_argument("--output", type=Path, required=True, help="New output folder; refuses to overwrite")
    args = parser.parse_args()
    labels = parse_placement(args.placement)
    source = Image.open(args.image).convert("RGB")
    left, top, right, bottom = args.box
    if not (0 <= left < right <= source.width and 0 <= top < bottom <= source.height):
        parser.error("Board box must be inside the image")
    if right - left != bottom - top:
        parser.error("Board box must be square")
    if args.output.exists():
        parser.error("Output exists; choose a new folder")
    args.output.mkdir(parents=True)
    board = source.crop(args.box)
    board.save(args.output / "board.png")
    preview = Image.new("RGB", (8 * 128, 8 * 150), "#252525")
    draw = ImageDraw.Draw(preview)
    records = []
    size = board.width
    for row in range(8):
        for col in range(8):
            rank_row = row if args.orientation == "white" else 7 - row
            file_col = col if args.orientation == "white" else 7 - col
            square = f"{'abcdefgh'[file_col]}{8-rank_row}"
            label = labels[rank_row][file_col]
            tile = board.crop((round(col*size/8), round(row*size/8), round((col+1)*size/8), round((row+1)*size/8)))
            folder = args.output / "squares" / label
            folder.mkdir(parents=True, exist_ok=True)
            relative = Path("squares") / label / f"{square}.png"
            tile.save(args.output / relative)
            preview.paste(ImageOps.contain(tile, (120, 120)), (col*128+4, row*150))
            draw.text((col*128+3, row*150+121), f"{square}: {label}", fill="white")
            records.append({"square": square, "label": label, "image": relative.as_posix(), "source_group": args.image.stem})
    with (args.output / "labels.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=records[0].keys())
        writer.writeheader()
        writer.writerows(records)
    preview.save(args.output / "contact_sheet.png")
    metadata = {"source": str(args.image.resolve()), "box": args.box, "placement": args.placement, "orientation": args.orientation, "label_source": "human-supplied placement; not model predictions", "split": "unassigned", "counts": dict(Counter(r["label"] for r in records))}
    (args.output / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"Prepared {len(records)} labeled squares in {args.output}")
    print("No model trained. Keep this whole board in one dataset split.")


if __name__ == "__main__":
    main()
