# Prototype validation

Verified on this PC, 11 November 2026:

- Python 3.11.9, Tk 8.6, Pillow 13.0.0, chess 1.11.2.
- Eight automated pipeline tests pass (`python -m unittest discover -s tests -v`).
- Automatically detected the board in the supplied full screenshot; all starting pieces matched its known placement.
- A resized version of that screenshot is detected and recognized.
- A synthetic moved queen on the opposite background is recognized.
- State tracking preserves castling and en passant from a known starting position/FEN and refuses to guess an unknown turn.
- The built-in engine finds a mate-in-one test and leaves the input board unchanged.
- Visually inspected the desktop interface and corrected a clipped footer and low-contrast combo boxes.
- Tested actual screen capture against a separate local test-board window: Share screen detected it; e2e4 changed the suggestion to a Black move; e7e5 changed it to a White move, with arrows and turn labels updated.
- Stop cleared the move and switched sharing off. The app was left in offline demo mode; the temporary test window was closed.

These checks do not establish recognition accuracy across other themes, all browser scales, highlights, animations, occluded windows, or all chess positions. The local live fixture uses the supplied theme; it is not a test of a running Chess.com match. The optional external UCI-engine path has not been tested with a downloaded Stockfish executable. The basic engine is modest and is not trained from the Lichess sample.

No new downloads were needed for the desktop prototype; it uses the previously installed packages.
