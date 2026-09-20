"""Image-to-video via Wan 2.2 Lightning on a public HF Space (ZeroGPU)."""
import os
import shutil
import tempfile

SPACE = "Saravutw/WAN2.2_I2V_LIGHTNING_4-8step_custom"
NEG = "blurry, low quality, chaotic, deformed, watermark, bad anatomy, shaky camera view point"


def generate(image_path: str, motion_prompt: str, out_mp4: str, seed: int = 42,
             duration_s: float = 3.5) -> str:
    from gradio_client import Client, handle_file
    token = os.environ.get("HF_TOKEN")
    kwargs = {"hf_token": token} if token else {}
    c = Client(SPACE, **kwargs)
    res = c.predict(
        handle_file(image_path),
        None,
        motion_prompt,
        4,
        NEG,
        duration_s,
        1,
        1,
        seed,
        False,
        5,
        "UniPCMultistep",
        3.0,
        16,
        False,
        True,
        api_name="/generate_video",
    )
    src = res[0]
    if isinstance(src, dict):
        src = src.get("video", {}).get("path") or src.get("path")
    shutil.copy(src, out_mp4)
    return out_mp4
