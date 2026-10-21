"""A command-line bridge to ELANIX SystemView 5 via native Windows messages.

Uses real menu/control handles and reads values back. No screenshots, keyboard
focus, global mouse input, or changes to the installed executable are required.
"""
from __future__ import annotations

import argparse
import csv
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
import math
from pathlib import Path
import subprocess
import re
import struct
import sys
import time
from svsettings import default_state,get_engine

H = W.HANDLE
U = W.UINT
D = W.DWORD
UP = C.c_size_t
LP = C.c_ssize_t
ENUM = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)


class BridgeError(RuntimeError):
    pass


class Win:
    def __init__(self):
        self.u = C.WinDLL("user32", use_last_error=True)
        self.k = C.WinDLL("kernel32", use_last_error=True)
        for name, ret, args in [
            ("EnumWindows", W.BOOL, [ENUM, W.LPARAM]),
            ("EnumChildWindows", W.BOOL, [W.HWND, ENUM, W.LPARAM]),
            ("GetWindowThreadProcessId", D, [W.HWND, C.POINTER(D)]),
            ("GetWindowTextW", C.c_int, [W.HWND, W.LPWSTR, C.c_int]),
            ("GetClassNameW", C.c_int, [W.HWND, W.LPWSTR, C.c_int]),
            ("IsWindow", W.BOOL, [W.HWND]),
            ("IsWindowVisible", W.BOOL, [W.HWND]),
            ("IsWindowEnabled", W.BOOL, [W.HWND]),
            ("GetDlgCtrlID", C.c_int, [W.HWND]),
            ("GetParent", W.HWND, [W.HWND]),
            ("GetMenu", H, [W.HWND]),
            ("GetSubMenu", H, [H, C.c_int]),
            ("GetMenuItemCount", C.c_int, [H]),
            ("GetMenuStringW", C.c_int, [H, U, W.LPWSTR, C.c_int, U]),
            ("GetMenuItemID", U, [H, C.c_int]),
            ("GetMenuState", U, [H, U, U]),
            ("PostMessageW", W.BOOL, [W.HWND, U, W.WPARAM, W.LPARAM]),
            ("SendMessageTimeoutW", LP,
             [W.HWND, U, W.WPARAM, W.LPARAM, U, U, C.POINTER(UP)]),
        ]:
            f = getattr(self.u, name)
            f.restype, f.argtypes = ret, args
        self.k.OpenProcess.restype = H
        self.k.OpenProcess.argtypes = [D, W.BOOL, D]
        self.k.CloseHandle.argtypes = [H]
        self.k.GetProcessTimes.argtypes = [H] + [C.POINTER(W.FILETIME)] * 4
        self.k.QueryFullProcessImageNameW.argtypes = [H, D, W.LPWSTR, C.POINTER(D)]
        self.k.CreateFileW.restype = H
        self.k.CreateFileW.argtypes = [W.LPCWSTR, D, D, H, D, D, H]

    def file_writes_closed(self, path):
        # SystemView retains a read handle on its active .svu. Permit readers,
        # but deny sharing with any still-open writer while checking completion.
        handle = self.k.CreateFileW(str(path), 0x80000000, 1, None, 3, 0x80, None)
        if handle == C.c_void_p(-1).value:
            return False
        self.k.CloseHandle(handle)
        return True

    def identity(self, pid):
        handle = self.k.OpenProcess(0x1000, False, pid)
        if not handle:
            raise BridgeError(f"Cannot open process {pid}: {C.get_last_error()}")
        try:
            times = [W.FILETIME() for _ in range(4)]
            if not self.k.GetProcessTimes(handle, *[C.byref(x) for x in times]):
                raise BridgeError("Cannot read process creation time")
            buf = C.create_unicode_buffer(32768)
            length = D(len(buf))
            if not self.k.QueryFullProcessImageNameW(handle, 0, buf, C.byref(length)):
                raise BridgeError("Cannot verify process image")
            return {"pid": pid, "created": (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime,
                    "exe": buf.value}
        finally:
            self.k.CloseHandle(handle)

    def pid(self, hwnd):
        pid = D()
        self.u.GetWindowThreadProcessId(hwnd, C.byref(pid))
        return pid.value

    def text(self, hwnd, timeout=400):
        buf = C.create_unicode_buffer(8192)
        result = UP()
        if self.u.SendMessageTimeoutW(hwnd, 0xD, len(buf), C.addressof(buf),
                                      2, timeout, C.byref(result)):
            return buf.value
        self.u.GetWindowTextW(hwnd, buf, len(buf))
        return buf.value

    def cls(self, hwnd):
        buf = C.create_unicode_buffer(256)
        self.u.GetClassNameW(hwnd, buf, len(buf))
        return buf.value

    def children(self, hwnd):
        result = []
        callback = ENUM(lambda h, _: result.append(h) or True)
        self.u.EnumChildWindows(hwnd, callback, 0)
        return result

    def windows(self, pid):
        result = []
        callback = ENUM(lambda h, _: (result.append(h) if self.pid(h) == pid else None) or True)
        self.u.EnumWindows(callback, 0)
        return result

    def describe(self, hwnd):
        result = {"hwnd": hwnd, "class": self.cls(hwnd), "text": self.text(hwnd),
                  "id": self.u.GetDlgCtrlID(hwnd), "visible": bool(self.u.IsWindowVisible(hwnd)),
                  "enabled": bool(self.u.IsWindowEnabled(hwnd))}
        if "ListBox" in result["class"]:
            count = self.send(hwnd, 0x18B)
            if 0 <= count <= 2000:
                result["items"] = []
                for index in range(count):
                    length = self.send(hwnd, 0x18A, index)
                    if 0 <= length <= 10000:
                        buf = C.create_unicode_buffer(length + 1)
                        self.send(hwnd, 0x189, index, C.addressof(buf))
                        result["items"].append(buf.value)
        return result

    def send(self, hwnd, msg, wparam=0, lparam=0, timeout=3000):
        result = UP()
        if not self.u.SendMessageTimeoutW(hwnd, msg, wparam, lparam, 2, timeout,
                                         C.byref(result)):
            raise BridgeError(f"Message 0x{msg:x} timed out or failed: {C.get_last_error()}")
        return C.c_ssize_t(result.value).value

    def post(self, hwnd, msg, wparam=0, lparam=0):
        if not self.u.PostMessageW(hwnd, msg, wparam, lparam):
            raise BridgeError(f"PostMessage failed: {C.get_last_error()}")

    @staticmethod
    def normalize(text):
        return " ".join(text.replace("&&", "\0").replace("&", "").replace("\0", "&")
                        .split("\t")[0].rstrip(". ").casefold().split())

    def menus(self, hwnd):
        def walk(menu, path=()):
            result = []
            if not menu:
                return result
            for index in range(self.u.GetMenuItemCount(menu)):
                buf = C.create_unicode_buffer(1024)
                self.u.GetMenuStringW(menu, index, buf, len(buf), 0x400)
                if not buf.value:
                    continue
                current = (*path, buf.value)
                sub = self.u.GetSubMenu(menu, index)
                if sub:
                    result.extend(walk(sub, current))
                else:
                    flags = self.u.GetMenuState(menu, index, 0x400)
                    result.append({"path": list(current), "id": self.u.GetMenuItemID(menu, index),
                                   "enabled": not bool(flags & 3), "checked": bool(flags & 8)})
            return result
        return walk(self.u.GetMenu(hwnd))


class Session:
    def __init__(self, state_path):
        self.win = Win()
        self.state_path = Path(state_path).resolve()
        self.state = json.loads(self.state_path.read_text(encoding="utf-8"))
        current = self.win.identity(self.state["pid"])
        if current != {k: self.state[k] for k in ("pid", "created", "exe")}:
            raise BridgeError("Session process identity changed; refusing to target a reused PID")

    def handle(self, hwnd):
        if not self.win.u.IsWindow(hwnd) or self.win.pid(hwnd) != self.state["pid"]:
            raise BridgeError("Window does not belong to this SystemView session")
        return hwnd

    def frame(self, kind):
        candidates = []
        for hwnd in self.win.windows(self.state["pid"]):
            text = self.win.text(hwnd)
            if kind == "design" and text.startswith("SystemView - "):
                candidates.append(hwnd)
            if kind == "analysis" and self.win.cls(hwnd) == "ThunderRT6MDIForm":
                candidates.append(hwnd)
        if kind == "design" and not candidates:
            # A newly created, unsaved model is captioned simply "SystemView".
            candidates = [h for h in self.win.windows(self.state["pid"])
                          if self.win.cls(h) == "ThunderRT6FormDC" and self.win.u.IsWindowVisible(h) and self.win.u.GetMenu(h)
                          and any(self.win.normalize(item["path"][0]) == "system"
                                  for item in self.win.menus(h))]
        if len(candidates) != 1:
            raise BridgeError(f"Expected one {kind} window; found {len(candidates)}")
        return candidates[0]

    def snapshot(self, include_children=False):
        windows = []
        for hwnd in self.win.windows(self.state["pid"]):
            if self.win.cls(hwnd) in ("MSCTFIME UI", "IME", "msvb_lib_tooltips"):
                continue
            item = self.win.describe(hwnd)
            if include_children:
                item["children"] = [self.win.describe(h) for h in self.win.children(hwnd)]
            windows.append(item)
        return {"pid": self.state["pid"], "project": self.state.get("project"), "windows": windows}

    def menu(self, kind, path):
        hwnd = self.frame(kind)
        expected = [self.win.normalize(x) for x in path.split("/")]
        matches = [x for x in self.win.menus(hwnd)
                   if [self.win.normalize(p) for p in x["path"]] == expected]
        if len(matches) != 1:
            raise BridgeError(f"Menu path must identify exactly one command: {path}")
        command = matches[0]
        if not command["enabled"]:
            raise BridgeError(f"Menu command is disabled: {path}")
        if not self.win.u.IsWindowEnabled(hwnd):
            raise BridgeError("Window is blocked by a modal dialog; inspect and handle it first")
        self.win.post(hwnd, 0x111, command["id"])
        return {"accepted": True, "completed": False, "window": kind, **command}

    def wait(self, predicate, description, timeout=12):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = predicate()
            if value:
                return value
            time.sleep(.08)
        messages = []
        for hwnd in self.win.windows(self.state["pid"]):
            if self.win.u.IsWindowVisible(hwnd) and self.win.u.IsWindowEnabled(hwnd):
                messages.append({"title": self.win.text(hwnd),
                                 "text": [self.win.text(c) for c in self.win.children(hwnd)
                                          if self.win.u.IsWindowVisible(c) and self.win.text(c)]})
        raise BridgeError(f"Timed out waiting for {description}; software feedback: {messages}")

    def dialog(self, title=None, cls=None, predicate=None):
        matches = [h for h in self.win.windows(self.state["pid"])
                   if self.win.u.IsWindowVisible(h) and self.win.u.IsWindowEnabled(h)
                   and (title is None or self.win.text(h) == title)
                   and (cls is None or self.win.cls(h) == cls)
                   and (predicate is None or predicate(h))]
        if len(matches) > 1:
            raise BridgeError("Dialog selector is ambiguous")
        return matches[0] if matches else None

    def control(self, parent, *, cid=None, text=None, cls=None, visible=True):
        candidates = [h for h in self.win.children(parent)
                      if (cid is None or self.win.u.GetDlgCtrlID(h) == cid)
                      and (text is None or self.win.normalize(self.win.text(h)) == self.win.normalize(text))
                      and (cls is None or cls.casefold() in self.win.cls(h).casefold())
                      and (not visible or self.win.u.IsWindowVisible(h))]
        if len(candidates) != 1:
            raise BridgeError(f"Control selector expected one match, got {len(candidates)}: "
                              f"id={cid}, text={text!r}, class={cls!r}")
        return candidates[0]

    def set_text(self, hwnd, value):
        self.handle(hwnd)
        buf = C.create_unicode_buffer(str(value))
        self.win.send(hwnd, 0xC, 0, C.addressof(buf))
        if self.win.text(hwnd) != str(value):
            raise BridgeError("Edit control did not retain the requested text")

    def press(self, hwnd):
        self.handle(hwnd)
        if (not any(kind in self.win.cls(hwnd).casefold() for kind in ("button", "checkbox"))
                or not self.win.u.IsWindowEnabled(hwnd)):
            raise BridgeError("Expected an enabled native button")
        self.win.post(hwnd, 0xF5)

    def dismiss_startup_notices(self):
        handled=False
        for hwnd in self.win.windows(self.state['pid']):
            if not self.win.u.IsWindowVisible(hwnd) or not self.win.u.IsWindowEnabled(hwnd):
                continue
            title=self.win.text(hwnd)
            if title in ['SystemView Tip','Recent SystemView Files']:
                handled=True
                # This VB6 startup button does not consistently dispatch BM_CLICK.
                # Address the exact visible form via its verified HWND and set its
                # own COM button Value, rather than synthesizing mouse input.
                from svapi.native import Native
                native=Native(self)
                controls=native.controls('@'+str(self.handle(hwnd)))
                choices=[c for c in controls if c.get('Caption','')=='Close']
                if len(choices)!=1:raise BridgeError('Expected one native startup Close control')
                control=choices[0];args=[] if control.get('Index') is None else [control['Index']]
                native.com('@'+str(hwnd),'value',control['Name'],'false',*args)
                native.com('@'+str(hwnd),'value',control['Name'],'true',*args)
                self.wait(lambda:not self.win.u.IsWindowVisible(hwnd),'known startup tip close')
                native.stop()
        return handled

    def select_list(self, hwnd, index):
        if index < 0 or self.win.send(hwnd, 0x186, index) != index:
            raise BridgeError("List selection failed")
        self.win.send(self.win.u.GetParent(hwnd), 0x111,
                      (1 << 16) | (self.win.u.GetDlgCtrlID(hwnd) & 0xffff), hwnd)
        if self.win.send(hwnd, 0x188) != index:
            raise BridgeError("List selection readback failed")

    def plots(self):
        frames = [h for h in self.win.windows(self.state["pid"])
                  if self.win.cls(h) == "ThunderRT6MDIForm"]
        if not frames:
            return []
        if len(frames) != 1:
            raise BridgeError("Expected at most one analysis window")
        return [self.win.describe(h) for h in self.win.children(frames[0])
                if self.win.cls(h) == "ThunderRT6FormDC" and re.match(r"^w\d+:", self.win.text(h))]

    def tokens(self):
        self.menu("design", "Tokens/Find Token")
        editor = self.wait(lambda: self.dialog("SystemView Token Finder"), "native token list")
        try:
            listing = self.control(editor, cls="ListBox")
            items = self.win.describe(listing).get("items", [])
            if items and not re.match(r"^\s*\d+\s", items[0]):
                self.press(self.control(editor, text="By Number", cls="CommandButton"))
                listing = self.wait(lambda: next((h for h in self.win.children(editor)
                                                  if "ListBox" in self.win.cls(h)
                                                  and self.win.u.IsWindowVisible(h)
                                                  and self.win.describe(h).get("items")
                                                  and re.match(r"^\s*\d+\s", self.win.describe(h)["items"][0])), None),
                                    "token list sorted by number")
                items = self.win.describe(listing).get("items", [])
            result = []
            for item in items:
                match = re.match(r"^\s*(\d+)\s+(.+)$", item)
                if not match:
                    raise BridgeError(f"Cannot parse native token entry: {item!r}")
                result.append({"id": int(match[1]), "description": match[2].strip()})
            return result
        finally:
            if self.win.u.IsWindow(editor):
                self.press(self.control(editor, text="Cancel", cls="CommandButton"))
                self.wait(lambda: not self.win.u.IsWindow(editor), "token finder to close")

    def run(self, timeout=30):
        # This command has no normal modal result. Wait for the actual native
        # simulation handler to return, rather than reporting PostMessage as success.
        if not 0 < timeout <= 60:
            raise BridgeError("Run timeout must be between 0 and 60 seconds")
        frame = self.frame("design")
        command = next((x for x in self.win.menus(frame)
                        if [self.win.normalize(p) for p in x["path"]]
                        == ["system", "run system and auto plot"]), None)
        if not command or not command["enabled"] or not self.win.u.IsWindowEnabled(frame):
            raise BridgeError("SystemView is not ready to run; inspect any open dialogs")
        start = time.monotonic()
        self.win.send(frame, 0x111, command["id"], timeout=int(timeout * 1000))
        plots = self.wait(self.plots, "actual simulation plot windows", timeout)
        if not self.win.u.IsWindowEnabled(frame):
            raise BridgeError("Simulation left a modal dialog open; inspect software feedback")
        return {"handler_returned": True, "seconds": time.monotonic() - start, "plots": plots,
                "verification": "Native simulation handler returned and result plots exist; "
                                "export data to verify numerical results."}

    def parameter_editor(self, token):
        self.menu("design", "Tools/Global Parameter Links")
        editor = self.wait(lambda: self.dialog("Global Token Parameter Links"), "parameter editor")
        toggle = self.control(editor, cid=5, cls="CommandButton")
        if self.win.normalize(self.win.text(toggle)) == "all tokens":
            self.win.send(toggle, 0xF5)
            self.wait(lambda: self.win.normalize(self.win.text(toggle)) == "show linked",
                      "all numeric tokens to be listed")
        token_list = self.control(editor, cid=12, cls="ListBox")
        items = self.win.describe(token_list).get("items", [])
        matches = [i for i, item in enumerate(items)
                   if re.match(rf"^\s*{int(token)}\s", item)]
        if len(matches) != 1:
            self.press(self.control(editor, text="Cancel", cls="CommandButton"))
            self.wait(lambda: not self.win.u.IsWindow(editor), "parameter editor to close")
            raise BridgeError(f"Token {token} is not available in the native numeric parameter editor")
        self.select_list(token_list, matches[0])
        return editor, items[matches[0]]

    def parameters(self, token):
        editor, label = self.parameter_editor(token)
        try:
            listing = self.control(editor, cid=22, cls="ListBox")
            names = self.win.describe(listing).get("items", [])
            parameters = []
            for index, name in enumerate(names):
                self.select_list(listing, index)
                parameters.append({"index": index, "name": name.split("\t", 1)[0].rstrip(),
                                   "value": self.win.text(self.control(editor, cid=20, cls="TextBox")),
                                   "link": self.win.text(self.control(editor, cid=16, cls="TextBox"))})
            return {"token": token, "label": label, "parameters": parameters}
        finally:
            if self.win.u.IsWindow(editor):
                self.press(self.control(editor, text="Cancel", cls="CommandButton"))
                self.wait(lambda: not self.win.u.IsWindow(editor), "parameter editor to close")

    def set_parameter(self, token, parameter, value):
        numeric = float(value)
        if not math.isfinite(numeric):
            raise BridgeError("Parameter value must be a finite number")
        editor, label = self.parameter_editor(token)
        listing = self.control(editor, cid=22, cls="ListBox")
        names = self.win.describe(listing).get("items", [])
        matches = [i for i, name in enumerate(names)
                   if name.split("\t", 1)[0].rstrip().casefold() == parameter.casefold()]
        if len(matches) != 1:
            self.press(self.control(editor, text="Cancel", cls="CommandButton"))
            self.wait(lambda: not self.win.u.IsWindow(editor), "parameter editor to close")
            raise BridgeError(f"Parameter name must match exactly; available names: {names}")
        index = matches[0]
        self.select_list(listing, index)
        before = {"value": self.win.text(self.control(editor, cid=20, cls="TextBox")),
                  "link": self.win.text(self.control(editor, cid=16, cls="TextBox"))}
        # The value field is a read-only result. The supported native mechanism
        # is a constant parameter link, which the simulator evaluates and saves.
        self.set_text(self.control(editor, cid=16, cls="TextBox"), str(value))
        # Merely changing WM_GETTEXT's buffer is insufficient: the native
        # evaluator must accept the expression into the application's model.
        self.win.send(self.control(editor, cid=15, text="Evaluate Link", cls="CommandButton"), 0xF5)
        self.press(self.control(editor, text="OK", cls="CommandButton"))
        self.wait(lambda: not self.win.u.IsWindow(editor), "parameter edit to commit")
        after = self.parameters(token)["parameters"][index]
        try:
            correct = (after["link"].strip() == str(value).strip()
                       and math.isclose(float(after["value"]), numeric, rel_tol=1e-11, abs_tol=1e-14))
        except ValueError:
            correct = False
        if not correct:
            raise BridgeError(f"Parameter did not verify after reopening the native editor: {after}")
        return {"verified": True, "token": token, "label": label, "parameter": after["name"],
                "before": before, "after": after, "method": "native constant global parameter link",
                "saved": False}

    def clear_parameter_link(self, token, parameter):
        editor, label = self.parameter_editor(token)
        listing = self.control(editor, cid=22, cls="ListBox")
        names = self.win.describe(listing).get("items", [])
        matches = [i for i, name in enumerate(names)
                   if name.split("\t", 1)[0].rstrip().casefold() == parameter.casefold()]
        if len(matches) != 1:
            self.press(self.control(editor, text="Cancel", cls="CommandButton"))
            self.wait(lambda: not self.win.u.IsWindow(editor), "parameter editor to close")
            raise BridgeError(f"Parameter name must match exactly; available names: {names}")
        index = matches[0]
        self.select_list(listing, index)
        before = self.win.text(self.control(editor, cid=16, cls="TextBox"))
        self.press(self.control(editor, cid=14, text="Clear Link", cls="CommandButton"))
        self.wait(lambda: self.win.text(self.control(editor, cid=16, cls="TextBox")).strip() == "None",
                  "native parameter link to clear")
        self.press(self.control(editor, text="OK", cls="CommandButton"))
        self.wait(lambda: not self.win.u.IsWindow(editor), "parameter link removal to commit")
        after = self.parameters(token)["parameters"][index]
        if after["link"].strip() != "None":
            raise BridgeError("Parameter link removal failed readback verification")
        return {"verified": True, "token": token, "label": label, "before_link": before,
                "after": after, "saved": False}

    def file_dialog(self, path):
        def ready_dialog():
            self.dismiss_startup_notices()
            return self.dialog(cls="#32770")
        dialog = self.wait(ready_dialog, "native file dialog")
        def filename_edit():
            edits = [h for h in self.win.children(dialog)
                     if self.win.cls(h) == "Edit" and self.win.u.IsWindowVisible(h)
                     and self.win.u.GetDlgCtrlID(h) in (1001, 1152)]
            return edits[0] if len(edits) == 1 else None
        # The Explorer save dialog becomes visible before its filename combo
        # and edit finish initializing, especially on consecutive exports.
        edit = self.wait(filename_edit, "unique native filename edit control")
        self.set_text(edit, str(path))
        self.press(self.control(dialog, cid=1, cls="Button"))
        self.wait(lambda: not self.win.u.IsWindow(dialog), "file dialog to accept the filename")

    def wait_file(self, path, kind):
        def complete():
            if not path.exists() or not self.win.file_writes_closed(path):
                return False
            data = path.read_bytes()
            if not data:
                return False
            if kind == "wmf":
                start = 22 if data.startswith(b"\xd7\xcd\xc6\x9a") else 0
                if len(data) < start + 18:
                    return False
                words = struct.unpack_from("<I", data, start + 6)[0]
                if len(data) != start + words * 2 or not data.endswith(b"\x03\x00\x00\x00\x00\x00"):
                    return False
            if kind == "svu":
                if not data.startswith(b"SystemView/System File"):
                    return False
                length = re.search(rb"SVU_BYTES%\s*(\d+)SVU_BYTES_END%", data[:2048])
                if length and int(length[1]) != len(data):
                    return False
            return data
        return self.wait(complete, f"complete, closed native {kind} file")

    def export(self, plot_name, output):
        output = Path(output).resolve()
        if output.exists():
            raise BridgeError(f"Refusing to overwrite an existing output: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        is_csv = output.suffix.casefold() == ".csv"
        raw = output.with_suffix(".sv.txt") if is_csv else output
        if raw.exists():
            raise BridgeError(f"Native export path already exists: {raw}")
        matches = [p for p in self.plots() if p["text"].split(":", 1)[0] == plot_name]
        if len(matches) != 1:
            raise BridgeError(f"Expected one plot named {plot_name}; run first and inspect the plot list")
        plot = matches[0]
        parent = self.win.u.GetParent(plot["hwnd"])
        if self.win.cls(parent) != "MDIClient":
            raise BridgeError("Plot is not a native MDI child")
        self.win.send(parent, 0x222, plot["hwnd"])
        if self.win.send(parent, 0x229) != plot["hwnd"]:
            raise BridgeError("The requested plot did not become the active native window")
        labels = {}
        for cid, name in [(9, "title"), (10, "y_label"), (11, "x_label")]:
            labels[name] = self.win.text(self.control(plot["hwnd"], cid=cid, cls="TextBox", visible=False))
        self.menu("analysis", "File/Export Active Window as Data")

        def export_dialog():
            def suitable(hwnd):
                captions = [self.win.normalize(self.win.text(c)) for c in self.win.children(hwnd)]
                return "select file" in captions and "data format" in captions and "text" in captions
            return self.dialog(cls="ThunderRT6FormDC", predicate=suitable)

        editor = self.wait(export_dialog, "native data export options")
        option = self.control(editor, text="Text", cls="OptionButton")
        self.press(option)
        self.wait(lambda: self.win.send(option, 0xF0) == 1, "native Text export format selection")
        self.press(self.control(editor, text="Select File", cls="CommandButton"))
        self.file_dialog(raw)
        self.wait(lambda: self.win.text(editor).casefold() == str(raw).casefold(), "native export filename readback")
        self.press(self.control(editor, text="OK", cls="CommandButton"))

        def exported():
            for hwnd in self.win.windows(self.state["pid"]):
                if self.win.u.IsWindowVisible(hwnd) and self.win.u.IsWindowEnabled(hwnd):
                    texts = [self.win.text(c) for c in self.win.children(hwnd)]
                    if any("Do you want to export both X and Y data?" in t for t in texts):
                        self.press(self.control(hwnd, text="X And Y Axis", cls="CommandButton"))
                        return False
            return raw.exists() and raw.stat().st_size > 0 and not self.win.u.IsWindow(editor)

        self.wait(exported, "native X/Y data export")
        data = self.wait_file(raw, "text")
        rows = [line.split() for line in data.decode("ascii").splitlines() if line.strip()]
        if not rows or any(len(row) != 2 for row in rows):
            raise BridgeError("Native export did not contain exactly two columns of X/Y data")
        values = [(float(x), float(y)) for x, y in rows]
        if not all(math.isfinite(v) for pair in values for v in pair):
            raise BridgeError("Native export contains non-finite values")
        if is_csv:
            with output.open("x", newline="", encoding="utf-8") as stream:
                writer = csv.writer(stream)
                writer.writerow(["x", "y"])
                writer.writerows(rows)
        return {"verified": True, "plot": plot["text"], **labels, "rows": len(rows),
                "x_start": values[0][0], "x_end": values[-1][0],
                "y_min": min(y for x, y in values), "y_max": max(y for x, y in values),
                "path": str(output), "native_path": str(raw),
                "sha256": hashlib.sha256(output.read_bytes()).hexdigest()}

    def save_as(self, output):
        output = Path(output).resolve()
        if output.suffix.casefold() != ".svu" or output.exists():
            raise BridgeError("save-as requires a new .svu filename")
        output.parent.mkdir(parents=True, exist_ok=True)
        self.menu("design", "File/Save System As")
        self.file_dialog(output)
        def metadata_ready():
            info = self.dialog("SystemView File Information")
            if info:
                self.press(self.control(info, text="OK", cls="CommandButton"))
                return False
            return output.exists()
        self.wait(metadata_ready, "first-save file information to commit")
        self.wait_file(output, "svu")
        self.wait(lambda: self.win.text(self.frame("design")).casefold() == ("SystemView - " + str(output)).casefold(),
                  "saved project title readback")
        if not output.read_bytes().startswith(b"SystemView/System File"):
            raise BridgeError("Saved file does not have a valid SystemView project signature")
        self.state["project"] = str(output)
        self.state_path.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"verified": True, "path": str(output), "bytes": output.stat().st_size,
                "sha256": hashlib.sha256(output.read_bytes()).hexdigest()}

    def export_image(self, plot_name, output):
        output = Path(output).resolve()
        if output.suffix.casefold() != ".wmf" or output.exists():
            raise BridgeError("export-image requires a new .wmf filename")
        output.parent.mkdir(parents=True, exist_ok=True)
        matches = [p for p in self.plots() if p["text"].split(":", 1)[0] == plot_name]
        if len(matches) != 1:
            raise BridgeError(f"Expected one native plot named {plot_name}")
        plot = matches[0]
        parent = self.win.u.GetParent(plot["hwnd"])
        if self.win.cls(parent) != "MDIClient":
            raise BridgeError("Plot is not a native MDI child")
        self.win.send(parent, 0x222, plot["hwnd"])
        if self.win.send(parent, 0x229) != plot["hwnd"]:
            raise BridgeError("Requested plot did not become active")
        self.menu("analysis", "File/Export Active Window as Metafile")
        self.file_dialog(output)
        data = self.wait_file(output, "wmf")
        signature = data[:4]
        if signature not in (b"\xd7\xcd\xc6\x9a", b"\x01\x00\x09\x00", b"\x02\x00\x09\x00"):
            raise BridgeError(f"Unexpected Windows metafile signature: {signature.hex()}")
        return {"verified": True, "plot": plot["text"], "path": str(output),
                "bytes": output.stat().st_size, "sha256": hashlib.sha256(output.read_bytes()).hexdigest()}


def launch(args):
    project = Path(args.project).resolve(strict=True)
    exe = Path(args.exe).resolve(strict=True) if args.exe else get_engine()
    if project.suffix.lower() != ".svu" or not project.read_bytes().startswith(b"SystemView/System File"):
        raise BridgeError("Project must be a valid SystemView .svu file")
    state_path = Path(args.state).resolve()
    if state_path.exists() and state_path.stat().st_size:
        try:
            Session(state_path)
        except (BridgeError, OSError, ValueError, KeyError):
            pass
        else:
            raise BridgeError("State file already points to a live session; use a different --state")
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0
    proc = subprocess.Popen([str(exe), str(project)], cwd=str(exe.parent), startupinfo=startup)
    win = Win()
    deadline = time.monotonic() + args.timeout
    try:
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise BridgeError(f"SystemView exited during startup: {proc.returncode}")
            for hwnd in win.windows(proc.pid):
                title = win.text(hwnd)
                if title == "SystemView Tip":
                    buttons=[h for h in win.children(hwnd) if win.u.IsWindowVisible(h) and
                             win.normalize(win.text(h))=='close' and 'button' in win.cls(h).casefold()]
                    if len(buttons)==1:win.post(buttons[0],0xF5)
                if title == "Recent SystemView Files":
                    win.post(hwnd, 0x10)
                if win.cls(hwnd) == "#32770":
                    messages = [win.text(x) for x in win.children(hwnd)]
                    if any("error loading SystemView" in x for x in messages):
                        raise BridgeError("SystemView startup failed: " + " | ".join(messages)
                                          + "; run this bridge on the normal Windows desktop")
                if title.startswith("SystemView - "):
                    if title.casefold() != ("SystemView - " + str(project)).casefold():
                        raise BridgeError(f"SystemView opened a different project: {title}")
                    state = {**win.identity(proc.pid), "project": str(project),
                             "original_sha256": hashlib.sha256(project.read_bytes()).hexdigest()}
                    state_path.parent.mkdir(parents=True, exist_ok=True)
                    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
                    return {"started": True, "state": str(state_path), **Session(state_path).snapshot()}
            time.sleep(.15)
        raise BridgeError("Timed out waiting for the SystemView design window")
    except BaseException:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=5)
        raise


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--state", default=str(default_state()))
    commands = root.add_subparsers(dest="command", required=True)
    start = commands.add_parser("start", help="Start a separate SystemView process and open a project")
    start.add_argument("project")
    start.add_argument("--exe", default=None)
    start.add_argument("--timeout", type=float, default=35)
    inspect = commands.add_parser("inspect", help="Read native windows and controls")
    inspect.add_argument("--children", action="store_true")
    menus = commands.add_parser("menus", help="Read current menu paths and enabled states")
    menus.add_argument("--window", choices=["design", "analysis"], default="design")
    run = commands.add_parser("run", help="Run the real simulator synchronously and generate plots")
    run.add_argument("--timeout", type=float, default=30)
    commands.add_parser("plots", help="List real simulation plot windows")
    commands.add_parser("tokens", help="Read actual token numbers and descriptions")
    params = commands.add_parser("params", help="Read a token's native numeric parameters and links")
    params.add_argument("token", type=int)
    setter = commands.add_parser("param-set", help="Set a numeric parameter using a native constant link; verify after reopening")
    setter.add_argument("token", type=int)
    setter.add_argument("parameter")
    setter.add_argument("value")
    clear = commands.add_parser("param-clear", help="Remove a selected parameter's global link")
    clear.add_argument("token", type=int)
    clear.add_argument("parameter")
    export = commands.add_parser("export", help="Export a specific real plot, with X/Y columns and numerical validation")
    export.add_argument("plot", help="Plot ID, e.g. w0 or w2")
    export.add_argument("output", help="New .csv file or a native whitespace-separated text file")
    image = commands.add_parser("export-image", help="Export the actual SystemView plot as a vector WMF")
    image.add_argument("plot")
    image.add_argument("output")
    png = commands.add_parser("export-png", help="Render a verified native plot in its actual screen colors")
    png.add_argument("plot")
    png.add_argument("output")
    save = commands.add_parser("save-as", help="Save a new .svu through SystemView itself")
    save.add_argument("output")
    menu = commands.add_parser("menu", help="Invoke one exact native menu path; inspect its outcome afterwards")
    menu.add_argument("path")
    menu.add_argument("--window", choices=["design", "analysis"], default="design")
    text = commands.add_parser("set-text", help="Set an edit control's text and verify it by reading it back")
    text.add_argument("hwnd", type=lambda x: int(x, 0))
    text.add_argument("value")
    click = commands.add_parser("click", help="Invoke a native button using BM_CLICK")
    click.add_argument("hwnd", type=lambda x: int(x, 0))
    select = commands.add_parser("select", help="Select an item in a native list or combo box")
    select.add_argument("hwnd", type=lambda x: int(x, 0))
    select.add_argument("index", type=int)
    commands.add_parser("close", help="Request a normal close; unsaved changes still require a dialog response")
    return root


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    args = parser().parse_args()
    try:
        if args.command == "start":
            result = launch(args)
        else:
            session = Session(args.state)
            win = session.win
            if args.command == "inspect":
                result = session.snapshot(args.children)
            elif args.command == "menus":
                result = win.menus(session.frame(args.window))
            elif args.command == "menu":
                result = session.menu(args.window, args.path)
            elif args.command == "run":
                result = session.run(args.timeout)
            elif args.command == "plots":
                result = session.plots()
            elif args.command == "tokens":
                result = session.tokens()
            elif args.command == "params":
                result = session.parameters(args.token)
            elif args.command == "param-set":
                result = session.set_parameter(args.token, args.parameter, args.value)
            elif args.command == "param-clear":
                result = session.clear_parameter_link(args.token, args.parameter)
            elif args.command == "export":
                result = session.export(args.plot, args.output)
            elif args.command == "export-image":
                result = session.export_image(args.plot, args.output)
            elif args.command == "export-png":
                from svapi.render import render_plot
                result = render_plot(session, args.plot, args.output)
            elif args.command == "save-as":
                result = session.save_as(args.output)
            elif args.command == "set-text":
                hwnd = session.handle(args.hwnd)
                if not any(x in win.cls(hwnd).casefold() for x in ("textbox", "edit", "combobox")):
                    raise BridgeError("set-text requires an edit/text/combo control")
                before = win.text(hwnd)
                buf = C.create_unicode_buffer(args.value)
                win.send(hwnd, 0xC, 0, C.addressof(buf))
                actual = win.text(hwnd)
                if actual != args.value:
                    raise BridgeError(f"Text verification failed: expected {args.value!r}, got {actual!r}")
                result = {"verified": True, "hwnd": hwnd, "before": before, "after": actual}
            elif args.command == "click":
                hwnd = session.handle(args.hwnd)
                if "button" not in win.cls(hwnd).casefold():
                    raise BridgeError("click requires a native button control")
                if not win.u.IsWindowEnabled(hwnd):
                    raise BridgeError("Button is disabled")
                win.post(hwnd, 0xF5)
                result = {"accepted": True, "completed": False, "hwnd": hwnd}
            elif args.command == "select":
                hwnd = session.handle(args.hwnd)
                cls = win.cls(hwnd).casefold()
                if "listbox" in cls:
                    message, get, notice = 0x186, 0x188, 1
                elif "combobox" in cls:
                    message, get, notice = 0x14E, 0x147, 1
                else:
                    raise BridgeError("select requires a list/combo box")
                if args.index < 0 or win.send(hwnd, message, args.index) < 0:
                    raise BridgeError("Invalid selection index")
                if win.send(hwnd, get) != args.index:
                    raise BridgeError("Selection verification failed")
                parent = win.u.GetParent(hwnd)
                win.post(parent, 0x111, (notice << 16) | (win.u.GetDlgCtrlID(hwnd) & 0xffff), hwnd)
                result = {"verified": True, "hwnd": hwnd, "selected": args.index}
            elif args.command == "close":
                win.post(session.frame("design"), 0x10)
                result = {"accepted": True, "completed": False, "pid": session.state["pid"]}
        print(json.dumps({"ok": True, "result": result}, ensure_ascii=False, indent=2))
    except (BridgeError, OSError, ValueError, KeyError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False, indent=2))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
