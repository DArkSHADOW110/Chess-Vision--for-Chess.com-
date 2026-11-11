# Chess Vision

The desktop prototype is ready on this PC. Double-click **Start Chess Vision.cmd**. See **QUICKSTART.md** for screen sharing, game-state controls, and limitations. No additional dependencies or engine downloads are required for the basic app.

Train a small model to recognize chess pieces from screenshots of a local practice board. A chess engine can suggest moves after recognition works.

## First milestone

Classify each cropped square into one of 13 classes: empty, or one of six white/six black piece types. This trains visual recognition, not chess strategy.

## Project layout

- `config.json`: image size, labels, and initial training settings.
- `data/raw/`: original board images and their position labels.
- `data/processed/`: square images grouped into train, validation, and test sets.
- `models/`: trained weights.
- `src/check_environment.py`: checks Python and optional GPU support.

## Setup

Python must run successfully before proceeding. In PowerShell, from this folder:

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe src/check_environment.py
```

Next: select one board theme and provide a screenshot from a local practice board. Record its piece placement and orientation, then prepare labeled square crops. Split original board positions into train/validation/test BEFORE cropping to avoid leaking squares from the same board between sets. If generating images, split positions before rendering variants too.

The `.venv` environment has been created with Python 3.11.9. Pillow, chess, and zstandard are installed (`requirements-data.txt`). The desktop app uses screenshot-calibrated visual templates plus a basic local search engine; PyTorch and a neural model are not installed.

## Prepare the supplied starting board

From this project directory in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-data.txt
.\.venv\Scripts\python.exe src/prepare_board.py data/raw/starting-position.png --box 391 114 1207 930 --placement rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR --output data/processed/starting-position
```

The box coordinates apply only to this supplied 1919 x 1046 screenshot. Output includes the board crop, 64 original-size square crops, human-provided labels, metadata, and a contact sheet for checking. No resizing or position recognition is performed by this script. New screenshots need verified coordinates and piece placement. Do not run this starting-position label on a moved board.

This is one source board, not a sufficient training/evaluation dataset. Some piece types appear on only one square color; collect independent positions with each piece on both colors before training. Keep variations of the same source board together in one split.

## Limits

A screenshot alone may not establish side to move, castling rights, or en passant state. Those must be supplied or tracked separately. Use this project for local practice and permitted analysis.

## Small Lichess sample

Source: https://database.lichess.org/standard/lichess_db_standard_rated_2026-10.pgn.zst (CC0).

Only its first 1 MiB was requested with HTTP byte range `0-1048575`; the `.part` file is deliberately incomplete and is not a standalone complete archive. Never decompress it as though it were the whole monthly download.

```powershell
.\.venv\Scripts\python.exe src/sample_games.py data/raw/lichess-2026-10-prefix.pgn.zst.part --output data/processed/lichess-sample --games 50
```

The script reads at most 32 MiB of decompressed text, discards the last potentially incomplete game, validates legal moves, and exports complete PGN games and FEN/played-move pairs. Games are grouped for provisional splits. Identical positions must also be deduplicated before evaluating a trained model. This tests data ingestion only; it does not train a screen reader or a chess-playing model. The sample is taken from the beginning of the file and is not representative of the whole month. See `summary.json` for the actual counts.

## Overview

Chess Vision is a desktop prototype that can recognize chess pieces from screenshots of a local practice board and suggest moves using a chess engine. It includes scripts for preparing board images, training a small visual model, and running the application.

The project is organized as follows:

- `src/` – source code for the application and utilities.
- `data/` – raw and processed board images.
- `models/` – trained model files.
- `QUICKSTART.md` – instructions for running the app.

Feel free to explore, modify the board theme, or extend the recognition pipeline.
