"""A modest offline search engine, plus optional user-supplied UCI engine."""
from dataclasses import dataclass
import subprocess
import time

import chess
import chess.engine

VALUES = {chess.PAWN: 100, chess.KNIGHT: 320, chess.BISHOP: 335, chess.ROOK: 500, chess.QUEEN: 900, chess.KING: 0}


@dataclass
class Suggestion:
    move: chess.Move | None
    engine: str
    depth: int
    nodes: int


class SearchTimeout(Exception):
    pass


def suggest(board, engine_path=None, seconds=1.0):
    if board.is_game_over():
        return Suggestion(None, "Game finished", 0, 0)
    if engine_path:
        options = {"creationflags": subprocess.CREATE_NO_WINDOW} if hasattr(subprocess, "CREATE_NO_WINDOW") else {}
        with chess.engine.SimpleEngine.popen_uci(engine_path, timeout=10, **options) as engine:
            settings = {key: value for key, value in {"Threads": 2, "Hash": 128}.items() if key in engine.options}
            engine.configure(settings)
            result = engine.play(board, chess.engine.Limit(time=seconds))
            return Suggestion(result.move, engine.id.get("name", "UCI engine"), 0, 0)
    deadline, nodes = time.monotonic()+seconds, 0

    def evaluate(position):
        score = 0
        for square, piece in position.piece_map().items():
            file, rank = chess.square_file(square), chess.square_rank(square)
            advancement = rank if piece.color else 7-rank
            center = 7 - abs(2*file-7) - abs(2*rank-7)
            bonus = 0
            if piece.piece_type == chess.PAWN:
                bonus = advancement*7 + (10 if 2 <= file <= 5 else 0)
            elif piece.piece_type in (chess.KNIGHT, chess.BISHOP):
                bonus = center*5
            elif piece.piece_type == chess.KING:
                bonus = -advancement*5 + (20 if file in (2, 6) and advancement == 0 else 0)
            score += (VALUES[piece.piece_type]+bonus) * (1 if piece.color else -1)
        return score if position.turn else -score

    def order(position, moves):
        def priority(move):
            victim = position.piece_at(move.to_square)
            attacker = position.piece_at(move.from_square)
            return (10000 if move.promotion else 0) + (10*VALUES[victim.piece_type] - VALUES[attacker.piece_type] if victim else 100 if position.is_en_passant(move) else 0)
        return sorted(moves, key=priority, reverse=True)

    def search(position, depth, alpha, beta, ply, quiet=0):
        nonlocal nodes
        nodes += 1
        if nodes % 64 == 0 and time.monotonic() >= deadline:
            raise SearchTimeout
        if position.is_checkmate():
            return -100000+ply
        if position.is_stalemate() or position.is_insufficient_material() or position.is_seventyfive_moves() or position.is_fivefold_repetition():
            return 0
        if depth <= 0:
            standing = evaluate(position)
            if quiet >= 3:
                return standing
            if not position.is_check():
                if standing >= beta:
                    return beta
                alpha = max(alpha, standing)
                moves = [m for m in position.legal_moves if position.is_capture(m) or m.promotion]
            else:
                moves = list(position.legal_moves)
        else:
            moves = list(position.legal_moves)
        for move in order(position, moves):
            position.push(move)
            try:
                score = -search(position, depth-1, -beta, -alpha, ply+1, quiet+1 if depth <= 0 else 0)
            finally:
                position.pop()
            if score >= beta:
                return beta
            alpha = max(alpha, score)
        return alpha

    legal = order(board, list(board.legal_moves))
    best, finished = legal[0], 0
    for depth in range(1, 6):
        iteration_best, alpha = best, -200000
        try:
            for move in sorted(legal, key=lambda m: m != best):
                board.push(move)
                try:
                    score = -search(board, depth-1, -200000, -alpha, 1)
                finally:
                    board.pop()
                if score > alpha:
                    alpha, iteration_best = score, move
                if time.monotonic() >= deadline:
                    raise SearchTimeout
        except SearchTimeout:
            break
        best, finished = iteration_best, depth
    return Suggestion(best, "Built-in basic engine", finished, nodes)
