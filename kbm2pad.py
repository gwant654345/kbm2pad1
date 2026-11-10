"""
KBM2Pad - turn your keyboard & mouse into a virtual Xbox 360 controller.
Windows only. Needs the ViGEmBus driver (installed with the vgamepad package).

  WASD            -> left stick
  Mouse movement  -> right stick
  Everything else -> rebindable buttons / triggers / D-pad
Press F8 to start / stop emulation at any time.
"""
import ctypes
import json
import os
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

if os.name != "nt":
    messagebox.showerror("KBM2Pad", "KBM2Pad only works on Windows (it uses the ViGEmBus driver).")
    sys.exit(1)

try:
    import vgamepad as vg
    from pynput import keyboard, mouse
except ImportError:
    messagebox.showerror("KBM2Pad", "Missing packages. Run:\n\npy -m pip install vgamepad pynput")
    sys.exit(1)

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

user32 = ctypes.windll.user32
CONFIG = os.path.join(os.path.expanduser("~"), "kbm2pad.json")
TOGGLE_KEY = "f8"

ACTIONS = [
    ("ls_up", "Left stick up"), ("ls_down", "Left stick down"),
    ("ls_left", "Left stick left"), ("ls_right", "Left stick right"),
    ("a", "A"), ("b", "B"), ("x", "X"), ("y", "Y"),
    ("lb", "Left bumper (LB)"), ("rb", "Right bumper (RB)"),
    ("lt", "Left trigger (LT)"), ("rt", "Right trigger (RT)"),
    ("l3", "Left stick click (L3)"), ("r3", "Right stick click (R3)"),
    ("start", "Start"), ("back", "Back / Select"),
    ("dpad_up", "D-pad up"), ("dpad_down", "D-pad down"),
    ("dpad_left", "D-pad left"), ("dpad_right", "D-pad right"),
]
DEFAULT_BIND = {
    "ls_up": "w", "ls_down": "s", "ls_left": "a", "ls_right": "d",
    "a": "space", "b": "ctrl", "x": "r", "y": "f", "lb": "q", "rb": "e",
    "lt": "mouse_right", "rt": "mouse_left", "l3": "shift", "r3": "mouse_middle",
    "start": "esc", "back": "tab",
    "dpad_up": "up", "dpad_down": "down", "dpad_left": "left", "dpad_right": "right",
}
DEFAULT_PARAMS = {"sens": 25.0, "smooth": 0.3, "dz": 0.10, "block": 1.0, "invy": 0.0}

B = vg.XUSB_BUTTON
BTN = {
    "a": B.XUSB_GAMEPAD_A, "b": B.XUSB_GAMEPAD_B, "x": B.XUSB_GAMEPAD_X, "y": B.XUSB_GAMEPAD_Y,
    "lb": B.XUSB_GAMEPAD_LEFT_SHOULDER, "rb": B.XUSB_GAMEPAD_RIGHT_SHOULDER,
    "l3": B.XUSB_GAMEPAD_LEFT_THUMB, "r3": B.XUSB_GAMEPAD_RIGHT_THUMB,
    "start": B.XUSB_GAMEPAD_START, "back": B.XUSB_GAMEPAD_BACK,
    "dpad_up": B.XUSB_GAMEPAD_DPAD_UP, "dpad_down": B.XUSB_GAMEPAD_DPAD_DOWN,
    "dpad_left": B.XUSB_GAMEPAD_DPAD_LEFT, "dpad_right": B.XUSB_GAMEPAD_DPAD_RIGHT,
}

VK_NAMES = {
    0x08: "backspace", 0x09: "tab", 0x0D: "enter", 0x10: "shift", 0xA0: "shift", 0xA1: "shift",
    0x11: "ctrl", 0xA2: "ctrl", 0xA3: "ctrl", 0x12: "alt", 0xA4: "alt", 0xA5: "alt",
    0x14: "caps", 0x1B: "esc", 0x20: "space", 0x21: "pgup", 0x22: "pgdn", 0x23: "end",
    0x24: "home", 0x25: "left", 0x26: "up", 0x27: "right", 0x28: "down", 0x2D: "insert",
    0x2E: "delete", 0xBA: ";", 0xBB: "=", 0xBC: ",", 0xBD: "-", 0xBE: ".", 0xBF: "/",
    0xC0: "`", 0xDB: "[", 0xDC: "\\", 0xDD: "]", 0xDE: "'",
}


