"""Track state from observed legal moves without inventing hidden castling/EP rights."""
import chess


class StateTracker:
    def __init__(self):
        self.board = None
        self.note = "Start sharing from the initial position for full game-state tracking."

    def reset(self):
        self.__init__()

    def set_fen(self, fen):
        board = chess.Board(fen)
        if not board.is_valid():
            raise ValueError("FEN is not a valid standard chess position")
        self.board = board
        self.note = "Full state loaded from FEN."

    def update(self, observed, side="Auto"):
        placement = observed.board_fen()
        if self.board is not None and self.board.board_fen() == placement:
            if side != "Auto" and self.board.turn != (side == "White"):
                raise ValueError("Selected side disagrees with tracked turn. Choose Auto or reset state.")
            return self.board.copy(stack=True)
        if placement == chess.Board().board_fen():
            if side == "Black":
                raise ValueError("The standard starting position has White to move.")
            self.board = chess.Board()
            self.note = "Synced from starting position; turn, castling and en passant are tracked."
            return self.board.copy(stack=True)
        if self.board is not None:
            matches = []
            for first in list(self.board.legal_moves):
                candidate = self.board.copy(stack=True)
                candidate.push(first)
                if candidate.board_fen() == placement:
                    matches.append(candidate)
                for second in list(candidate.legal_moves):
                    candidate.push(second)
                    if candidate.board_fen() == placement:
                        matches.append(candidate.copy(stack=True))
                    candidate.pop()
            if len(matches) == 1:
                candidate = matches[0]
                if side != "Auto" and candidate.turn != (side == "White"):
                    raise ValueError("Selected side disagrees with tracked turn. Choose Auto.")
                self.board = candidate
                self.note = "Legal moves tracked from the previous frame."
                return self.board.copy(stack=True)
            raise ValueError("Position changed beyond tracking or recognition is wrong. Reset state or load the exact FEN.")
        if side == "Auto":
            raise ValueError("Turn is unknown. Start from the initial position, select Side to move, or load FEN.")
        candidate = observed.copy()
        candidate.turn = side == "White"
        candidate.castling_rights = chess.BB_EMPTY
        candidate.ep_square = None
        if not candidate.is_valid():
            raise ValueError("Recognized position is invalid for the selected side. Check the preview and orientation.")
        self.board = candidate
        self.note = "Manual turn. Unknown castling/en passant rights are disabled; load FEN for exact state."
        return self.board.copy(stack=True)
