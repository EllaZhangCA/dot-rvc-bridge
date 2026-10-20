"""Process-local overlay for the pinned engine; leaves its checkout unchanged."""
import hashlib
import io
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from dot_rvc.safe_model_yukina import BUNDLE_SHA256, load_tensors, read_bundle
from dot_rvc.safe_api import validate_setting

SOURCE_HASHES = {
    "voice_changer/VoiceChangerManager.py": "feb4ddf9e09de013199a1bf08d296e1b2fa47d10215f317198beaa597a682f46",
    "voice_changer/ModelSlotManager.py": "aa17281376d4a4d3f7ea18e186d3158cdbec5fea86681e32812df5781433f9c2",
    "data/ModelSlot.py": "468bd1fdc3b303b91bead0e6c847b8c867ff0c2bc5a9c72af80e8d58f6e1900a",
    "voice_changer/RVC/inferencer/InferencerManager.py": "5a1e960cf3a55b0c2dc97a4b9b96a5f87c76d332c2c3a91e35d3ecabd11d7ebf",
    "voice_changer/RVC/inferencer/RVCInferencerv2.py": "b8d53a04f0f3dc0ed4e306ddcbf405c68060be0fccef910b3538e252b18bb553",
    "voice_changer/RVC/pipeline/PipelineGenerator.py": "e924947863d04ed8298e19c61bb3fc96a73c74a4e76390277b942a66bb927b47",
    "voice_changer/Local/ServerDevice.py": "aa64b1c0811937184f05edfcdbca2925e4127d3f31d82e5d2aefda461e5e9d28",
    "MMVCServerSIO.py": "8c2ca051e65c36ec7445ffa1fcf34ac3eabf8f9bed24b49d830fd2ffc719065f",
}
BASE_ASSETS = {
    "hubert_base.pt": (189507909, "f54b40fd2802423a5643779c4861af1e9ee9c1564dc9d32f54f20b5ffba7db96"),
    "rmvpe.pt": (181184272, "6d62215f4306e3ca278246188607209f09af3dc77ed4232efdd069798c4ec193"),
}


def install_checkpoint_guard(torch, source):
    """Legacy loader may see only the two previously installed fixed base assets.

    Character data never enters this function. No added pickle globals/classes.
    Hash the bytes actually sent to the existing loader, including file handles.
    """
    original = torch.load
    allowed = {(Path(source) / "pretrain" / name).resolve(): item for name, item in BASE_ASSETS.items()}
    audit = []
    def guarded(file, *args, **kwargs):
        name = file if isinstance(file, (str, Path)) else getattr(file, "name", None)
        if not isinstance(name, (str, Path)):
            raise ValueError("Unidentified checkpoint loading is disabled")
        path = Path(name)
        item = allowed.get(path.resolve())
        if item is None or path.is_symlink():
            raise ValueError("Character/unknown checkpoint deserialization is disabled")
        size, expected = item
        if hasattr(file, "read"):
            file.seek(0)
            data = file.read(size + 1)
        else:
            with path.open("rb") as stream:
                data = stream.read(size + 1)
        if len(data) != size or hashlib.sha256(data).hexdigest() != expected:
            raise ValueError("Base asset identity mismatch")
        audit.append(path.name)
        return original(io.BytesIO(data), *args, **kwargs)
    torch.load = guarded
    torch.serialization.load = guarded
    return audit