def vk_name(vk):
    if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:
        return chr(vk).lower()
    if 0x70 <= vk <= 0x87:
        return "f%d" % (vk - 0x6F)
    if 0x60 <= vk <= 0x69:
        return "num%d" % (vk - 0x60)
    return VK_NAMES.get(vk, "vk%d" % vk)


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class App:
    def __init__(self, root):
        self.root = root
        self.q = queue.Queue()
        self.bind = dict(DEFAULT_BIND)
        self.params = dict(DEFAULT_PARAMS)
        self.load()
        self.down, self.pulse, self.mapped = set(), {}, set()
        self.active, self.capture, self.pad, self.worker = False, None, None, None
        self.build_ui()
        self.refresh_mapped()
        self.kb = keyboard.Listener(win32_event_filter=self.kb_filter)
        self.ms = mouse.Listener(win32_event_filter=self.ms_filter)
        self.kb.start()
        self.ms.start()
        root.after(30, self.poll)
        root.protocol("WM_DELETE_WINDOW", self.close)

    # ---------- config ----------
    def load(self):
        try:
            with open(CONFIG) as f:
                d = json.load(f)
            self.bind.update(d.get("bind", {}))
            self.params.update(d.get("params", {}))
        except Exception:
            pass

    def save(self):
        try:
            with open(CONFIG, "w") as f:
                json.dump({"bind": self.bind, "params": self.params}, f, indent=2)
        except Exception:
            pass

    def refresh_mapped(self):
        self.mapped = {v for v in self.bind.values() if v and v != TOGGLE_KEY}

    # ---------- UI ----------
    def build_ui(self):
        r = self.root
        r.title("KBM2Pad - keyboard & mouse to controller")
        r.geometry("460x700")
        top = ttk.Frame(r, padding=10)
        top.pack(fill="x")
        self.btn_start = ttk.Button(top, text="Start emulation (F8)", command=self.toggle)
        self.btn_start.pack(side="left")
        self.status = ttk.Label(top, text="Stopped", foreground="#b00020")
        self.status.pack(side="left", padx=12)

        self.tree = ttk.Treeview(r, columns=("act", "inp"), show="headings", height=20)
        self.tree.heading("act", text="Controller input")
        self.tree.heading("inp", text="Keyboard / mouse")
        self.tree.column("act", width=250)
        self.tree.column("inp", width=170)
        for aid, label in ACTIONS:
            self.tree.insert("", "end", iid=aid, values=(label, self.bind.get(aid, "")))
        self.tree.pack(fill="x", padx=10)
        self.tree.bind("<Double-1>", lambda e: self.start_capture())

        row = ttk.Frame(r, padding=(10, 6))
        row.pack(fill="x")
        self.btn_rebind = ttk.Button(row, text="Rebind selected", command=self.start_capture)
        self.btn_rebind.pack(side="left")
        ttk.Button(row, text="Clear", command=self.clear_sel).pack(side="left", padx=6)
        ttk.Button(row, text="Reset all", command=self.reset).pack(side="left")
        self.hint = ttk.Label(r, text="Double-click a row to rebind it.", padding=(10, 0))
        self.hint.pack(fill="x")

        ttk.Label(r, text="Mouse -> right stick", font=("Segoe UI", 10, "bold"), padding=(10, 10, 0, 0)).pack(anchor="w")
        self.slider("Sensitivity", "sens", 1, 100, "%.0f")
        self.slider("Smoothing", "smooth", 0, 0.9, "%.2f")
        self.slider("Deadzone compensation", "dz", 0, 0.5, "%.2f")
        self.chk("Invert Y axis", "invy")
        self.chk("Block mapped keys/buttons from other apps while running", "block")

    def slider(self, text, key, lo, hi, fmt):
        f = ttk.Frame(self.root, padding=(10, 2))
        f.pack(fill="x")
        ttk.Label(f, text=text, width=22).pack(side="left")
        val = ttk.Label(f, width=6)

        def cb(v):
            self.params[key] = float(v)
            val.config(text=fmt % float(v))
        s = ttk.Scale(f, from_=lo, to=hi, command=cb)
        s.set(self.params[key])
        s.pack(side="left", fill="x", expand=True)
        val.pack(side="left")

    def chk(self, text, key):
        var = tk.BooleanVar(value=bool(self.params[key]))

        def cb():
            self.params[key] = 1.0 if var.get() else 0.0
        ttk.Checkbutton(self.root, text=text, variable=var, command=cb).pack(anchor="w", padx=10)

    # ---------- rebinding ----------
    def start_capture(self):
        sel = self.tree.selection()
        if self.capture:
            self.capture = None
            self.hint.config(text="Cancelled.")
            self.btn_rebind.config(text="Rebind selected")
            return
        if not sel:
            self.hint.config(text="Select a row first.")
            return
        self.capture = sel[0]
        self.hint.config(text="Press a key or mouse button... (click Rebind again to cancel)")
        self.btn_rebind.config(text="Cancel")

    def set_bind(self, aid, name):
        self.bind[aid] = name
        self.tree.set(aid, "inp", name)
        self.refresh_mapped()
        self.save()

    def clear_sel(self):
        for aid in self.tree.selection():
            self.set_bind(aid, "")

    def reset(self):
        for aid, name in DEFAULT_BIND.items():
            self.set_bind(aid, name)

    def poll(self):
        try:
            while True:
                ev = self.q.get_nowait()
                if ev[0] == "toggle":
                    self.toggle()
                elif ev[0] == "cap" and self.capture:
                    self.set_bind(self.capture, ev[1])
                    self.capture = None
                    self.hint.config(text="Bound to: %s" % ev[1])
                    self.btn_rebind.config(text="Rebind selected")
        except queue.Empty:
            pass
        self.root.after(30, self.poll)

    # ---------- input hooks (low-level, run in pynput threads) ----------
    def kb_filter(self, msg, data):
        down, up = msg in (0x100, 0x104), msg in (0x101, 0x105)
        if not (down or up):
            return True
        name = vk_name(data.vkCode)
        if down:
            if name == TOGGLE_KEY:
                if name not in self.down:
                    self.down.add(name)
                    self.q.put(("toggle",))
                return True
            if self.capture:
                self.q.put(("cap", name))
                return True
            self.down.add(name)
        else:
            self.down.discard(name)
        if self.active and self.params["block"] and name in self.mapped:
            self.kb.suppress_event()
        return True

    MOUSE_BTN = {0x201: ("mouse_left", 1), 0x202: ("mouse_left", 0),
                 0x204: ("mouse_right", 1), 0x205: ("mouse_right", 0),
                 0x207: ("mouse_middle", 1), 0x208: ("mouse_middle", 0)}

    def ms_filter(self, msg, data):
        if msg in self.MOUSE_BTN:
            name, is_down = self.MOUSE_BTN[msg]
        elif msg in (0x20B, 0x20C):
            name = "mouse_x1" if ((data.mouseData >> 16) & 0xFFFF) == 1 else "mouse_x2"
            is_down = 1 if msg == 0x20B else 0
        elif msg == 0x20A:
            name = "wheel_up" if ctypes.c_short((data.mouseData >> 16) & 0xFFFF).value > 0 else "wheel_down"
            if self.capture:
                self.q.put(("cap", name))
                return True
            if self.active:
                self.pulse[name] = time.time() + 0.06
                if self.params["block"] and name in self.mapped:
                    self.ms.suppress_event()
            return True
        else:
            return True
        if is_down and self.capture:
            self.q.put(("cap", name))
            return True
        (self.down.add if is_down else self.down.discard)(name)
        if self.active and self.params["block"] and name in self.mapped:
            self.ms.suppress_event()
        return True

    # ---------- emulation ----------
    def toggle(self):
        self.stop() if self.active else self.start()

    def start(self):
        try:
            self.pad = vg.VX360Gamepad()
        except Exception as e:
            messagebox.showerror("KBM2Pad", "Couldn't create the virtual controller.\n"
                                 "Is the ViGEmBus driver installed?\n\n%s" % e)
            return
        self.active = True
        self.worker = threading.Thread(target=self.loop, daemon=True)
        self.worker.start()
        self.btn_start.config(text="Stop emulation (F8)")
        self.status.config(text="RUNNING - mouse is locked to screen centre", foreground="#1a7f37")

    def stop(self):
        self.active = False
        if self.worker:
            self.worker.join(timeout=1)
        if self.pad:
            try:
                self.pad.reset()
                self.pad.update()
            except Exception:
                pass
            self.pad = None  # releases (unplugs) the virtual controller
        self.btn_start.config(text="Start emulation (F8)")
        self.status.config(text="Stopped", foreground="#b00020")

    def loop(self):
        pad = self.pad
        W, H = user32.GetSystemMetrics(0) // 2, user32.GetSystemMetrics(1) // 2
        user32.SetCursorPos(W, H)
        try:
            ctypes.windll.winmm.timeBeginPeriod(1)
        except Exception:
            pass
        rx = ry = 0.0
        nxt = time.perf_counter()
        pt = POINT()

        def shape(v, dz):
            if abs(v) < 0.01:
                return 0.0
            return (1 if v > 0 else -1) * (dz + (1 - dz) * abs(v))

        while self.active:
            P, now = self.params, time.time()

            def on(a):
                n = self.bind.get(a)
                return bool(n) and (n in self.down or self.pulse.get(n, 0) > now)

            x = int(on("ls_right")) - int(on("ls_left"))
            y = int(on("ls_up")) - int(on("ls_down"))
            if x and y:
                x, y = x * 0.7071, y * 0.7071
            pad.left_joystick_float(x_value_float=float(x), y_value_float=float(y))

            user32.GetCursorPos(ctypes.byref(pt))
            dx, dy = pt.x - W, pt.y - H
            if dx or dy:
                user32.SetCursorPos(W, H)
            g, s = P["sens"] / 100.0, P["smooth"]
            ty = dy if P["invy"] else -dy
            rx = rx * s + max(-1.0, min(1.0, dx * g)) * (1 - s)
            ry = ry * s + max(-1.0, min(1.0, ty * g)) * (1 - s)
            pad.right_joystick_float(x_value_float=shape(rx, P["dz"]), y_value_float=shape(ry, P["dz"]))

            for a, b in BTN.items():
                if on(a):
                    pad.press_button(button=b)
                else:
                    pad.release_button(button=b)
            pad.left_trigger_float(value_float=1.0 if on("lt") else 0.0)
            pad.right_trigger_float(value_float=1.0 if on("rt") else 0.0)
            pad.update()

            nxt += 1 / 125
            time.sleep(max(0.0, nxt - time.perf_counter()))
        try:
            ctypes.windll.winmm.timeEndPeriod(1)
        except Exception:
            pass

    def close(self):
        if self.active:
            self.stop()
        self.save()
        self.kb.stop()
        self.ms.stop()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
