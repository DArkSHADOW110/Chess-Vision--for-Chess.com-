"""Validate complete games from a bounded, deliberately incomplete Zstandard prefix."""
import argparse
import hashlib
import io
import json
import re
from pathlib import Path

import chess.pgn
import chess.svg
import zstandard


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prefix", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--games", type=int, default=50)
    args = parser.parse_args()
    if not 1 <= args.games <= 1000:
        parser.error("Choose 1 to 1000 games")
    if args.output.exists():
        parser.error("Output already exists")
    # Bound both compressed input and decompressed output. This is not a full archive.
    if args.prefix.stat().st_size > 2 * 1024 * 1024:
        parser.error("Prefix exceeds the 2 MiB safety limit")
    chunks = []
    total = 0
    with args.prefix.open("rb") as compressed:
        with zstandard.ZstdDecompressor().stream_reader(compressed) as stream:
            while total < 32 * 1024 * 1024:
                chunk = stream.read(min(65536, 32 * 1024 * 1024 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
    text = b"".join(chunks).decode("utf-8", errors="strict")
    starts = [match.start() for match in re.finditer(r"(?m)^\[Event ", text)]
    # A following Event header is required, so the potentially incomplete last game is dropped.
    games, positions, rejected = [], [], 0
    for start, end in zip(starts, starts[1:]):
        if len(games) >= args.games:
            break
        game = chess.pgn.read_game(io.StringIO(text[start:end]))
        if game is None or game.errors or game.headers.get("Result") not in ("1-0", "0-1", "1/2-1/2"):
            rejected += 1
            continue
        board = game.board()
        moves = list(game.mainline_moves())
        if not moves:
            rejected += 1
            continue
        identity = game.headers.get("Site", "") + str(game)
        group = hashlib.sha256(identity.encode()).hexdigest()[:16]
        bucket = int(group, 16) % 10
        split = "test" if bucket == 0 else "validation" if bucket == 1 else "train"
        selected = set(range(0, len(moves), max(1, len(moves)//10)))
        for ply, move in enumerate(moves):
            if move not in board.legal_moves:
                raise ValueError(f"Illegal move in parsed game {group}, ply {ply}")
            if ply in selected:
                positions.append({"source_game": group, "split": split, "ply": ply, "fen": board.fen(), "played_move_uci": move.uci(), "played_move_san": board.san(move), "target_type": "human played move; not verified best move"})
            board.push(move)
        games.append(game)
    if not games:
        raise ValueError("No complete valid games found in prefix")
    args.output.mkdir(parents=True)
    (args.output / "sample.pgn").write_text("\n\n".join(str(g) for g in games) + "\n", encoding="utf-8")
    (args.output / "positions.jsonl").write_text("".join(json.dumps(p) + "\n" for p in positions), encoding="utf-8")
    # Representative position after the opening; illustration only, not target-theme training data.
    chosen = next((p for p in positions if p["ply"] >= 15), positions[0])
    (args.output / "example-board.svg").write_text(chess.svg.board(chess.Board(chosen["fen"]), size=512), encoding="utf-8")
    counts = {name: sum(p["split"] == name for p in positions) for name in ("train", "validation", "test")}
    summary = {"source_url": "https://database.lichess.org/standard/lichess_db_standard_rated_2026-10.pgn.zst", "license": "CC0 (Lichess open database)", "compressed_bytes_downloaded": args.prefix.stat().st_size, "decompressed_bytes_read": total, "complete_games_validated": len(games), "rejected_games": rejected, "positions": len(positions), "position_split_counts": counts, "split_group": "source game", "sampling": "first complete games from start of file; not random or representative", "limitations": ["Moves are human choices, not best-move labels", "No model has been trained", "Rendered SVG uses a different piece theme from supplied screenshot", "Opening positions can repeat across games; deduplicate positions before model evaluation"]}
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
