"""Meaningful regressions for the screenshot -> state -> legal move pipeline."""
from pathlib import Path
import sys
import unittest

import chess
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from game_state import StateTracker
from move_engine import suggest
from vision import BoardReader, pixel_data


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reader = BoardReader()
        cls.screenshot = Image.open(ROOT / "data/raw/starting-position.png").convert("RGB")
        cls.board_image = cls.screenshot.crop((391, 114, 1207, 930))

    def test_original_screenshot_detects_and_reads(self):
        box = self.reader.detect(self.screenshot)
        self.assertLessEqual(abs(box[0]-391), 2)
        self.assertLessEqual(abs(box[1]-114), 2)
        result = self.reader.read(self.screenshot.crop(box))
        self.assertEqual(result.board.board_fen(), chess.Board().board_fen())
        self.assertEqual(result.uncertain, [])

    def test_resized_screenshot(self):
        image = self.screenshot.resize((1535, 837), Image.Resampling.LANCZOS)
        box = self.reader.detect(image)
        result = self.reader.read(image.crop(box))
        self.assertEqual(result.board.board_fen(), chess.Board().board_fen())
        self.assertEqual(result.uncertain, [])

    def test_does_not_find_board_on_blank_screen(self):
        with self.assertRaises(ValueError):
            self.reader.detect(Image.new("RGB", (1000, 700), "#101722"))

    def test_black_bottom_orientation_and_turn_tracking(self):
        flipped = Image.new("RGB", (816, 816))
        for row in range(8):
            for col in range(8):
                tile = self.board_image.crop((col*102, row*102, (col+1)*102, (row+1)*102))
                flipped.paste(tile, ((7-col)*102, (7-row)*102))
        recognized = self.reader.read(flipped, "black")
        self.assertEqual(recognized.board.board_fen(), chess.Board().board_fen())
        tracker = StateTracker()
        board = tracker.update(recognized.board)
        self.assertNotEqual(board.turn, chess.BLACK)
        board.push_uci("e2e4")
        tracked = tracker.update(board)
        self.assertEqual(tracked.turn, chess.BLACK)

    def test_piece_on_opposite_background(self):
        image = self.board_image.copy()
        # Move a black queen from dark d8 onto light e6, changing only background.
        queen = image.crop((306, 0, 408, 102))
        old_background = queen.getpixel((2, 2))
        target_color = image.getpixel((410, 206))
        pixels = [target_color if max(abs(pixel[i]-old_background[i]) for i in range(3)) < 12 else pixel for pixel in pixel_data(queen)]
        queen.putdata(pixels)
        image.paste(queen, (408, 204))
        image.paste(Image.new("RGB", (102, 102), old_background), (306, 0))
        result = self.reader.read(image)
        self.assertEqual(result.board.piece_at(chess.E6), chess.Piece(chess.QUEEN, chess.BLACK))
        self.assertIsNone(result.board.piece_at(chess.D8))

    def test_tracking_two_moves_preserves_en_passant(self):
        tracker = StateTracker()
        tracker.update(chess.Board())
        actual = chess.Board()
        actual.push_uci("e2e4")
        actual.push_uci("d7d5")
        observed = chess.Board(actual.board_fen() + " w - - 0 1")
        result = tracker.update(observed)
        self.assertEqual(result.fen(en_passant="fen"), actual.fen(en_passant="fen"))
        self.assertEqual(len(result.move_stack), 2)

    def test_unknown_turn_is_not_guessed(self):
        board = chess.Board()
        board.push_uci("e2e4")
        tracker = StateTracker()
        with self.assertRaises(ValueError):
            tracker.update(board)
        manual = tracker.update(board, "Black")
        self.assertEqual(manual.castling_rights, 0)
        self.assertIsNone(manual.ep_square)

    def test_known_fen_preserves_rights(self):
        board = chess.Board()
        board.push_uci("e2e4")
        tracker = StateTracker()
        tracker.set_fen(board.fen(en_passant="fen"))
        result = tracker.update(board)
        self.assertEqual(result.fen(en_passant="fen"), board.fen(en_passant="fen"))

    def test_basic_engine_finds_mate_and_leaves_board_unchanged(self):
        board = chess.Board("7k/8/5KQ1/8/8/8/8/8 w - - 0 1")
        original = board.fen()
        result = suggest(board, seconds=.2)
        self.assertEqual(board.fen(), original)
        self.assertIn(result.move, board.legal_moves)
        board.push(result.move)
        self.assertTrue(board.is_checkmate())


if __name__ == "__main__":
    unittest.main()