def install(root, source):
    root, source = Path(root).resolve(), Path(source).resolve()
    profile = root / "runtime/safe-service-yukina"
    model_dir = profile / "model_dir"
    bundle = model_dir / "0/yukina.rvcd"
    for relative, expected in SOURCE_HASHES.items():
        if hashlib.sha256((source / relative).read_bytes()).hexdigest() != expected:
            raise ValueError("Pinned upstream source changed: " + relative)
    read_bundle(bundle)  # Verify before any upstream import/initialization.
    sys.path.insert(0, str(source))
    import torch
    audit = install_checkpoint_guard(torch, source)
    import const
    const.STORED_SETTING_FILE = str(profile / "stored_setting.json")
    const.UPLOAD_DIR = str(profile / "upload_dir")
    const.MODEL_DIR = str(profile / "logs")
    const.MODEL_DIR_STATIC = str(profile / "no_static_models")
    const.TMP_DIR = str(profile / "tmp_dir")
    from const import EnumInferenceTypes
    import data.ModelSlot as slots

    def safe_slots(directory):
        if Path(directory).resolve() != model_dir:
            raise ValueError("Unexpected model directory")
        return [slots.RVCModelSlot(slotIndex=0, name="Minato Yukina (voice pending audition)",
            modelFile="yukina.rvcd", indexFile="", defaultTune=0, defaultIndexRatio=0,
            isONNX=False, modelType=EnumInferenceTypes.pyTorchRVCv2.value,
            samplingRate=40000, f0=True, embChannels=768, embOutputLayer=12,
            useFinalProj=False, embedder="hubert_base", version="v2",
            speakers={0: "sid 0 (unverified voice)"})]
    slots.loadAllSlotInfo = safe_slots

    from voice_changer.RVC.inferencer.RVCInferencerv2 import RVCInferencerv2
    from voice_changer.RVC.inferencer.InferencerManager import InferencerManager
    from voice_changer.RVC.deviceManager.DeviceManager import DeviceManager
    from voice_changer.RVC.inferencer.rvc_models.infer_pack.models import SynthesizerTrnMs768NSFsid
    def load_data_model(self, file, gpu):
        if Path(file).resolve() != bundle or Path(file).is_symlink() or gpu not in (-1, 0):
            raise ValueError("Only the provisioned data model is supported")
        checkpoint = load_tensors(bundle)
        self.setProps(EnumInferenceTypes.pyTorchRVCv2, str(bundle), True, gpu)
        device = DeviceManager.get_instance().getDevice(gpu)
        half = DeviceManager.get_instance().halfPrecisionAvailable(gpu)
        model = SynthesizerTrnMs768NSFsid(*checkpoint["config"], is_half=half)
        del model.enc_q  # Training-only encoder absent from exported inference weights.
        model.load_state_dict(checkpoint["weight"], strict=True)
        model.eval().to(device)
        self.model = model.half() if half else model.float()
        return self
    RVCInferencerv2.loadModel = load_data_model
    def load_inferencer(cls, kind, file, gpu, inferencerTypeVersion=None):
        if kind not in (EnumInferenceTypes.pyTorchRVCv2, EnumInferenceTypes.pyTorchRVCv2.value):
            raise ValueError("Other inferencer types are disabled")
        if inferencerTypeVersion not in (None, "v2"):
            raise ValueError("Unsupported inferencer version")
        return RVCInferencerv2().loadModel(file, gpu)
    InferencerManager.loadInferencer = classmethod(load_inferencer)

    import voice_changer.RVC.pipeline.PipelineGenerator as pipeline
    def no_index(path):
        if Path(path).resolve() != bundle.parent:
            raise ValueError("Index parsing is disabled")
        return None
    pipeline._loadIndex = no_index

    import voice_changer.ModelSlotManager as slot_manager
    slot_manager.loadAllSlotInfo = safe_slots
    from voice_changer.VoiceChangerManager import VoiceChangerManager
    import voice_changer.RVC.RVCr2 as rvc
    original_init = rvc.RVCr2.__init__
    def safe_init(self, params, slot):
        if slot != safe_slots(params.model_dir)[0]:
            raise ValueError("Unapproved slot metadata")
        original_init(self, params, slot)
        self.settings.f0Detector = "rmvpe"
        self.settings.tran = 0
        self.settings.gpu = 0
    rvc.RVCr2.__init__ = safe_init

    def disabled(*args, **kwargs):
        raise ValueError("Model mutation/export is disabled in this service profile")
    for method in ("loadModel", "merge_models", "export2onnx", "update_model_info",
                   "update_model_default", "upload_model_assets"):
        setattr(VoiceChangerManager, method, disabled)
    original_update = VoiceChangerManager.update_settings
    def update(self, key, value):
        validate_setting(key, value)
        settings = self.serverDevice.settings
        if settings.serverAudioStated and key not in ("serverAudioStated", "passThrough", "tran", "dstId"):
            raise ValueError("Pause before changing device/model configuration")
        if key == "serverAudioStated" and int(value) == 1:
            if not getattr(getattr(self, "voiceChangerModel", None), "pipeline", None):
                raise ValueError("Pipeline is not ready")
            source_device = self.serverDevice.getServerInputAudioDevice(settings.serverInputDeviceId)
            output_device = self.serverDevice.getServerOutputAudioDevice(settings.serverOutputDeviceId)
            if (source_device is None or source_device.name != "CABLE Output (VB-Audio Virtual Cable)"
                    or source_device.hostAPI != "Windows WASAPI" or output_device is None
                    or output_device.hostAPI != "Windows WASAPI" or "CABLE" in output_device.name
                    or settings.serverMonitorDeviceId != -1 or settings.serverAudioSampleRate != 48000
                    or settings.enableServerAudio != 1):
                raise ValueError("Expected WASAPI cable input, headphones/output, 48 kHz, no monitor")
        return original_update(self, key, value)
    VoiceChangerManager.update_settings = update
    return {"profile": "yukina-data-only-v1", "bundle_sha256": BUNDLE_SHA256,
            "role_checkpoint_pickle": False, "slot": 0, "index_enabled": False,
            "browser_audio_enabled": False, "legacy_base_assets": list(BASE_ASSETS),
            "base_checkpoint_loads": audit}
