from __future__ import annotations

import base64
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def test_reference_image_blob_fields_store_small_image():
    import backend.main as backend_main

    image_bytes = b"stable-image-bytes"
    fields = backend_main.build_reference_image_blob_fields(image_bytes, "image/png")

    assert fields["image_blob_saved"] is True
    assert fields["image_mime_type"] == "image/png"
    assert fields["image_size_bytes"] == len(image_bytes)
    assert base64.b64decode(fields["image_blob_base64"]) == image_bytes


def test_restore_generated_image_from_record(tmp_path):
    import backend.main as backend_main

    original_generated_image_dir = backend_main.GENERATED_IMAGE_DIR
    image_bytes = b"stable-kim-eunji-reference-image"
    filename = "safe182_fallback_kim_eunji_20021112.png"

    backend_main.GENERATED_IMAGE_DIR = tmp_path

    try:
        restored = backend_main.restore_generated_image_from_record(
            {
                "reference_image_url": f"/generated/{filename}",
                "image_blob_base64": base64.b64encode(image_bytes).decode("utf-8"),
            }
        )
    finally:
        backend_main.GENERATED_IMAGE_DIR = original_generated_image_dir

    assert restored is True
    assert (tmp_path / filename).read_bytes() == image_bytes


if __name__ == "__main__":
    import tempfile

    test_reference_image_blob_fields_store_small_image()
    with tempfile.TemporaryDirectory() as directory:
        test_restore_generated_image_from_record(Path(directory))
    print("reference image cache tests passed")

