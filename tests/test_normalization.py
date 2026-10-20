import importlib.util
from pathlib import Path
import unittest
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location("normalize_rvc", Path(__file__).resolve().parents[1] / "scripts/normalize-rvc-model.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Tensor:
    def __init__(self, shape=(1, 256), finite=True):
        self.shape, self.finite = shape, finite
        self.device = SimpleNamespace(type="cpu")
        self.layout, self.dtype = "strided", "float16"
        self.ndim = len(shape)

    def numel(self):
        import math
        return math.prod(self.shape)

    def detach(self):
        return self

    def contiguous(self):
        return self

    def clone(self):
        return Tensor(self.shape, self.finite)


torch = SimpleNamespace(Tensor=Tensor, strided="strided", float16="float16", float32="float32", float64="float64",
                        isfinite=lambda t: SimpleNamespace(all=lambda: t.finite))


def valid():
    return {"weight": {"emb_g.weight": Tensor()}, "version": "v2", "f0": 1,
            "config": [1025, 32, 192, 192, 768, 2, 6, 3, 0.0, "1", [3, 7, 11],
                       [[1, 3, 5], [1, 3, 5], [1, 3, 5]], [12, 10, 2, 2], 512, [24, 20, 4, 4], 1, 256, 48000]}


class NormalizationTests(unittest.TestCase):
    def test_only_standard_data_is_copied_and_unknown_fields_are_removed(self):
        cpt = valid()
        cpt["unrelated_metadata"] = object()
        result = module.normalize(cpt, torch)
        self.assertEqual(set(result), {"weight", "config", "version", "f0", "sr"})
        self.assertEqual(result["sr"], "48k")
        self.assertIsNot(result["weight"]["emb_g.weight"], cpt["weight"]["emb_g.weight"])

    def test_custom_tensor_and_dictionary_subclasses_are_rejected(self):
        class CustomTensor(Tensor):
            pass
        cpt = valid()
        cpt["weight"]["emb_g.weight"] = CustomTensor()
        with self.assertRaises(ValueError):
            module.normalize(cpt, torch)
        class CustomDict(dict):
            pass
        with self.assertRaises(ValueError):
            module.normalize(CustomDict(valid()), torch)

    def test_bad_shape_nonfinite_and_training_checkpoints_are_rejected(self):
        for tensor in (Tensor((100000, 256)), Tensor((1, 256), False), Tensor((2, 256))):
            cpt = valid()
            cpt["weight"]["emb_g.weight"] = tensor
            with self.assertRaises(ValueError):
                module.normalize(cpt, torch)
        with self.assertRaises(ValueError):
            module.normalize({"model": {}, "optimizer": {}}, torch)

    def test_config_cannot_smuggle_objects_or_nonfinite_values(self):
        for value in (object(), float("nan"), float("inf"), True, "arbitrary", [-1], [[[[[[1]]]]]]):
            with self.subTest(value=type(value).__name__), self.assertRaises(ValueError):
                module.plain_config(value)
