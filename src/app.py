"""Local Windows screen-to-chess-move desktop prototype."""
import ctypes
from concurrent.futures import ThreadPoolExecutor
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import queue
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import chess
from PIL import Image, ImageDraw, ImageGrab, ImageTk

from game_state import StateTracker
from move_engine import suggest
from vision import BoardReader, ROOT

BG, PANEL, TEXT, MUTED, ACCENT = "#101722", "#1b2635", "#edf3f9", "#a5b4c7", "#71e0b1"


class AreaPicker(tk.Toplevel):
    def __init__(self, parent, screenshot, callback):
        super().__init__(parent)
        self.callback = callback
        self.start = None
        self.rectangle = None
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.geometry(f"{screenshot.width}x{screenshot.height}+0+0")
        self.canvas = tk.Canvas(self, cursor="crosshair", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.photo = ImageTk.PhotoImage(screenshot)
        self.canvas.create_image(0, 0, anchor="nw", image=self.photo)
        self.canvas.create_rectangle(0, 0, 650, 60, fill=BG, outline="")
        self.canvas.create_text(20, 20, anchor="nw", text="Drag around the complete board. Esc cancels.", fill=TEXT, font=("Segoe UI", 16))
        self.canvas.bind("<ButtonPress-1>", self.press)
        self.canvas.bind("<B1-Motion>", self.drag)
        self.canvas.bind("<ButtonRelease-1>", self.release)
        self.bind("<Escape>", lambda event: self.finish(None))
        self.focus_force()
        self.grab_set()

    def press(self, event):
        self.start = (event.x, event.y)
        if self.rectangle:
            self.canvas.delete(self.rectangle)
        self.rectangle = self.canvas.create_rectangle(event.x, event.y, event.x, event.y, outline=ACCENT, width=3)

    def drag(self, event):
        if self.start:
            self.canvas.coords(self.rectangle, *self.start, event.x, event.y)

    def release(self, event):
        if not self.start:
            return
        x, y = self.start
        box = (min(x, event.x), min(y, event.y), max(x, event.x), max(y, event.y))
        if box[2]-box[0] < 160 or box[3]-box[1] < 160:
            return
        if abs((box[2]-box[0])-(box[3]-box[1])) > (box[2]-box[0])*.05:
            messagebox.showinfo("Select a square board", "Select only the complete chess board, including all 64 squares.", parent=self)
            return
        self.finish(box)

    def finish(self, box):
        self.grab_release()
        self.destroy()
        self.callback(box)


class ChessVisionApp:
    def __init__(self, root):
        self.root = root
        self.reader = BoardReader()
        self.tracker = StateTracker()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="chess-analysis")
        self.events = queue.Queue()
        self.busy = False
        self.live = False
        self.closed = False
        self.generation = 0
        self.capture_box = None
        engines = sorted((ROOT / "engines").rglob("stockfish*.exe"))
        self.engine_path = str(engines[0]) if engines else None
        self.last_image = None
        self.last_result = None
        self.last_key = None
        self.pending_placement = None
        self.pending_count = 0
        self.orientation = tk.StringVar(value="White at bottom")
        self.side = tk.StringVar(value="Auto")
        self.status = tk.StringVar(value="Ready · screen sharing is off")
        self.move = tk.StringVar(value="—")
        self.move_detail = tk.StringVar(value="Share your board or try the demo.")
        self.engine_label = tk.StringVar(value="Built-in basic engine · offline")
        self.state_note = tk.StringVar(value="Start sharing before the first move for automatic turn tracking.")
        self.source_label = tk.StringVar(value="No screen is being captured")
        self.recognition_label = tk.StringVar(value="Calibrated to your green/cream board theme")
        self.build_ui()
        self.root.after(100, self.poll)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def label(self, parent, text=None, variable=None, size=10, color=TEXT, **kw):
        return tk.Label(parent, text=text, textvariable=variable, bg=parent.cget("bg"), fg=color, font=("Segoe UI", size), **kw)

    def button(self, parent, text, command, primary=False):
        return tk.Button(parent, text=text, command=command, bg=ACCENT if primary else "#2a3a50", fg=BG if primary else TEXT, activebackground="#9aefce" if primary else "#394d68", activeforeground=BG if primary else TEXT, relief="flat", bd=0, padx=12, pady=9, cursor="hand2", font=("Segoe UI", 10, "bold"))

    def build_ui(self):
        root = self.root
        root.title("Chess Vision")
        root.attributes("-topmost", True)
        root.configure(bg=BG)
        root.geometry(f"380x310+{max(0, root.winfo_screenwidth()-400)}+60")
        root.resizable(False, False)
        self.label(root, "CHESS VISION", size=18).pack(anchor="w", padx=22, pady=(20, 12))
        bar = tk.Frame(root, bg=BG)
        bar.pack(fill="x", padx=22)
        self.share_button = self.button(bar, "Share screen", self.start_share, primary=True)
        self.share_button.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.button(bar, "Stop", self.stop).pack(side="left")
        self.label(root, variable=self.move, size=34, color=ACCENT).pack(anchor="w", padx=22, pady=(16, 0))
        self.label(root, variable=self.move_detail, size=12, wraplength=335, justify="left").pack(anchor="w", padx=22)
        self.label(root, variable=self.status, color=MUTED, size=9, wraplength=335, justify="left").pack(anchor="w", padx=22, pady=(12, 8))
        # Retain an unmounted canvas for existing preview rendering; it is not shown.
        self.canvas = tk.Canvas(root, width=344, height=344)

    def clear_move(self, detail="Waiting for a clear board."):
        self.move.set("—")
        self.move_detail.set(detail)
        self.last_key = None

    def invalidate(self):
        self.generation += 1
        self.pending_placement = None
        self.pending_count = 0
        self.last_key = None

    def stop(self):
        self.live = False
        self.invalidate()
        self.status.set("Stopped · screen sharing is off")
        self.source_label.set("No screen is being captured")
        self.clear_move("Sharing stopped. Start sharing to get a fresh move.")
        if self.last_image:
            self.draw_board(self.last_image, None)

    def start_share(self):
        self.live = False
        self.invalidate()
        self.capture_box = None
        self.tracker.reset()
        self.clear_move("Looking for the board…")
        self.status.set("Starting screen share…")
        self.root.withdraw()
        generation = self.generation
        self.root.after(700, lambda: self.capture_initial() if generation == self.generation and not self.closed else None)

    def capture_initial(self):
        if self.closed:
            return
        try:
            screen = ImageGrab.grab()
            self.root.deiconify()
            self.live = True
            self.source_label.set("Sharing primary display locally · locating the board")
            self.submit(screen, live=True, detect=True)
        except Exception as error:
            self.root.deiconify()
            self.stop()
            self.status.set(f"Screen capture failed: {error}")

    def select_area(self):
        self.stop()
        self.root.withdraw()
        self.root.after(600, self.pick_area)

    def pick_area(self):
        if self.closed:
            return
        try:
            screen = ImageGrab.grab()
            def chosen(box):
                self.root.deiconify()
                if box:
                    self.capture_box = box
                    self.live = True
                    self.source_label.set("Sharing selected board area locally")
                    self.submit(screen.crop(box), live=True, detect=False)
            AreaPicker(self.root, screen, chosen)
        except Exception as error:
            self.root.deiconify()
            self.status.set(f"Area selection failed: {error}")

    def open_image(self):
        filename = filedialog.askopenfilename(title="Open a practice board screenshot", filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.webp")])
        if filename:
            self.load_image(Path(filename))

    def demo(self):
        self.load_image(ROOT / "data/raw/starting-position.png")

    def load_image(self, path):
        self.stop()
        try:
            with Image.open(path) as source:
                image = source.convert("RGB")
            self.source_label.set(f"Screenshot · {path.name}")
            self.status.set("Reading screenshot…")
            self.submit(image, live=False, detect=True)
        except Exception as error:
            self.status.set(f"Cannot open screenshot: {error}")

    def submit(self, image, live, detect):
        if self.closed:
            return
        if self.busy:
            requested_generation = self.generation
            self.root.after(250, lambda: self.submit(image, live, detect) if requested_generation == self.generation and not self.closed and (not live or self.live) else None)
            return
        self.busy = True
        generation = self.generation
        orientation = "white" if self.orientation.get().startswith("White") else "black"
        side, engine_path = self.side.get(), self.engine_path

        def work():
            try:
                box = self.reader.detect(image) if detect else None
                board_image = image.crop(box) if box else image
                recognized = self.reader.read(board_image, orientation)
                if self.tracker.board is None:
                    # Lock orientation only when a standard starting position is visible.
                    for candidate_orientation in ("white", "black"):
                        candidate = self.reader.read(board_image, candidate_orientation)
                        if candidate.board.board_fen() == chess.Board().board_fen():
                            recognized, orientation_local = candidate, candidate_orientation
                            break
                    else:
                        raise ValueError("Share from the starting board so your side and turn can be detected automatically.")
                else:
                    orientation_local = orientation
                if recognized.uncertain:
                    raise ValueError("Unclear squares: " + ", ".join(recognized.uncertain[:8]) + ". Wait for animation to finish; check theme and board selection.")
                # Recognized frames are handed to the UI thread for state mutation.
                self.events.put(("recognized", generation, (board_image, recognized, box, live, side, engine_path, orientation_local)))
            except Exception as error:
                logging.exception("Board recognition failed")
                self.events.put(("error", generation, (str(error), live)))
        self.executor.submit(work)

    def poll(self):
        if self.closed:
            return
        try:
            while True:
                event, generation, payload = self.events.get_nowait()
                self.busy = False
                if generation != self.generation:
                    if self.live:
                        self.root.after(250, self.tick)
                    continue
                if event == "error":
                    error, live = payload
                    self.clear_move("No suggestion while the position is uncertain.")
                    self.status.set(error)
                    if self.last_image:
                        self.draw_board(self.last_image, None)
                    if live and self.live:
                        if self.capture_box is None:
                            self.live = False
                            self.source_label.set("Sharing stopped · use Select board area or Share screen to retry")
                        else:
                            self.root.after(1100, self.tick)
                elif event == "recognized":
                    self.on_recognized(*payload)
                elif event == "suggested":
                    board, result, image, key, live = payload
                    self.last_key = key
                    self.last_result = result
                    self.show_suggestion(board, result, image)
                    if live and self.live:
                        self.root.after(1000, self.tick)
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def on_recognized(self, image, recognized, box, live, side, engine_path, orientation):
        self.orientation.set("White at bottom" if orientation == "white" else "Black at bottom")
        if box:
            self.capture_box = box
        self.last_image = image
        self.recognition_label.set(f"Theme match · max template error {recognized.worst_error:.1%}\nCheck the piece positions in the preview.")
        self.draw_board(image, None)
        placement = recognized.board.board_fen()
        if live:
            if placement != self.pending_placement:
                self.pending_placement, self.pending_count = placement, 1
                self.clear_move("Waiting for a second stable frame…")
                self.status.set("Sharing · confirming board stability")
                self.root.after(600, self.tick)
                return
            self.pending_count += 1
        try:
            board = self.tracker.update(recognized.board, side)
            if not board.is_valid():
                raise ValueError("Recognized board is not a valid standard chess position.")
            self.state_note.set(self.tracker.note)
        except ValueError as error:
            self.clear_move(str(error))
            self.status.set("Board read · game state needs attention")
            if live and self.live:
                self.root.after(1200, self.tick)
            return
        player_color = chess.WHITE if orientation == "white" else chess.BLACK
        if board.turn != player_color and not board.is_game_over():
            self.clear_move("Waiting for the opponent’s move…")
            self.status.set("You are " + ("White" if player_color else "Black") + " · watching the board")
            if live and self.live:
                self.root.after(900, self.tick)
            return
        key = (board.fen(), engine_path, orientation)
        if key == self.last_key and self.last_result:
            self.show_suggestion(board, self.last_result, image)
            if live and self.live:
                self.root.after(1100, self.tick)
            return
        self.clear_move("Analysing the recognized position…")
        self.status.set("Sharing · analysing" if live else "Analysing screenshot…")
        self.busy = True
        generation = self.generation
        def analyse():
            try:
                result = suggest(board.copy(stack=True), engine_path, seconds=.9)
                self.events.put(("suggested", generation, (board, result, image, key, live)))
            except Exception as error:
                logging.exception("Move analysis failed")
                self.events.put(("error", generation, (f"Engine failed: {error}", live)))
        self.executor.submit(analyse)

    def tick(self):
        if not self.live or self.closed or self.busy:
            return
        try:
            image = ImageGrab.grab(bbox=self.capture_box)
            self.source_label.set("Sharing board region locally · Stop ends capture")
            self.submit(image, live=True, detect=self.capture_box is None)
        except Exception as error:
            self.stop()
            self.status.set(f"Screen capture failed: {error}")

    def show_suggestion(self, board, result, image):
        if result.move:
            self.move.set(board.san(result.move))
            self.move_detail.set(f"{chess.square_name(result.move.from_square)} → {chess.square_name(result.move.to_square)}" + (f" · promote to {chess.piece_name(result.move.promotion)}" if result.move.promotion else "") + f"\n{'White' if board.turn else 'Black'} to move")
        else:
            self.move.set("Finished")
            self.move_detail.set(f"Result: {board.result()}")
        detail = f" · depth {result.depth}" if result.depth else ""
        self.engine_label.set(result.engine + detail)
        self.status.set("Sharing · move ready" if self.live else "Screenshot analysed · screen sharing is off")
        self.draw_board(image, result.move)

    def draw_board(self, image, move):
        preview = image.convert("RGB").resize((344, 344), Image.Resampling.LANCZOS)
        draw = ImageDraw.Draw(preview)
        if move:
            def center(square):
                file, rank = chess.square_file(square), chess.square_rank(square)
                col, row = (file, 7-rank) if self.orientation.get().startswith("White") else (7-file, rank)
                return ((col+.5)*43, (row+.5)*43)
            start, end = center(move.from_square), center(move.to_square)
            draw.line((start, end), fill="#13b988", width=8)
            draw.ellipse((start[0]-6, start[1]-6, start[0]+6, start[1]+6), fill="#13b988")
            import math
            angle = math.atan2(end[1]-start[1], end[0]-start[0])
            corners = [end, (end[0]-17*math.cos(angle-.48), end[1]-17*math.sin(angle-.48)), (end[0]-17*math.cos(angle+.48), end[1]-17*math.sin(angle+.48))]
            draw.polygon(corners, fill="#13b988")
        self.preview_photo = ImageTk.PhotoImage(preview)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self.preview_photo, anchor="nw")

    def settings_changed(self, event=None, reset=False):
        self.invalidate()
        if reset:
            self.tracker.reset()
        self.clear_move("Settings changed. Reading the board again…")
        if self.live:
            self.root.after(150, self.tick)
        elif self.last_image:
            self.submit(self.last_image.copy(), live=False, detect=False)

    def choose_engine(self):
        path = filedialog.askopenfilename(title="Select a trusted local UCI chess engine executable", filetypes=[("Windows executable", "*.exe")])
        if path:
            self.engine_path = path
            self.engine_label.set(Path(path).name)
            self.settings_changed()

    def use_basic(self):
        self.engine_path = None
        self.engine_label.set("Built-in basic engine · offline")
        self.settings_changed()

    def reset_state(self):
        self.tracker.reset()
        self.invalidate()
        self.state_note.set(self.tracker.note)
        self.clear_move("State reset. Use Auto from the starting board, or select the turn.")
        if self.live:
            self.root.after(200, self.tick)

    def load_fen(self):
        fen = simpledialog.askstring("Exact game state", "Paste the full six-field FEN for the visible board:", parent=self.root)
        if fen:
            try:
                if len(fen.split()) != 6:
                    raise ValueError("Enter a full six-field FEN, including turn and castling rights.")
                self.tracker.set_fen(fen)
                self.side.set("Auto")
                self.invalidate()
                self.state_note.set(self.tracker.note)
                if self.live:
                    self.root.after(150, self.tick)
                elif self.last_image:
                    self.submit(self.last_image.copy(), live=False, detect=False)
            except ValueError as error:
                messagebox.showerror("Cannot load FEN", str(error))

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.live = False
        self.generation += 1
        self.capture_box = None
        self.last_image = None
        # Cancel all scheduled capture/retry callbacks before destroying Tk.
        for callback in self.root.tk.splitlist(self.root.tk.call("after", "info")):
            self.root.after_cancel(callback)
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.root.destroy()


