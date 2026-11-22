"""Экспорт обученной модели MaskablePPO в numpy-файл для программы (app/agent/agent_policy.npz)."""
import hashlib, sys
import numpy as np
from sb3_contrib import MaskablePPO


def export(model_path, out_path):
    m = MaskablePPO.load(model_path, device="cpu")
    pol = m.policy
    lin = [l for l in pol.mlp_extractor.policy_net if l.__class__.__name__ == "Linear"]
    d = {"n_hidden": np.array(len(lin))}
    for i, l in enumerate(lin):
        d[f"W{i}"] = l.weight.detach().numpy().T.astype(np.float32)
        d[f"b{i}"] = l.bias.detach().numpy().astype(np.float32)
    d["Wa"] = pol.action_net.weight.detach().numpy().T.astype(np.float32)
    d["ba"] = pol.action_net.bias.detach().numpy().astype(np.float32)
    np.savez(out_path, **d)
    return hashlib.sha256(open(out_path, "rb").read()).hexdigest()


if __name__ == "__main__":
    print(export(sys.argv[1], sys.argv[2]))
