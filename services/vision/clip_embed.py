# services/vision/clip_embed.py
import os
import torch
from typing import List
from PIL import Image

# import clip lazily to avoid heavy import at module load time
# (some CLIP installs expose module name 'clip')
try:
    import clip  # type: ignore
except Exception:
    clip = None  # we'll raise if used and not available

_device = "cuda" if torch.cuda.is_available() else "cpu"

# module-level cache
_MODEL = None
_PREPROCESS = None

def _ensure_model():
    global _MODEL, _PREPROCESS, clip
    if _MODEL is not None and _PREPROCESS is not None:
        return
    if clip is None:
        raise RuntimeError("clip package not available. Install via: pip install git+https://github.com/openai/CLIP.git")
    # try local model file first
    local_path = os.path.join(os.getcwd(), "models", "clip", "ViT-B-32.pt")
    try:
        if os.path.exists(local_path):
            _MODEL, _PREPROCESS = clip.load(local_path, device=_device)
        else:
            _MODEL, _PREPROCESS = clip.load("ViT-B/32", device=_device)
    except Exception:
        # fallback to standard load
        _MODEL, _PREPROCESS = clip.load("ViT-B/32", device=_device)
    _MODEL.to(_device); _MODEL.eval()

def embed_image(img_path: str):
    """
    Lazily loads CLIP model on first call and returns a list (vector).
    """
    _ensure_model()
    image = Image.open(img_path).convert("RGB")
    image_t = _PREPROCESS(image).unsqueeze(0).to(_device)
    with torch.no_grad():
        feats = _MODEL.encode_image(image_t)
    return feats.cpu().numpy()[0].tolist()

def embed_texts(texts: List[str]):
    """
    Lazily loads CLIP model on first call and returns vectors for texts.
    """
    _ensure_model()
    tokens = clip.tokenize(texts).to(_device)
    with torch.no_grad():
        feats = _MODEL.encode_text(tokens)
    return feats.cpu().numpy().tolist()