def main():
    if sys.platform == "win32":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass
    logs = (Path(sys.executable).parent if getattr(sys, "frozen", False) else ROOT) / "logs"
    logs.mkdir(exist_ok=True)
    handler = RotatingFileHandler(logs / "app.log", maxBytes=200000, backupCount=2, encoding="utf-8")
    logging.basicConfig(level=logging.WARNING, handlers=[handler])
    root = tk.Tk()
    app = ChessVisionApp(root)
    if "--self-test" in sys.argv:
        import json
        report = Path(sys.executable).parent / "self-test.json"
        try:
            if not app.engine_path:
                raise RuntimeError("Packaged Stockfish missing")
            position = chess.Board()
            result = suggest(position, app.engine_path, seconds=.2)
            if result.move not in position.legal_moves:
                raise RuntimeError("Engine returned an illegal move")
            report.write_text(json.dumps({"ok": True, "engine": result.engine, "move": result.move.uci(), "templates": len(app.reader.templates), "tk": tk.TkVersion}, indent=2), encoding="utf-8")
        except Exception as error:
            report.write_text(json.dumps({"ok": False, "error": str(error)}), encoding="utf-8")
        finally:
            app.close()
        return
    if "--demo" in sys.argv:
        root.after(400, app.demo)
    root.mainloop()


if __name__ == "__main__":
    main()
