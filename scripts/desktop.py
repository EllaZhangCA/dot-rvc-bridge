"""Small bilingual Windows controller; all model/runtime work stays off Tk's thread."""
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from dot_rvc.audio import devices
from dot_rvc.config import Config
from dot_rvc.engine import Engine
from dot_rvc import processes


class Desktop:
    def __init__(self, window):
        self.window = window
        self.events = queue.Queue()
        self.busy = False
        self.process = None
        self.engine = Engine(Config())
        self.buttons = []
        window.title("Dot RVC Bridge · Easy Edition")
        window.geometry("760x510")
        window.minsize(680, 500)
        window.protocol("WM_DELETE_WINDOW", self.close)
        frame = ttk.Frame(window, padding=24)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Dot RVC Bridge", font=("Segoe UI", 22, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Local voice conversion / 本地变声", font=("Segoe UI", 11)).pack(anchor="w", pady=(0, 18))
        self.model = tk.StringVar(value=self.current_model())
        ttk.Label(frame, textvariable=self.model, wraplength=680).pack(anchor="w")
        self.button(frame, "Import .pth / 导入模型", self.import_model).pack(anchor="w", pady=(8, 16))
        ttk.Label(frame, text="Playback device / 变声后播放到").pack(anchor="w")
        row = ttk.Frame(frame)
        row.pack(fill="x", pady=(5, 16))
        self.output = ttk.Combobox(row, state="readonly", width=66)
        self.output.pack(side="left", fill="x", expand=True)
        self.button(row, "Refresh / 刷新", self.refresh).pack(side="right", padx=(8, 0))
        controls = ttk.Frame(frame)
        controls.pack(fill="x")
        ttk.Label(controls, text="Pitch / 音高").pack(side="left")
        self.pitch = tk.StringVar(value="0")
        ttk.Spinbox(controls, from_=-24, to=24, width=5, textvariable=self.pitch).pack(side="left", padx=8)
        self.button(controls, "Apply / 应用", self.apply_pitch).pack(side="left")
        self.original = tk.BooleanVar(value=False)
        self.bypass = ttk.Checkbutton(controls, text="Original voice / 原声", variable=self.original, command=self.apply_bypass)
        self.bypass.pack(side="left", padx=18)
        actions = ttk.Frame(frame)
        actions.pack(fill="x", pady=18)
        self.button(actions, "Start / 开始变声", self.start).pack(side="left")
        self.button(actions, "Pause / 暂停", self.pause).pack(side="left", padx=8)
        self.button(actions, "Stop engine / 关闭引擎", self.stop).pack(side="left")
        ttk.Separator(frame).pack(fill="x", pady=(0, 12))
        ttk.Label(frame, text="Windows volume mixer: Dot's app → CABLE Input\nWindows 音量合成器：将 Dot 所在应用的输出设为 CABLE Input。\nKeep your normal microphone. / 麦克风保持原设备。", wraplength=680).pack(anchor="w")
        self.status = tk.StringVar(value="Ready. Import a model to begin. / 就绪，先导入模型。")
        ttk.Label(frame, textvariable=self.status, wraplength=680).pack(anchor="w", pady=(16, 0))
        self.refresh()
        window.after(100, self.poll)

    def button(self, parent, label, command):
        button = ttk.Button(parent, text=label, command=command)
        self.buttons.append(button)
        return button

    def current_model(self):
        current = ROOT / "runtime/easy-current.json"
        if current.exists():
            return "Model / 模型: " + json.loads(current.read_text(encoding="utf-8"))["name"]
        return "Model / 模型: none / 未导入"

    def refresh(self):
        listing = devices()
        outputs = [d["name"] for d in listing["devices"] if d["host_api"] == "Windows WASAPI"
                   and d["outputs"] > 0 and "cable" not in d["name"].lower()]
        chosen = self.output.get()
        self.output["values"] = outputs
        if chosen not in outputs:
            config = Config.from_env()
            default = next((d["name"] for d in listing["devices"] if d["id"] == listing["default_output_id"]), "")
            matches = [name for name in outputs if default and name.startswith(default)]
            self.output.set(config.output_device if config.output_device in outputs else matches[0] if len(matches) == 1 else "")

    def work(self, label, action, done=None):
        if self.busy:
            return
        self.busy = True
        self.status.set(label)
        for button in [*self.buttons, self.bypass]:
            button.configure(state="disabled")
        def worker():
            try:
                result = action()
                self.events.put((True, result, done))
            except Exception as exc:
                with (ROOT / "runtime/desktop.log").open("a", encoding="utf-8") as log:
                    traceback.print_exc(file=log)
                self.events.put((False, str(exc), None))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            success, result, done = self.events.get_nowait()
            self.busy = False
            for button in [*self.buttons, self.bypass]:
                button.configure(state="normal")
            self.status.set(result if success else "Error / 错误: " + result[:300])
            if success and done:
                done()
            if not success:
                messagebox.showerror("Dot RVC Bridge", result[-3000:])
        except queue.Empty:
            pass
        self.window.after(100, self.poll)

    def ensure_engine(self):
        import httpx
        if self.process is None or self.process.poll() is not None:
            self.process = processes.launch(ROOT)
        deadline = time.monotonic() + 120
        with httpx.Client(trust_env=False, timeout=2) as client:
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise RuntimeError("Engine exited. See runtime/easy-engine.log / 引擎退出，请查看日志。")
                try:
                    response = client.get("http://127.0.0.1:18888/safe_status")
                    response.raise_for_status()
                    status = response.json()
                    current = json.loads((ROOT / "runtime/easy-current.json").read_text(encoding="utf-8"))
                    profile = json.loads((Path(current["directory"]) / "profile.json").read_text(encoding="utf-8"))
                    if status.get("profile") != "easy-rvc-v1" or status.get("bundle_sha256") != profile["sha256"]:
                        raise RuntimeError("Unexpected engine profile / 引擎模型不匹配")
                    return
                except (httpx.ConnectError, httpx.ReadTimeout):
                    time.sleep(0.5)
        raise RuntimeError("Engine startup timed out. See runtime/easy-engine.log / 引擎启动超时。")

    def require_running(self):
        if self.process is None or self.process.poll() is not None:
            raise RuntimeError("Click Start first / 请先点击开始变声")

    def import_model(self):
        path = filedialog.askopenfilename(title="Select RVC v2 f0 .pth / 选择模型", filetypes=[("RVC checkpoint", "*.pth")])
        if not path:
            return
        def action():
            if self.process is not None:
                processes.stop(ROOT)
                self.process = None
            result = subprocess.run([str(ROOT / "runtime/model-check-venv/Scripts/python.exe"),
                                     str(ROOT / "scripts/import-model.py"), path], cwd=ROOT,
                                    capture_output=True, encoding="utf-8", errors="replace",
                                    env={**os.environ, "PYTHONUTF8": "1"}, creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode:
                raise RuntimeError(result.stderr[-2800:] or "Model import failed")
            return "Model imported. Click Start. / 导入完成，点击开始变声。"
        self.work("Importing model... / 正在导入模型…", action, lambda: self.model.set(self.current_model()))

    def start(self):
        output, pitch, original = self.output.get(), self.pitch.get(), self.original.get()
        def action():
            if not output:
                raise RuntimeError("Choose a playback device / 请选择播放设备")
            if not (ROOT / "runtime/easy-current.json").exists():
                raise RuntimeError("Import your .pth first / 请先导入 .pth 模型")
            semitones = int(pitch)
            if not -24 <= semitones <= 24:
                raise ValueError("Pitch must be -24…24 / 音高范围 -24…24")
            self.ensure_engine()
            self.engine.pause_audio()
            self.engine.configure_audio("CABLE Output (VB-Audio Virtual Cable)", output, "Windows WASAPI", 64)
            self.engine.set_pitch(semitones)
            self.engine.set_bypass(original)
            self.engine.start_audio()
            return "Start requested. Listen to Dot to check the result. / 已启动，请播放 Dot 语音试听。"
        self.work("Loading engine... / 正在加载引擎…", action)

    def pause(self):
        def action():
            self.require_running()
            self.engine.pause_audio()
            return "Paused; cable audio is silent. / 已暂停，虚拟线上的声音暂不可听。"
        self.work("Pausing... / 正在暂停…", action)

    def apply_pitch(self):
        value = self.pitch.get()
        def action():
            self.require_running()
            self.engine.set_pitch(int(value))
            return "Pitch updated / 音高已更新"
        self.work("Applying pitch... / 正在应用音高…", action)

    def apply_bypass(self):
        enabled = self.original.get()
        def action():
            if self.process is not None and self.process.poll() is None:
                self.engine.set_bypass(enabled)
            return "Original voice selected / 已选原声" if enabled else "RVC voice selected / 已选变声"
        self.work("Updating mode... / 正在切换…", action)

    def stop(self):
        def action():
            if self.process is not None:
                processes.stop(ROOT)
                self.process = None
            return "Engine stopped. Restore the app output in Windows for normal audio. / 引擎已关闭；恢复正常播放请在 Windows 改回应用输出。"
        self.work("Stopping engine... / 正在关闭引擎…", action)

    def close(self):
        if self.busy:
            self.status.set("Wait for the current operation before closing. / 请等待当前操作完成再关闭。")
            return
        if self.process is not None:
            self.work("Closing... / 正在关闭…", lambda: processes.stop(ROOT) or "Closed", self.window.destroy)
        else:
            self.window.destroy()


def main():
    (ROOT / "runtime").mkdir(exist_ok=True)
    window = tk.Tk()
    try:
        Desktop(window)
        window.mainloop()
    except Exception:
        report = traceback.format_exc()
        (ROOT / "runtime/desktop.log").write_text(report, encoding="utf-8")
        messagebox.showerror("Dot RVC Bridge", report[-3000:])
        raise


if __name__ == "__main__":
    main()
