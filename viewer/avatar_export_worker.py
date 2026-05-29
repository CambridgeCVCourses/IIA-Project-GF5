from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Any

from scene_render import export_avatar_scene_video


def emit(event: dict[str, Any]) -> None:
    print(json.dumps(event), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a final-avatar scene video for the GF5 scene editor.")
    parser.add_argument("--input", required=True, help="Path to the JSON render job payload.")
    args = parser.parse_args()

    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    scene = payload["scene"]
    avatar_assets = payload["avatar_assets"]
    project_root = Path(payload["project_root"])
    output_dir = Path(payload["output_dir"])

    def progress(frame: int, frames: int) -> None:
        emit({"type": "progress", "frame": frame, "frames": frames})

    try:
        video_path = export_avatar_scene_video(
            scene,
            output_dir,
            avatar_assets,
            project_root,
            progress_callback=progress,
        )
    except Exception as exc:
        emit({"type": "error", "error": str(exc)})
        traceback.print_exc()
        return 1
    emit({"type": "done", "video_path": str(video_path)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
