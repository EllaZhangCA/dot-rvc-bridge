"""Device inventory; enumeration never opens a microphone or playback stream."""

from .errors import BridgeError


def devices() -> dict:
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise BridgeError("audio_dependency_missing", '请运行 scripts/setup.ps1 安装 audio 依赖。') from exc
    apis = sd.query_hostapis()
    default_in, default_out = sd.default.device
    return {"default_input_id": default_in, "default_output_id": default_out, "devices": [
        {"id": i, "name": d["name"], "host_api": apis[d["hostapi"]]["name"],
         "inputs": d["max_input_channels"], "outputs": d["max_output_channels"],
         "default_sample_rate": d["default_samplerate"]}
        for i, d in enumerate(sd.query_devices())
    ]}


def test_cable() -> dict:
    """Send a quiet known tone ONLY to VB-CABLE and capture ONLY its output.

    No speaker/microphone fallback. Audio remains in memory and is discarded.
    This checks the driver, not RVC conversion, speaker playback, or latency.
    """
    from array import array
    import math
    import threading
    listing = devices()["devices"]
    import sounddevice as sd
    chosen = []
    for name, field in (("CABLE Output (VB-Audio Virtual Cable)", "inputs"),
                        ("CABLE Input (VB-Audio Virtual Cable)", "outputs")):
        found = [d for d in listing if d["name"] == name and d["host_api"] == "Windows WASAPI" and d[field] >= 2]
        if len(found) != 1:
            raise BridgeError("cable_missing", f"无法唯一定位 WASAPI {name}。")
        chosen.append(found[0]["id"])
    rate, frequency, total = 48000, 997, 96000
    tone = array("h")
    for frame in range(total):
        # A finite tone surrounded by silence lets the last samples drain.
        value = int(655 * math.sin(2 * math.pi * frequency * frame / rate)) if 12000 <= frame < 60000 else 0
        tone.extend((value, value))
    data = tone.tobytes()
    captured, stream_warnings = [], []
    done = threading.Event()
    position = 0

    def callback(indata, outdata, frames, time_info, status):
        nonlocal position
        if status:
            stream_warnings.append(str(status))
        captured.append(bytes(indata))
        chunk = data[position * 4:(position + frames) * 4]
        outdata[:] = chunk + b"\0" * (frames * 4 - len(chunk))
        position += frames
        if position >= total:
            done.set()

    try:
        with sd.RawStream(device=tuple(chosen), samplerate=rate, channels=2,
                          dtype="int16", blocksize=1024, callback=callback):
            if not done.wait(5):
                raise BridgeError("cable_test_timeout", "虚拟线测试超时。")
    except sd.PortAudioError as exc:
        raise BridgeError("cable_device_error", f"无法打开虚拟线：{exc}") from exc
    samples = array("h")
    samples.frombytes(b"".join(captured))
    mono = samples[::2]
    strongest = 0.0
    for start in range(0, len(mono) - 4096, 4096):
        block = mono[start:start + 4096]
        real = sum(v * math.cos(2 * math.pi * frequency * n / rate) for n, v in enumerate(block))
        imag = sum(v * math.sin(2 * math.pi * frequency * n / rate) for n, v in enumerate(block))
        strongest = max(strongest, 2 * math.hypot(real, imag) / (4096 * 32768))
    return {"cable_signal_verified": strongest > 0.002, "tone_hz": frequency,
            "received_tone_amplitude": round(strongest, 5), "sample_rate": rate,
            "warnings": stream_warnings[:5], "audio_saved": False,
            "rvc_conversion_verified": False, "dot_integration_verified": False}
