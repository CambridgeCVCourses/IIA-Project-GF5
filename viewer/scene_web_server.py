from __future__ import annotations

import argparse
import json
import mimetypes
import subprocess
import sys
import tempfile
import threading
import traceback
import urllib.parse
import uuid
import webbrowser
from email.parser import BytesParser
from email.policy import default as email_default_policy
from email.utils import formatdate
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from hy_motion_import import convert_file, safe_motion_filename
from scene_core import (
    DEFAULT_SCENE_STEM,
    default_scene,
    discover_avatar_assets,
    discover_motion_library,
    discover_proxy_assets,
    load_proxy_asset_previews,
    load_scene_file,
    normalize_scene,
    save_scene_file,
    scene_library,
    scene_warnings,
)
from scene_render import avatar_final_export_settings, export_avatar_scene_video, export_scene_video


HY_MOTION_IMPORT_MAX_BYTES = 128 * 1024 * 1024


class SceneEditorServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], project_root: Path) -> None:
        super().__init__(server_address, SceneEditorHandler)
        self.project_root = project_root
        self.static_root = project_root / "viewer" / "scene_editor_web"
        self.scene_dir = project_root / "libraries" / "scenes"
        self.motion_custom_dir = project_root / "libraries" / "motions" / "custom"
        self.export_dir = project_root / "exports" / "scene_videos"
        self.asset_dir = project_root / "assets" / "blocky"
        self.export_jobs: dict[str, dict[str, Any]] = {}
        self.export_jobs_lock = threading.Lock()

    def motion_library(self) -> list[dict[str, Any]]:
        return discover_motion_library(self.project_root)

    def proxy_assets(self) -> list[str]:
        return discover_proxy_assets(self.asset_dir)

    def proxy_asset_previews(self) -> dict[str, dict[str, Any]]:
        return load_proxy_asset_previews(self.asset_dir)

    def avatar_assets(self) -> list[dict[str, str]]:
        return discover_avatar_assets(self.project_root)

    def set_export_job(self, export_job_id: str, **updates: Any) -> None:
        with self.export_jobs_lock:
            job = self.export_jobs.setdefault(export_job_id, {})
            job.update(updates)

    def get_export_job(self, export_job_id: str) -> dict[str, Any] | None:
        with self.export_jobs_lock:
            job = self.export_jobs.get(export_job_id)
            return dict(job) if job is not None else None

    def start_avatar_export_job(
        self,
        *,
        scene: dict[str, Any],
        scene_path: Path,
        mode: str,
        avatar_assets: list[dict[str, str]],
    ) -> str:
        job_id = uuid.uuid4().hex
        export_settings = avatar_final_export_settings(scene)
        resolution_note = f" Rendering at {export_settings['width']}x{export_settings['height']} {export_settings['fps']} fps."
        render_warning = str(export_settings.get("warning", ""))
        if render_warning:
            resolution_note = f" {render_warning}"
        self.set_export_job(
            job_id,
            job_id=job_id,
            status="running",
            mode=mode,
            path=str(scene_path),
            scene=scene,
            scenes=scene_library(self.scene_dir),
            warnings=scene_warnings(scene, self.motion_library()),
            avatar_assets=avatar_assets,
            export=export_settings,
            message=f"Rendering final avatars in the background.{resolution_note}",
            progress={"frame": 0, "frames": 0},
        )

        def update_progress(frame: int, frames: int) -> None:
            suffix = f" {render_warning}" if render_warning else ""
            self.set_export_job(
                job_id,
                progress={"frame": frame, "frames": frames},
                message=f"Rendering final avatars: {frame}/{frames} frames...{suffix}",
            )

        def run() -> None:
            try:
                if sys.platform == "darwin":
                    video_path = self.run_avatar_export_worker(
                        scene=scene,
                        avatar_assets=avatar_assets,
                        progress_callback=update_progress,
                    )
                else:
                    video_path = export_avatar_scene_video(
                        scene,
                        self.export_dir,
                        avatar_assets,
                        self.project_root,
                        progress_callback=update_progress,
                    )
                self.set_export_job(
                    job_id,
                    status="done",
                    video_path=str(video_path),
                    video_url=f"/exports/scene_videos/{urllib.parse.quote(video_path.name)}",
                    message=render_warning or f"Rendered final avatar video {video_path.name}.",
                )
            except Exception as exc:
                traceback.print_exc()
                self.set_export_job(
                    job_id,
                    status="error",
                    error=str(exc),
                    message=f"Final render failed: {exc}",
                )

        thread = threading.Thread(target=run, name=f"scene-export-{job_id[:8]}", daemon=True)
        thread.start()
        return job_id

    def run_avatar_export_worker(
        self,
        *,
        scene: dict[str, Any],
        avatar_assets: list[dict[str, str]],
        progress_callback: Any,
    ) -> Path:
        worker_path = self.project_root / "viewer" / "avatar_export_worker.py"
        payload = {
            "scene": scene,
            "avatar_assets": avatar_assets,
            "project_root": str(self.project_root),
            "output_dir": str(self.export_dir),
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False) as handle:
            json.dump(payload, handle)
            input_path = Path(handle.name)
        command = [sys.executable, str(worker_path), "--input", str(input_path)]
        output_tail: list[str] = []
        worker_error = ""
        video_path: Path | None = None
        try:
            process = subprocess.Popen(
                command,
                cwd=str(self.project_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if process.stdout is not None:
                for line in process.stdout:
                    text = line.strip()
                    if not text:
                        continue
                    try:
                        event = json.loads(text)
                    except json.JSONDecodeError:
                        output_tail.append(text)
                        output_tail = output_tail[-20:]
                        continue
                    event_type = str(event.get("type", ""))
                    if event_type == "progress":
                        progress_callback(int(event.get("frame", 0)), int(event.get("frames", 0)))
                    elif event_type == "done":
                        video_path = Path(str(event.get("video_path", "")))
                    elif event_type == "error":
                        worker_error = str(event.get("error", "Final render worker failed."))
            returncode = process.wait()
            if returncode != 0:
                details = "\n".join(output_tail)
                message = worker_error or f"Final render worker exited with code {returncode}."
                if details:
                    message = f"{message}\n{details}"
                raise RuntimeError(message)
            if video_path is None:
                raise RuntimeError("Final render worker finished without reporting an output video.")
            return video_path
        finally:
            input_path.unlink(missing_ok=True)


class SceneEditorHandler(BaseHTTPRequestHandler):
    server: SceneEditorServer

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[scene-web] {self.address_string()} - {format % args}")

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        try:
            if parsed.path == "/api/bootstrap":
                self.handle_bootstrap()
                return
            if parsed.path == "/api/scenes":
                self.send_json({"scenes": scene_library(self.server.scene_dir)})
                return
            if parsed.path == "/api/load":
                self.handle_load(parsed.query)
                return
            if parsed.path == "/api/export/status":
                self.handle_export_status(parsed.query)
                return
            if parsed.path.startswith("/exports/scene_videos/"):
                self.serve_export(parsed.path)
                return
            self.serve_static(parsed.path)
        except Exception as exc:
            traceback.print_exc()
            self.send_error_json(500, str(exc))

    def do_HEAD(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        try:
            self.serve_static(parsed.path, head_only=True)
        except Exception as exc:
            traceback.print_exc()
            self.send_error_json(500, str(exc))

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        try:
            if parsed.path == "/api/save":
                self.handle_save()
                return
            if parsed.path == "/api/validate":
                self.handle_validate()
                return
            if parsed.path == "/api/import/hy-motion":
                self.handle_import_hy_motion()
                return
            if parsed.path == "/api/export":
                self.handle_export()
                return
            self.send_error_json(404, "Unknown API endpoint.")
        except Exception as exc:
            traceback.print_exc()
            self.send_error_json(500, str(exc))

    def handle_bootstrap(self) -> None:
        motions = self.server.motion_library()
        proxy_assets = self.server.proxy_assets()
        scene = default_scene(motions, proxy_assets)
        self.send_json(
            {
                "motions": motions,
                "proxy_assets": proxy_assets,
                "proxy_asset_previews": self.server.proxy_asset_previews(),
                "avatar_assets": self.server.avatar_assets(),
                "scene": scene,
                "scenes": scene_library(self.server.scene_dir),
                "warnings": scene_warnings(scene, motions),
            }
        )

    def handle_load(self, query: str) -> None:
        params = urllib.parse.parse_qs(query)
        name = params.get("name", [""])[0]
        if not name:
            self.send_error_json(400, "Missing scene name.")
            return
        stem = "".join(ch for ch in name if ch.isalnum() or ch in {"_", "-", "."}).removesuffix(".scene")
        path = self.server.scene_dir / f"{stem}.scene.json"
        if not path.exists():
            self.send_error_json(404, f"Scene '{name}' not found.")
            return
        motions = self.server.motion_library()
        proxy_assets = self.server.proxy_assets()
        scene = load_scene_file(path, motions, proxy_assets)
        self.send_json(
            {
                "scene": scene,
                "avatar_assets": self.server.avatar_assets(),
                "warnings": scene_warnings(scene, motions),
            }
        )

    def handle_save(self) -> None:
        payload = self.read_json_body()
        name = str(payload.get("name", DEFAULT_SCENE_STEM))
        raw_scene = payload.get("scene")
        if not isinstance(raw_scene, dict):
            self.send_error_json(400, "Request body must include a scene object.")
            return
        motions = self.server.motion_library()
        proxy_assets = self.server.proxy_assets()
        scene = normalize_scene(raw_scene, motions, proxy_assets)
        path = save_scene_file(self.server.scene_dir, name, scene)
        self.send_json(
            {
                "ok": True,
                "path": str(path),
                "scene": scene,
                "scenes": scene_library(self.server.scene_dir),
                "avatar_assets": self.server.avatar_assets(),
                "warnings": scene_warnings(scene, motions),
            }
        )

    def handle_validate(self) -> None:
        payload = self.read_json_body()
        raw_scene = payload.get("scene")
        if not isinstance(raw_scene, dict):
            self.send_error_json(400, "Request body must include a scene object.")
            return
        motions = self.server.motion_library()
        proxy_assets = self.server.proxy_assets()
        scene = normalize_scene(raw_scene, motions, proxy_assets)
        self.send_json(
            {
                "scene": scene,
                "avatar_assets": self.server.avatar_assets(),
                "warnings": scene_warnings(scene, motions),
            }
        )

    def handle_import_hy_motion(self) -> None:
        try:
            files = self.read_multipart_files()
        except ValueError as exc:
            self.send_error_json(400, str(exc))
            return
        if len(files) != 2:
            self.send_error_json(400, "Select exactly one HY-Motion .fbx file and its matching .txt prompt file.")
            return

        suffixes = {file["suffix"] for file in files}
        if suffixes != {".fbx", ".txt"}:
            self.send_error_json(400, "HY-Motion import requires one .fbx file and one .txt prompt file.")
            return

        fbx_file = next(file for file in files if file["suffix"] == ".fbx")
        txt_file = next(file for file in files if file["suffix"] == ".txt")
        fbx_name = Path(fbx_file["filename"]).stem
        txt_name = Path(txt_file["filename"]).stem
        if fbx_name != txt_name:
            self.send_error_json(400, "The .fbx and .txt files must have the same base filename.")
            return

        try:
            prompt_text = txt_file["data"].decode("utf-8-sig").strip()
        except UnicodeDecodeError:
            self.send_error_json(400, "The HY-Motion .txt prompt file must be UTF-8 text.")
            return
        if not prompt_text:
            self.send_error_json(400, "The HY-Motion .txt prompt file is empty.")
            return

        safe_stem = safe_motion_filename(Path(fbx_file["filename"]))
        try:
            with tempfile.TemporaryDirectory(prefix="gf5_hy_motion_import_") as temp_dir_name:
                temp_dir = Path(temp_dir_name)
                temp_fbx = temp_dir / f"{safe_stem}.fbx"
                temp_txt = temp_dir / f"{safe_stem}.txt"
                temp_fbx.write_bytes(fbx_file["data"])
                temp_txt.write_text(prompt_text + "\n", encoding="utf-8")
                output_path = convert_file(
                    temp_fbx,
                    output_dir=self.server.motion_custom_dir,
                    motion_name=None,
                    unit_scale=0.01,
                    source_fbx_path=fbx_file["filename"],
                )
        except Exception as exc:
            self.send_error_json(400, f"Could not import HY-Motion FBX: {exc}")
            return
        motions = self.server.motion_library()
        imported_motion = next(
            (
                motion
                for motion in motions
                if motion.get("path") and Path(str(motion["path"])).resolve() == output_path.resolve()
            ),
            None,
        )
        self.send_json(
            {
                "ok": True,
                "path": str(output_path),
                "motion": imported_motion,
                "motions": motions,
                "message": f"Imported {imported_motion.get('label') if imported_motion else output_path.name}",
            }
        )

    def handle_export(self) -> None:
        payload = self.read_json_body()
        name = str(payload.get("name", DEFAULT_SCENE_STEM))
        raw_scene = payload.get("scene")
        if not isinstance(raw_scene, dict):
            self.send_error_json(400, "Request body must include a scene object.")
            return
        raw_scene = dict(raw_scene)
        if isinstance(payload.get("export"), dict):
            raw_scene["export"] = payload["export"]
        motions = self.server.motion_library()
        proxy_assets = self.server.proxy_assets()
        scene = normalize_scene(raw_scene, motions, proxy_assets)
        scene_path = save_scene_file(self.server.scene_dir, name, scene)
        mode = str(payload.get("mode", "blocky_draft"))
        avatar_assets = self.server.avatar_assets()
        if mode == "avatar_final":
            job_id = self.server.start_avatar_export_job(
                scene=scene,
                scene_path=scene_path,
                mode=mode,
                avatar_assets=avatar_assets,
            )
            job = self.server.get_export_job(job_id) or {}
            self.send_json(
                {
                    "ok": True,
                    "job_id": job_id,
                    "status": job.get("status", "running"),
                    "mode": mode,
                    "path": str(scene_path),
                    "scene": scene,
                    "scenes": scene_library(self.server.scene_dir),
                    "warnings": scene_warnings(scene, motions),
                    "avatar_assets": avatar_assets,
                    "export": job.get("export", scene.get("export", {})),
                    "message": job.get("message", "Rendering final avatars in the background."),
                },
                status=202,
            )
            return
        else:
            video_path = export_scene_video(scene, self.server.export_dir, self.server.project_root)
            message = f"Rendered blocky draft {video_path.name}."
        self.send_json(
            {
                "ok": True,
                "mode": mode,
                "path": str(scene_path),
                "scene": scene,
                "scenes": scene_library(self.server.scene_dir),
                "warnings": scene_warnings(scene, motions),
                "avatar_assets": avatar_assets,
                "video_path": str(video_path),
                "video_url": f"/exports/scene_videos/{urllib.parse.quote(video_path.name)}",
                "export": scene.get("export", {}),
                "message": message,
            }
        )

    def handle_export_status(self, query: str) -> None:
        params = urllib.parse.parse_qs(query)
        job_id = params.get("id", [""])[0]
        if not job_id:
            self.send_error_json(400, "Missing export job id.")
            return
        job = self.server.get_export_job(job_id)
        if job is None:
            self.send_error_json(404, "Export job not found.")
            return
        self.send_json(job)

    def read_json_body(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def read_multipart_files(self) -> list[dict[str, Any]]:
        content_length = int(self.headers.get("Content-Length", "0") or "0")
        if content_length <= 0:
            raise ValueError("Missing import files.")
        if content_length > HY_MOTION_IMPORT_MAX_BYTES:
            raise ValueError("HY-Motion import is larger than the 128 MB limit.")
        content_type = self.headers.get("Content-Type", "")
        if not content_type.startswith("multipart/form-data"):
            raise ValueError("HY-Motion import must use multipart form data.")
        body = self.rfile.read(content_length)
        header = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8")
        message = BytesParser(policy=email_default_policy).parsebytes(header + body)
        if not message.is_multipart():
            raise ValueError("HY-Motion import did not contain file parts.")

        files: list[dict[str, Any]] = []
        for part in message.iter_parts():
            raw_filename = part.get_filename()
            if not raw_filename:
                continue
            filename = Path(str(raw_filename).replace("\\", "/")).name
            suffix = Path(filename).suffix.lower()
            data = part.get_payload(decode=True) or b""
            files.append({"filename": filename, "suffix": suffix, "data": data})
        return files

    def serve_static(self, request_path: str, *, head_only: bool = False) -> None:
        if request_path in {"", "/"}:
            request_path = "/index.html"
        relative = Path(urllib.parse.unquote(request_path.lstrip("/")))
        path = (self.server.static_root / relative).resolve()
        if self.server.static_root.resolve() not in path.parents and path != self.server.static_root.resolve():
            self.send_error_json(403, "Forbidden.")
            return
        if not path.exists() or not path.is_file():
            self.send_error_json(404, "File not found.")
            return
        stat = path.stat()
        etag = f'W/"{stat.st_mtime_ns:x}-{stat.st_size:x}"'
        if self.headers.get("If-None-Match") == etag:
            self.send_response(304)
            self.send_header("Cache-Control", "no-cache, must-revalidate")
            self.send_header("ETag", etag)
            self.end_headers()
            return
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache, must-revalidate")
        self.send_header("ETag", etag)
        self.send_header("Last-Modified", formatdate(stat.st_mtime, usegmt=True))
        self.end_headers()
        if not head_only:
            self.wfile.write(data)

    def serve_export(self, request_path: str) -> None:
        filename = Path(urllib.parse.unquote(request_path)).name
        path = (self.server.export_dir / filename).resolve()
        if self.server.export_dir.resolve() not in path.parents:
            self.send_error_json(403, "Forbidden.")
            return
        if not path.exists() or not path.is_file():
            self.send_error_json(404, "Export not found.")
            return
        data = path.read_bytes()
        content_type = mimetypes.guess_type(str(path))[0] or "video/mp4"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_error_json(self, status: int, message: str) -> None:
        self.send_json({"error": message}, status=status)


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="GF5 lightweight web scene editor.")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind.")
    parser.add_argument("--port", type=int, default=8093, help="Port for the scene editor web server.")
    parser.add_argument("--no-open-browser", action="store_true", help="Do not open the browser automatically.")
    args = parser.parse_args()

    server = SceneEditorServer((args.host, args.port), project_root)
    url = f"http://localhost:{server.server_address[1]}"
    print(f"GF5 scene editor v3 listening at {url}")
    if not args.no_open_browser:
        webbrowser.open(url, new=2)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        print("GF5 scene editor stopped")


if __name__ == "__main__":
    main()
