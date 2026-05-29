from __future__ import annotations

import math
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

try:
    from PIL import Image, ImageDraw, ImageEnhance
except ModuleNotFoundError as exc:  # pragma: no cover - reported to user at export time.
    Image = None
    ImageDraw = None
    ImageEnhance = None
    PIL_IMPORT_ERROR = exc
else:
    PIL_IMPORT_ERROR = None


Vec3 = tuple[float, float, float]
DEFAULT_CLIP_BLEND_SECONDS = 0.45
MAX_TRANSITION_GAP_SECONDS = 0.25
CAMERA_ORIGIN_TARGET = "__origin__"
AVATAR_FINAL_MAX_FPS = 24
AVATAR_FINAL_MAX_WIDTH = 1280
AVATAR_FINAL_MAX_HEIGHT = 720
AVATAR_FINAL_TEXTURE_SATURATION = 0.88
AVATAR_FINAL_TEXTURE_CONTRAST = 1.06
AVATAR_FINAL_TEXTURE_BRIGHTNESS = 0.9
AVATAR_FINAL_OVERLAY_SATURATION = 1.0
AVATAR_FINAL_OVERLAY_CONTRAST = 1.08
AVATAR_FINAL_OVERLAY_BRIGHTNESS = 0.96
AVATAR_CONTACT_SHADOW_ALPHA = 48

PALETTE = (
    "#2f7f7b",
    "#3f7db8",
    "#4e68b8",
    "#2f91c2",
    "#d6a72f",
    "#a86438",
    "#d88c2d",
    "#c04848",
    "#7d6aa8",
    "#5d8749",
    "#2f9b72",
    "#b85b71",
    "#56656f",
)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def vec_add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def vec_sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def vec_scale(a: Vec3, scale: float) -> Vec3:
    return (a[0] * scale, a[1] * scale, a[2] * scale)


def dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def norm(a: Vec3) -> float:
    return math.sqrt(max(1e-12, dot(a, a)))


def normalize(a: Vec3) -> Vec3:
    length = norm(a)
    return (a[0] / length, a[1] / length, a[2] / length)


def parse_hex_color(value: str, fallback: tuple[int, int, int]) -> tuple[int, int, int]:
    text = str(value).strip()
    if len(text) == 7 and text.startswith("#"):
        try:
            return tuple(int(text[index:index + 2], 16) for index in (1, 3, 5))  # type: ignore[return-value]
        except ValueError:
            return fallback
    return fallback


def character_color(scene: dict[str, Any], character_id: str, index: int) -> tuple[int, int, int]:
    fallback = parse_hex_color(PALETTE[index % len(PALETTE)], (47, 127, 123))
    for character in scene.get("characters", []):
        if isinstance(character, dict) and str(character.get("id", "")) == character_id:
            return parse_hex_color(str(character.get("color", "")), fallback)
    return fallback


def tinted_part_color(character_rgb: tuple[int, int, int], part_rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    return tuple(
        int(clamp(0.55 * float(part_rgb[channel]) + 0.45 * float(character_rgb[channel]), 0.0, 255.0))
        for channel in range(3)
    )  # type: ignore[return-value]


def sorted_keys(character: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(character.get("root_keys", []), key=lambda key: (float(key.get("time", 0.0)), str(key.get("id", ""))))


def key_position(key: dict[str, Any]) -> Vec3:
    return tuple(float(v) for v in key.get("position", [0.0, 0.0, 0.0])[:3])  # type: ignore[return-value]


def segment_mode_for_pair(character: dict[str, Any], first: dict[str, Any], second: dict[str, Any]) -> str:
    first_id = str(first.get("id", ""))
    second_id = str(second.get("id", ""))
    for segment in character.get("root_segments", []):
        if not isinstance(segment, dict):
            continue
        if str(segment.get("from", "")) == first_id and str(segment.get("to", "")) == second_id:
            mode = str(segment.get("mode", "linear"))
            return mode if mode in {"linear", "curve", "hold"} else "linear"
    return "linear"


def interpolate_facing(first: dict[str, Any], second: dict[str, Any], alpha: float) -> float:
    facing0 = float(first.get("facing_degrees", 0.0))
    facing1 = float(second.get("facing_degrees", 0.0))
    delta = ((facing1 - facing0 + 180.0) % 360.0) - 180.0
    return facing0 + delta * alpha


def lerp_vec3(first: Vec3, second: Vec3, alpha: float) -> Vec3:
    return (
        first[0] * (1.0 - alpha) + second[0] * alpha,
        first[1] * (1.0 - alpha) + second[1] * alpha,
        first[2] * (1.0 - alpha) + second[2] * alpha,
    )


def catmull_rom_vec3(p0: Vec3, p1: Vec3, p2: Vec3, p3: Vec3, alpha: float) -> Vec3:
    t2 = alpha * alpha
    t3 = t2 * alpha
    return tuple(
        0.5
        * (
            2.0 * p1[axis]
            + (-p0[axis] + p2[axis]) * alpha
            + (2.0 * p0[axis] - 5.0 * p1[axis] + 4.0 * p2[axis] - p3[axis]) * t2
            + (-p0[axis] + 3.0 * p1[axis] - 3.0 * p2[axis] + p3[axis]) * t3
        )
        for axis in range(3)
    )  # type: ignore[return-value]


def root_at(character: dict[str, Any], scene_time: float) -> tuple[Vec3, float]:
    keys = sorted_keys(character)
    if not keys:
        return (0.0, 0.0, 0.0), 0.0
    if scene_time <= float(keys[0].get("time", 0.0)):
        return key_position(keys[0]), float(keys[0].get("facing_degrees", 0.0))
    if scene_time >= float(keys[-1].get("time", 0.0)):
        return key_position(keys[-1]), float(keys[-1].get("facing_degrees", 0.0))
    for index, (first, second) in enumerate(zip(keys[:-1], keys[1:])):
        t0 = float(first.get("time", 0.0))
        t1 = float(second.get("time", 0.0))
        if t0 <= scene_time <= t1:
            alpha = (scene_time - t0) / max(1e-6, t1 - t0)
            mode = segment_mode_for_pair(character, first, second)
            p0 = key_position(first)
            p1 = key_position(second)
            if mode == "hold":
                position = p1 if alpha >= 1.0 else p0
            elif mode == "curve":
                prev = key_position(keys[max(0, index - 1)])
                next_key = key_position(keys[min(len(keys) - 1, index + 2)])
                position = catmull_rom_vec3(prev, p0, p1, next_key, alpha)
            else:
                position = lerp_vec3(p0, p1, alpha)
            return position, interpolate_facing(first, second, alpha)
    return key_position(keys[-1]), float(keys[-1].get("facing_degrees", 0.0))


def active_clip_label(character: dict[str, Any], scene_time: float) -> str:
    for clip in sorted(character.get("track", []), key=lambda item: float(item.get("start", 0.0))):
        start = float(clip.get("start", 0.0))
        duration = max(1e-6, float(clip.get("duration", 0.0)))
        if start <= scene_time <= start + duration:
            return str(clip.get("clip", "Idle Breathing"))
    return "Idle Breathing"


def clip_start(clip: dict[str, Any]) -> float:
    return float(clip.get("start", 0.0))


def clip_duration(clip: dict[str, Any]) -> float:
    return max(1e-6, float(clip.get("duration", 0.0)))


def clip_end(clip: dict[str, Any]) -> float:
    return clip_start(clip) + clip_duration(clip)


def default_clip_blend(clip: dict[str, Any]) -> float:
    return min(DEFAULT_CLIP_BLEND_SECONDS, max(0.05, clip_duration(clip) * 0.3))


def has_clip_blend_value(clip: dict[str, Any], key: str) -> bool:
    return key in clip and clip[key] is not None and clip[key] != ""


def normalized_clip_blend(clip: dict[str, Any], key: str) -> float:
    if not has_clip_blend_value(clip, key):
        return default_clip_blend(clip)
    value = float(clip[key])
    if not math.isfinite(value):
        return default_clip_blend(clip)
    return clamp(value, 0.0, clip_duration(clip))


def effective_clip_blend_in(clip: dict[str, Any]) -> float:
    return normalized_clip_blend(clip, "blend_in")


def effective_clip_blend_out(clip: dict[str, Any]) -> float:
    return normalized_clip_blend(clip, "blend_out")


def clip_transition_window(first: dict[str, Any], second: dict[str, Any]) -> tuple[float, float] | None:
    first_end = clip_end(first)
    second_start = clip_start(second)
    second_end = clip_end(second)
    blend_out = effective_clip_blend_out(first)
    blend_in = effective_clip_blend_in(second)
    overlap_start = second_start
    overlap_end = min(first_end, second_end)
    if overlap_end > overlap_start + 1e-6:
        return min(overlap_start, first_end - blend_out), max(overlap_end, second_start + blend_in)

    if second_start - first_end > MAX_TRANSITION_GAP_SECONDS:
        return None
    if blend_out <= 1e-6 and blend_in <= 1e-6:
        return None
    return first_end - blend_out, second_start + blend_in


def clip_transition_at(character: dict[str, Any], scene_time: float) -> tuple[dict[str, Any], dict[str, Any], float, float] | None:
    clips = sorted(character.get("track", []), key=lambda item: float(item.get("start", 0.0)))
    for first, second in zip(clips[:-1], clips[1:]):
        window = clip_transition_window(first, second)
        if window is None:
            continue
        start, end = window
        if end > start + 1e-6 and start <= scene_time <= end:
            return first, second, start, end
    return None


def scene_center_and_radius(scene: dict[str, Any]) -> tuple[Vec3, float]:
    points: list[Vec3] = []
    for character in scene.get("characters", []):
        for key in character.get("root_keys", []):
            position = key.get("position", [0.0, 0.0, 0.0])
            points.append((float(position[0]), float(position[1]), float(position[2] if len(position) > 2 else 0.0)))
    if not points:
        return (0.0, 0.0, 0.8), 2.4
    center = (
        sum(point[0] for point in points) / len(points),
        sum(point[1] for point in points) / len(points),
        0.8,
    )
    radius = max(2.4, max(math.hypot(point[0] - center[0], point[1] - center[1]) for point in points) + 2.0)
    return center, radius


def camera_pose(scene: dict[str, Any], scene_time: float) -> tuple[Vec3, Vec3]:
    camera = scene.get("camera", {})
    center, radius = scene_center_and_radius(scene)
    height = max(0.4, float(camera.get("height", 1.35)))
    preset = str(camera.get("preset", "slow_orbit"))
    look_at = (center[0], center[1], max(0.6, height * 0.72))
    target_look_at = camera_target_look_at(scene, camera, scene_time, height)
    if preset == "front_stage":
        position = vec_add(look_at, (0.0, radius, height * 0.85))
    elif preset == "slow_orbit":
        if target_look_at is not None:
            look_at = target_look_at
        duration = max(0.001, float(scene.get("duration", 1.0)))
        angle = 2.0 * math.pi * (scene_time / duration)
        position = vec_add(look_at, (math.sin(angle) * radius, math.cos(angle) * radius, height * 0.9))
    elif preset == "follow_character":
        if target_look_at is not None:
            look_at = target_look_at
        position = vec_add(look_at, (0.0, -2.35, height * 0.55))
    elif preset == "dolly_in":
        if target_look_at is not None:
            look_at = target_look_at
        duration = max(0.001, float(scene.get("duration", 1.0)))
        alpha = clamp(scene_time / duration, 0.0, 1.0)
        position = vec_add(look_at, (0.25 * radius, radius * (1.55 - 0.45 * alpha), height * 0.85))
    elif preset == "top_down":
        position = (center[0], center[1] + 0.001, radius * 1.75)
        look_at = (center[0], center[1], 0.0)
    else:
        position = vec_add(look_at, (0.45 * radius, 1.15 * radius, height * 0.95))
    return position, look_at


def camera_target_look_at(scene: dict[str, Any], camera: dict[str, Any], scene_time: float, height: float) -> Vec3 | None:
    target_id = str(camera.get("target", ""))
    if target_id == CAMERA_ORIGIN_TARGET:
        return (0.0, 0.0, max(0.75, height * 0.72))
    target = next((item for item in scene.get("characters", []) if item.get("id") == target_id), None)
    if target is None:
        return None
    root, _ = root_at(target, scene_time)
    return (root[0], root[1], max(0.75, height * 0.72))


def project_point(point: Vec3, camera_position: Vec3, look_at: Vec3, width: int, height: int, *, top_down: bool) -> tuple[float, float, float] | None:
    forward = normalize(vec_sub(look_at, camera_position))
    world_up = (0.0, 0.0, 1.0)
    right = cross(forward, world_up)
    if norm(right) < 1e-5:
        right = (1.0, 0.0, 0.0)
    else:
        right = normalize(right)
    up = normalize(cross(right, forward))
    rel = vec_sub(point, camera_position)
    depth = dot(rel, forward)
    if depth <= 0.03:
        return None
    fov = math.radians(38.0 if top_down else 45.0)
    focal = 0.5 * height / math.tan(fov * 0.5)
    x = width * 0.5 + dot(rel, right) * focal / depth
    y = height * 0.54 - dot(rel, up) * focal / depth
    return x, y, focal / depth


def collect_projected_triangles(
    triangles: list[tuple[float, tuple[tuple[float, float], ...], tuple[int, int, int]]],
    vertices: Any,
    faces: Any,
    color: tuple[int, int, int],
    camera_position: Vec3,
    look_at: Vec3,
    width: int,
    height: int,
    *,
    top_down: bool,
) -> None:
    import numpy as np

    projected = [
        project_point(
            (float(point[0]), float(point[1]), float(point[2])),
            camera_position,
            look_at,
            width,
            height,
            top_down=top_down,
        )
        for point in np.asarray(vertices, dtype=np.float32)
    ]
    for face in np.asarray(faces, dtype=np.int64):
        points = [projected[int(index)] for index in face[:3]]
        if any(point is None for point in points):
            continue
        assert points[0] is not None and points[1] is not None and points[2] is not None
        coords = tuple((point[0], point[1]) for point in points)
        if all((x < -width or x > 2 * width or y < -height or y > 2 * height) for x, y in coords):
            continue
        depth_key = sum(point[2] for point in points) / 3.0
        triangles.append((depth_key, coords, color))


def character_segments(root: Vec3, facing_degrees: float, clip_label: str, scene_time: float) -> tuple[list[tuple[Vec3, Vec3]], Vec3, Vec3]:
    angle = math.radians(facing_degrees)
    forward = (math.sin(angle), math.cos(angle), 0.0)
    right = (math.cos(angle), -math.sin(angle), 0.0)
    label = clip_label.lower()
    pace = 2.0 * math.pi * scene_time
    swing = 0.0
    lift = 0.0
    wave = 0.0
    if any(word in label for word in ("walk", "jog", "march")):
        swing = math.sin(pace * 1.8) * 0.18
    if "jump" in label:
        lift = max(0.0, math.sin(pace * 1.2)) * 0.28
    if any(word in label for word in ("wave", "point", "clap", "dance")):
        wave = math.sin(pace * 2.3) * 0.16
    base = (root[0], root[1], root[2] + lift)
    pelvis = vec_add(base, (0.0, 0.0, 0.45))
    chest = vec_add(base, (0.0, 0.0, 1.05))
    neck = vec_add(base, (0.0, 0.0, 1.24))
    head = vec_add(base, (0.0, 0.0, 1.43))
    left_shoulder = vec_add(chest, vec_scale(right, -0.22))
    right_shoulder = vec_add(chest, vec_scale(right, 0.22))
    left_hip = vec_add(pelvis, vec_scale(right, -0.13))
    right_hip = vec_add(pelvis, vec_scale(right, 0.13))
    left_hand = vec_add(vec_add(left_shoulder, vec_scale(forward, 0.04 + swing)), (0.0, 0.0, -0.48))
    right_hand = vec_add(vec_add(right_shoulder, vec_scale(forward, -0.04 - swing)), (0.0, 0.0, -0.48))
    if wave:
        right_hand = vec_add(vec_add(right_shoulder, vec_scale(right, 0.12)), (0.0, 0.0, 0.25 + wave))
    left_foot = vec_add(vec_add(left_hip, vec_scale(forward, -swing)), (0.0, 0.0, -0.45))
    right_foot = vec_add(vec_add(right_hip, vec_scale(forward, swing)), (0.0, 0.0, -0.45))
    segments = [
        (pelvis, chest),
        (chest, neck),
        (left_shoulder, right_shoulder),
        (left_shoulder, left_hand),
        (right_shoulder, right_hand),
        (left_hip, right_hip),
        (left_hip, left_foot),
        (right_hip, right_foot),
    ]
    return segments, head, chest


def blend_character_segments(
    first: tuple[list[tuple[Vec3, Vec3]], Vec3, Vec3],
    second: tuple[list[tuple[Vec3, Vec3]], Vec3, Vec3],
    alpha: float,
) -> tuple[list[tuple[Vec3, Vec3]], Vec3, Vec3]:
    alpha = smoothstep(alpha)
    first_segments, first_head, first_chest = first
    second_segments, second_head, second_chest = second
    if len(first_segments) != len(second_segments):
        return second if alpha >= 0.5 else first
    segments = [
        (lerp_vec3(a0, b0, alpha), lerp_vec3(a1, b1, alpha))
        for (a0, a1), (b0, b1) in zip(first_segments, second_segments)
    ]
    return segments, lerp_vec3(first_head, second_head, alpha), lerp_vec3(first_chest, second_chest, alpha)


def smoothstep(alpha: float) -> float:
    alpha = clamp(alpha, 0.0, 1.0)
    return alpha * alpha * (3.0 - 2.0 * alpha)


def character_segments_at(
    character: dict[str, Any],
    root: Vec3,
    facing_degrees: float,
    scene_time: float,
) -> tuple[list[tuple[Vec3, Vec3]], Vec3, Vec3]:
    transition = clip_transition_at(character, scene_time)
    if transition is not None:
        first_clip, second_clip, start, end = transition
        alpha = (scene_time - start) / (end - start)
        first_time = clamp(scene_time, clip_start(first_clip), clip_end(first_clip))
        second_time = clamp(scene_time, clip_start(second_clip), clip_end(second_clip))
        first = character_segments(root, facing_degrees, str(first_clip.get("clip", "Idle Breathing")), first_time)
        second = character_segments(root, facing_degrees, str(second_clip.get("clip", "Idle Breathing")), second_time)
        return blend_character_segments(first, second, alpha)
    clips = sorted(character.get("track", []), key=lambda item: float(item.get("start", 0.0)))
    for index, clip in enumerate(clips):
        start = clip_start(clip)
        end = clip_end(clip)
        blend_in = effective_clip_blend_in(clip)
        blend_out = effective_clip_blend_out(clip)
        label = str(clip.get("clip", "Idle Breathing"))
        if blend_in > 1e-6 and start - blend_in <= scene_time < start:
            previous = clips[index - 1] if index > 0 else None
            previous_end = clip_end(previous) if previous is not None else float("-inf")
            if previous is not None and (scene_time <= previous_end + 1e-6 or start - previous_end <= MAX_TRANSITION_GAP_SECONDS):
                continue
            alpha = (scene_time - (start - blend_in)) / blend_in
            idle = character_segments(root, facing_degrees, "Idle Breathing", scene_time)
            motion = character_segments(root, facing_degrees, label, start)
            return blend_character_segments(idle, motion, alpha)
        if blend_out > 1e-6 and end < scene_time <= end + blend_out:
            next_clip = clips[index + 1] if index < len(clips) - 1 else None
            next_start = clip_start(next_clip) if next_clip is not None else float("inf")
            if next_clip is not None and (scene_time >= next_start - 1e-6 or next_start - end <= MAX_TRANSITION_GAP_SECONDS):
                continue
            alpha = (scene_time - end) / blend_out
            motion = character_segments(root, facing_degrees, label, end)
            idle = character_segments(root, facing_degrees, "Idle Breathing", scene_time)
            return blend_character_segments(motion, idle, alpha)
    return character_segments(root, facing_degrees, active_clip_label(character, scene_time), scene_time)


def draw_proxy_asset_characters(
    draw: Any,
    scene: dict[str, Any],
    proxy_context: dict[str, Any],
    scene_time: float,
    camera_position: Vec3,
    look_at: Vec3,
    width: int,
    height: int,
    top_down: bool,
) -> None:
    import numpy as np

    triangles: list[tuple[float, tuple[tuple[float, float], ...], tuple[int, int, int]]] = []
    motion_scene = proxy_context["motion_scene"]
    motion_library = proxy_context["motion_library"]
    asset_cache = proxy_context["asset_cache"]
    sample_character_pose = proxy_context["sample_character_pose"]
    pose_sample_to_asset_local_rotations = proxy_context["pose_sample_to_asset_local_rotations"]
    transform_world_pose = proxy_context["transform_world_pose"]

    for index, character in enumerate(motion_scene.characters):
        sample = sample_character_pose(character, scene_time, motion_library)
        if sample is None:
            continue
        pose_sample, stage_root, facing_degrees = sample
        asset = asset_cache[character.character_id]
        local_rotations = pose_sample_to_asset_local_rotations(asset, pose_sample)
        rotations, positions = transform_world_pose(
            asset,
            local_rotations,
            pose_sample.root_offset,
            stage_root,
            facing_degrees,
        )
        base_color = character_color(scene, character.character_id, index)
        for part in asset.parts:
            joint_index = part.joint_index
            vertices = np.asarray(part.vertices, dtype=np.float32) @ np.asarray(rotations[joint_index], dtype=np.float32).T
            vertices = vertices + np.asarray(positions[joint_index], dtype=np.float32)
            collect_projected_triangles(
                triangles,
                vertices,
                part.faces,
                tinted_part_color(base_color, part.color),
                camera_position,
                look_at,
                width,
                height,
                top_down=top_down,
            )

    for _, coords, color in sorted(triangles, key=lambda item: item[0]):
        draw.polygon(coords, fill=(*color, 235))


def render_scene_frame(
    scene: dict[str, Any],
    scene_time: float,
    width: int,
    height: int,
    proxy_context: dict[str, Any] | None = None,
) -> Any:
    if Image is None or ImageDraw is None:
        raise RuntimeError("Pillow is required for video export. Install pillow in the GF5 environment.") from PIL_IMPORT_ERROR
    background = scene.get("background", {})
    image = Image.new("RGB", (width, height), parse_hex_color(str(background.get("color", "#f4f1ea")), (244, 241, 234)))
    draw = ImageDraw.Draw(image, "RGBA")
    camera_position, look_at = camera_pose(scene, scene_time)
    top_down = str(scene.get("camera", {}).get("preset", "")) == "top_down"
    center, radius = scene_center_and_radius(scene)

    grid_extent = math.ceil(radius + 1.0)
    for index in range(-grid_extent, grid_extent + 1):
        for a, b in (
            ((index, -grid_extent, 0.0), (index, grid_extent, 0.0)),
            ((-grid_extent, index, 0.0), (grid_extent, index, 0.0)),
        ):
            pa = project_point((a[0] + center[0], a[1] + center[1], a[2]), camera_position, look_at, width, height, top_down=top_down)
            pb = project_point((b[0] + center[0], b[1] + center[1], b[2]), camera_position, look_at, width, height, top_down=top_down)
            if pa and pb:
                draw.line((pa[0], pa[1], pb[0], pb[1]), fill=(36, 43, 45, 38), width=1)

    if proxy_context is not None:
        draw_proxy_asset_characters(
            draw,
            scene,
            proxy_context,
            scene_time,
            camera_position,
            look_at,
            width,
            height,
            top_down,
        )
        return image

    draw_items: list[tuple[float, int, dict[str, Any], Vec3, float]] = []
    for index, character in enumerate(scene.get("characters", [])):
        root, facing = root_at(character, scene_time)
        projected = project_point((root[0], root[1], root[2] + 0.8), camera_position, look_at, width, height, top_down=top_down)
        if projected:
            draw_items.append((projected[2], index, character, root, facing))
    draw_items.sort(key=lambda item: item[0])

    for _, index, character, root, facing in draw_items:
        fallback = parse_hex_color(PALETTE[index % len(PALETTE)], (47, 127, 123))
        color = parse_hex_color(str(character.get("color", "")), fallback)
        segments, head, chest = character_segments_at(character, root, facing, scene_time)
        for first, second in segments:
            pa = project_point(first, camera_position, look_at, width, height, top_down=top_down)
            pb = project_point(second, camera_position, look_at, width, height, top_down=top_down)
            if not pa or not pb:
                continue
            line_width = max(3, int(0.045 * (pa[2] + pb[2]) * 0.5))
            draw.line((pa[0], pa[1], pb[0], pb[1]), fill=(*color, 230), width=line_width)
        head_p = project_point(head, camera_position, look_at, width, height, top_down=top_down)
        chest_p = project_point(chest, camera_position, look_at, width, height, top_down=top_down)
        if chest_p:
            body_r = max(5, int(0.13 * chest_p[2]))
            draw.ellipse((chest_p[0] - body_r, chest_p[1] - body_r, chest_p[0] + body_r, chest_p[1] + body_r), fill=(255, 255, 255, 225), outline=(*color, 255), width=2)
        if head_p:
            head_r = max(4, int(0.11 * head_p[2]))
            draw.ellipse((head_p[0] - head_r, head_p[1] - head_r, head_p[0] + head_r, head_p[1] + head_r), fill=(255, 255, 255, 238), outline=(*color, 255), width=2)

    return image


def write_mp4(frames: list[Any], output_path: Path, fps: int) -> None:
    if not frames:
        raise ValueError("Cannot export a video with zero frames.")
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path is None:
        raise RuntimeError("Could not find an ffmpeg binary on PATH.")
    width, height = frames[0].size
    command = [
        ffmpeg_path,
        "-y",
        "-loglevel",
        "error",
        "-f",
        "rawvideo",
        "-vcodec",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{width}x{height}",
        "-r",
        str(fps),
        "-i",
        "-",
        "-an",
        "-vcodec",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(output_path),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    assert process.stdin is not None
    try:
        for frame in frames:
            process.stdin.write(frame.convert("RGB").tobytes())
    finally:
        process.stdin.close()
    stderr = process.stderr.read() if process.stderr is not None else b""
    code = process.wait()
    if code != 0:
        raise RuntimeError(stderr.decode("utf-8", errors="ignore").strip() or "ffmpeg failed to encode the video.")


def stream_mp4(output_path: Path, fps: int, width: int, height: int, frame_iter: Any) -> None:
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path is None:
        raise RuntimeError("Could not find an ffmpeg binary on PATH.")
    command = [
        ffmpeg_path,
        "-y",
        "-loglevel",
        "error",
        "-f",
        "rawvideo",
        "-vcodec",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{width}x{height}",
        "-r",
        str(fps),
        "-i",
        "-",
        "-an",
        "-vcodec",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(output_path),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    assert process.stdin is not None
    try:
        for frame in frame_iter:
            process.stdin.write(frame.convert("RGB").tobytes())
    finally:
        process.stdin.close()
    stderr = process.stderr.read() if process.stderr is not None else b""
    code = process.wait()
    if code != 0:
        raise RuntimeError(stderr.decode("utf-8", errors="ignore").strip() or "ffmpeg failed to encode the video.")


def even_dimension(value: float, minimum: int = 2) -> int:
    dimension = max(minimum, int(round(value)))
    return dimension if dimension % 2 == 0 else dimension + 1


def avatar_final_export_settings(scene: dict[str, Any]) -> dict[str, int | float | bool | str]:
    export = scene.get("export", {})
    requested_fps = max(1, int(export.get("fps", 24)))
    requested_width = max(2, int(export.get("width", 960)))
    requested_height = max(2, int(export.get("height", 540)))
    scale = min(
        1.0,
        AVATAR_FINAL_MAX_WIDTH / max(1, requested_width),
        AVATAR_FINAL_MAX_HEIGHT / max(1, requested_height),
    )
    fps = min(requested_fps, AVATAR_FINAL_MAX_FPS)
    width = even_dimension(requested_width * scale)
    height = even_dimension(requested_height * scale)
    capped = fps != requested_fps or scale < 1.0
    adjusted = width != requested_width or height != requested_height
    warning = ""
    if capped:
        warning = (
            "Final avatar render capped from "
            f"{requested_width}x{requested_height} {requested_fps} fps to "
            f"{width}x{height} {fps} fps."
        )
    elif adjusted:
        warning = (
            "Final avatar render adjusted to even video dimensions: "
            f"{requested_width}x{requested_height} -> {width}x{height}."
        )
    return {
        "fps": fps,
        "width": width,
        "height": height,
        "requested_fps": requested_fps,
        "requested_width": requested_width,
        "requested_height": requested_height,
        "max_fps": AVATAR_FINAL_MAX_FPS,
        "max_width": AVATAR_FINAL_MAX_WIDTH,
        "max_height": AVATAR_FINAL_MAX_HEIGHT,
        "scale": scale,
        "capped": capped,
        "adjusted": adjusted,
        "warning": warning,
    }


def export_scene_video(scene: dict[str, Any], output_dir: Path, project_root: Path | None = None) -> Path:
    if project_root is None:
        project_root = Path(__file__).resolve().parent.parent
    from asset_viewer import discover_assets, load_asset, pose_sample_to_asset_local_rotations
    from scene_editor import (
        discover_motion_library,
        preferred_asset_label,
        sample_character_pose,
        scene_from_json,
        transform_world_pose,
    )

    asset_sources = discover_assets(project_root / "assets" / "blocky")
    if not asset_sources:
        raise RuntimeError("No blocky proxy assets found under assets/blocky.")
    default_asset = preferred_asset_label(asset_sources)
    motion_library = discover_motion_library(project_root / "libraries" / "motions", project_root / "libraries" / "motions" / "custom")
    motion_scene = scene_from_json(scene, default_asset)
    asset_cache: dict[str, Any] = {}
    for character in motion_scene.characters:
        asset_label = character.proxy_asset if character.proxy_asset in asset_sources else default_asset
        asset_cache[character.character_id] = load_asset(asset_sources[asset_label])
    proxy_context = {
        "motion_scene": motion_scene,
        "motion_library": motion_library,
        "asset_cache": asset_cache,
        "sample_character_pose": sample_character_pose,
        "pose_sample_to_asset_local_rotations": pose_sample_to_asset_local_rotations,
        "transform_world_pose": transform_world_pose,
    }

    export = scene.get("export", {})
    fps = max(1, int(export.get("fps", 24)))
    width = max(2, int(export.get("width", 960)))
    height = max(2, int(export.get("height", 540)))
    frame_count = max(2, int(round(float(scene.get("duration", 1.0)) * fps)) + 1)
    duration = max(0.001, float(scene.get("duration", 1.0)))
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"motion_scene_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
    def frames() -> Any:
        for frame_index in range(frame_count):
            frame_time = duration * frame_index / max(1, frame_count - 1)
            yield render_scene_frame(scene, frame_time, width, height, proxy_context)
    stream_mp4(path, fps, width, height, frames())
    return path


def resolve_avatar_asset(value: str, avatar_assets: list[dict[str, str]]) -> dict[str, str] | None:
    text = str(value).strip()
    if not text:
        return None
    for asset in avatar_assets:
        if text in {asset.get("label", ""), asset.get("path", "")}:
            return asset
    path = Path(text).expanduser()
    if path.exists():
        return {"label": path.name, "path": str(path), "kind": "up2you"}
    return None


def camera_basis(camera_position: Vec3, look_at: Vec3) -> tuple[Any, Any, Any]:
    import numpy as np

    forward = np.asarray(vec_sub(look_at, camera_position), dtype=np.float32)
    forward /= max(float(np.linalg.norm(forward)), 1e-8)
    world_up = np.asarray([0.0, 0.0, 1.0], dtype=np.float32)
    right = np.cross(forward, world_up)
    if float(np.linalg.norm(right)) < 1e-5:
        right = np.asarray([1.0, 0.0, 0.0], dtype=np.float32)
    else:
        right /= max(float(np.linalg.norm(right)), 1e-8)
    up = np.cross(right, forward)
    up /= max(float(np.linalg.norm(up)), 1e-8)
    return forward, right, up


def pyrender_camera_pose(camera_position: Vec3, look_at: Vec3) -> Any:
    import numpy as np

    forward, right, up = camera_basis(camera_position, look_at)
    pose = np.eye(4, dtype=np.float32)
    pose[:3, 0] = right
    pose[:3, 1] = up
    pose[:3, 2] = -forward
    pose[:3, 3] = np.asarray(camera_position, dtype=np.float32)
    return pose


def rgba_vertex_colors(vertex_colors: Any, vertex_count: int) -> Any:
    import numpy as np

    if vertex_colors is None:
        rgb = np.tile(np.asarray([[214, 189, 161]], dtype=np.uint8), (vertex_count, 1))
    else:
        rgb = np.asarray(vertex_colors)
        if rgb.dtype.kind == "f" and rgb.size and float(np.nanmax(rgb)) <= 1.0:
            rgb = rgb * 255.0
        rgb = np.clip(rgb, 0.0, 255.0).astype(np.uint8)
        if rgb.shape[0] != vertex_count:
            rgb = np.resize(rgb, (vertex_count, rgb.shape[1] if rgb.ndim == 2 else 3))
        if rgb.ndim != 2 or rgb.shape[1] < 3:
            rgb = np.tile(np.asarray([[214, 189, 161]], dtype=np.uint8), (vertex_count, 1))
        rgb = rgb[:, :3]
    rgb = final_render_rgb_colors(rgb, np)
    alpha = np.full((vertex_count, 1), 255, dtype=np.uint8)
    return np.concatenate([rgb, alpha], axis=1)


def final_render_rgb_colors(rgb: Any, np: Any) -> Any:
    rgb_f = np.asarray(rgb, dtype=np.float32)
    if rgb_f.size == 0:
        return np.asarray(rgb, dtype=np.uint8)
    luminance_weights = np.asarray([0.2126, 0.7152, 0.0722], dtype=np.float32)
    luminance = rgb_f @ luminance_weights
    rgb_f = luminance[:, None] + (rgb_f - luminance[:, None]) * AVATAR_FINAL_TEXTURE_SATURATION
    rgb_f = 128.0 + (rgb_f - 128.0) * AVATAR_FINAL_TEXTURE_CONTRAST
    rgb_f *= AVATAR_FINAL_TEXTURE_BRIGHTNESS
    return np.clip(rgb_f, 0.0, 255.0).astype(np.uint8)


def color_grade_avatar_overlay(image: Any) -> Any:
    if ImageEnhance is None:
        return image
    alpha = image.getchannel("A") if image.mode == "RGBA" else None
    rgb = image.convert("RGB")
    rgb = ImageEnhance.Color(rgb).enhance(AVATAR_FINAL_OVERLAY_SATURATION)
    rgb = ImageEnhance.Contrast(rgb).enhance(AVATAR_FINAL_OVERLAY_CONTRAST)
    rgb = ImageEnhance.Brightness(rgb).enhance(AVATAR_FINAL_OVERLAY_BRIGHTNESS)
    if alpha is not None:
        rgb.putalpha(alpha)
    return rgb


def rigid_asset_frame_mesh(asset: Any, world_rotations: Any, world_positions: Any) -> tuple[Any, Any, Any]:
    import numpy as np

    vertex_groups: list[Any] = []
    face_groups: list[Any] = []
    color_groups: list[Any] = []
    vertex_offset = 0
    for part in asset.parts:
        joint_index = int(part.joint_index)
        vertices = (
            np.asarray(part.vertices, dtype=np.float32)
            @ np.asarray(world_rotations[joint_index], dtype=np.float32).T
            + np.asarray(world_positions[joint_index], dtype=np.float32)
        )
        faces = np.asarray(part.faces, dtype=np.int64) + vertex_offset
        colors = np.tile(np.asarray(part.color, dtype=np.uint8)[None, :], (vertices.shape[0], 1))
        vertex_groups.append(vertices)
        face_groups.append(faces)
        color_groups.append(colors)
        vertex_offset += int(vertices.shape[0])
    if not vertex_groups:
        return (
            np.zeros((0, 3), dtype=np.float32),
            np.zeros((0, 3), dtype=np.int64),
            np.zeros((0, 4), dtype=np.uint8),
        )
    vertices = np.concatenate(vertex_groups, axis=0).astype(np.float32)
    faces = np.concatenate(face_groups, axis=0).astype(np.int64)
    colors = rgba_vertex_colors(np.concatenate(color_groups, axis=0), int(vertices.shape[0]))
    return vertices, faces, colors


class OffscreenAvatarRenderer:
    def __init__(self, width: int, height: int) -> None:
        if Image is None:
            raise RuntimeError("Pillow is required for final avatar rendering.") from PIL_IMPORT_ERROR
        opengl_platform = os.environ.get("PYOPENGL_PLATFORM", "").strip().lower()
        if opengl_platform == "auto":
            os.environ.pop("PYOPENGL_PLATFORM", None)
            opengl_platform = ""
        if sys.platform.startswith("linux") and not opengl_platform:
            os.environ["PYOPENGL_PLATFORM"] = "egl"
        elif sys.platform.startswith("win") and opengl_platform in {"win32", "windows", "nt"}:
            os.environ.pop("PYOPENGL_PLATFORM", None)
        mesa_cache_dir = Path(os.environ.get("MESA_SHADER_CACHE_DIR", str(Path("/tmp") / "gf5_mesa_shader_cache")))
        try:
            mesa_cache_dir.mkdir(parents=True, exist_ok=True)
            os.environ.setdefault("MESA_SHADER_CACHE_DIR", str(mesa_cache_dir))
        except OSError:
            pass
        try:
            import numpy as np
            import pyrender
            import trimesh
        except Exception as exc:  # pragma: no cover - depends on local OpenGL setup.
            platform_hint = os.environ.get("PYOPENGL_PLATFORM") or "auto"
            raise RuntimeError(
                "Final avatar rendering requires trimesh, pyrender, and a working OpenGL/EGL context. "
                f"Install the GF5 environment or set PYOPENGL_PLATFORM for this machine "
                f"(current: {platform_hint})."
            ) from exc

        self.width = int(width)
        self.height = int(height)
        self.np = np
        self.pyrender = pyrender
        self.trimesh = trimesh
        try:
            self.renderer = pyrender.OffscreenRenderer(self.width, self.height)
        except Exception as exc:  # pragma: no cover - depends on local OpenGL setup.
            platform_hint = os.environ.get("PYOPENGL_PLATFORM") or "auto"
            raise RuntimeError(
                "Could not create a pyrender offscreen renderer. "
                f"Current PYOPENGL_PLATFORM is {platform_hint}. "
                "On macOS, run from a local desktop Terminal session; final avatar export "
                "uses a helper process so pyrender can create its OpenGL context on the main thread. "
                "On Windows, leave PYOPENGL_PLATFORM unset and run from a normal desktop session. "
                "On headless Linux, try PYOPENGL_PLATFORM=egl or check EGL/OpenGL availability."
            ) from exc

    def close(self) -> None:
        self.renderer.delete()

    def mesh_from_vertices(self, vertices: Any, faces: Any, vertex_colors: Any) -> Any:
        mesh = self.trimesh.Trimesh(
            vertices=self.np.asarray(vertices, dtype=self.np.float32),
            faces=self.np.asarray(faces, dtype=self.np.int64),
            vertex_colors=self.np.asarray(vertex_colors, dtype=self.np.uint8),
            process=False,
        )
        render_mesh = self.pyrender.Mesh.from_trimesh(mesh, smooth=True)
        for primitive in render_mesh.primitives:
            primitive.material.doubleSided = True
            primitive.material.metallicFactor = 0.0
            primitive.material.roughnessFactor = 0.78
            primitive.material.alphaMode = "OPAQUE"
        return render_mesh

    def render(
        self,
        scene_payload: dict[str, Any],
        scene_time: float,
        meshes: list[tuple[Any, Any, Any]],
    ) -> Any:
        pyrender_scene = self.pyrender.Scene(
            bg_color=self.np.asarray([0.0, 0.0, 0.0, 0.0], dtype=self.np.float32),
            ambient_light=self.np.asarray([0.22, 0.215, 0.205, 1.0], dtype=self.np.float32),
        )
        for vertices, faces, vertex_colors in meshes:
            pyrender_scene.add(self.mesh_from_vertices(vertices, faces, vertex_colors))

        camera_position, look_at = camera_pose(scene_payload, scene_time)
        top_down = str(scene_payload.get("camera", {}).get("preset", "")) == "top_down"
        fov = math.radians(38.0 if top_down else 45.0)
        focal = 0.5 * self.height / math.tan(fov * 0.5)
        _, radius = scene_center_and_radius(scene_payload)
        camera = self.pyrender.IntrinsicsCamera(
            fx=focal,
            fy=focal,
            cx=self.width * 0.5,
            cy=self.height * 0.54,
            znear=0.03,
            zfar=max(100.0, radius * 10.0),
        )
        camera_pose_matrix = pyrender_camera_pose(camera_position, look_at)
        pyrender_scene.add(camera, pose=camera_pose_matrix)
        key_light = self.pyrender.DirectionalLight(
            color=self.np.asarray([1.0, 0.98, 0.94], dtype=self.np.float32),
            intensity=2.45,
        )
        fill_light = self.pyrender.DirectionalLight(
            color=self.np.asarray([0.75, 0.8, 0.9], dtype=self.np.float32),
            intensity=0.38,
        )
        pyrender_scene.add(key_light, pose=camera_pose_matrix)
        fill_position = tuple(
            self.np.asarray(camera_position, dtype=self.np.float32) + self.np.asarray([2.0, -3.0, 3.0], dtype=self.np.float32)
        )
        fill_pose = pyrender_camera_pose(fill_position, look_at)
        pyrender_scene.add(fill_light, pose=fill_pose)

        flags = self.pyrender.RenderFlags.RGBA | self.pyrender.RenderFlags.SKIP_CULL_FACES
        color, _depth = self.renderer.render(pyrender_scene, flags=flags)
        return color_grade_avatar_overlay(Image.fromarray(color))


def export_avatar_scene_video(
    scene: dict[str, Any],
    output_dir: Path,
    avatar_assets: list[dict[str, str]],
    project_root: Path,
    progress_callback: Callable[[int, int], None] | None = None,
) -> Path:
    if Image is None or ImageDraw is None:
        raise RuntimeError("Pillow is required for video export. Install pillow in the GF5 environment.") from PIL_IMPORT_ERROR

    from asset_viewer import load_asset, load_smpl_asset, load_up2you_character_asset, pose_sample_to_asset_local_rotations
    from scene_editor import (
        discover_motion_library,
        scene_from_json,
        sample_character_pose,
        transform_world_pose,
    )
    from smpl_support import skin_smpl_mesh

    export_settings = avatar_final_export_settings(scene)
    fps = int(export_settings["fps"])
    width = int(export_settings["width"])
    height = int(export_settings["height"])
    duration = max(0.001, float(scene.get("duration", 1.0)))
    frame_count = max(2, int(round(duration * fps)) + 1)

    motion_library = discover_motion_library(project_root / "libraries" / "motions", project_root / "libraries" / "motions" / "custom")
    motion_scene = scene_from_json(scene, default_asset="SMPL-24 Proxy")
    avatar_cache: dict[str, Any] = {}
    avatar_vertex_colors: dict[str, Any] = {}
    for character in motion_scene.characters:
        avatar_spec = resolve_avatar_asset(character.avatar_asset, avatar_assets)
        if avatar_spec is None:
            raise RuntimeError(f"{character.label} does not have a valid final avatar assigned.")
        avatar_path = Path(str(avatar_spec["path"]))
        avatar_kind = str(avatar_spec.get("kind", "up2you"))
        try:
            if avatar_kind == "blocky":
                asset = load_asset(avatar_path)
            elif avatar_kind == "smpl":
                asset = load_smpl_asset(avatar_path)
            else:
                asset = load_up2you_character_asset(avatar_path, Path(""))
        except Exception as exc:
            label = str(avatar_spec.get("label", avatar_path))
            raise RuntimeError(f"Could not load final avatar for {character.label} ({label}): {exc}") from exc
        if asset.asset_kind != "rigid":
            if asset.skinned_model_data is None or asset.mesh_faces is None:
                label = str(avatar_spec.get("label", avatar_path))
                raise RuntimeError(f"Final avatar {label} does not have usable skinning data.")
            avatar_vertex_colors[character.character_id] = rgba_vertex_colors(
                asset.mesh_vertex_colors,
                int(asset.mesh_vertices.shape[0]) if asset.mesh_vertices is not None else 0,
            )
        avatar_cache[character.character_id] = asset

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"final_avatar_scene_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
    avatar_renderer = OffscreenAvatarRenderer(width, height)

    def frames() -> Any:
        for frame_index in range(frame_count):
            scene_time = duration * frame_index / max(1, frame_count - 1)
            background = scene.get("background", {})
            image = Image.new("RGB", (width, height), parse_hex_color(str(background.get("color", "#f4f1ea")), (244, 241, 234)))
            draw = ImageDraw.Draw(image, "RGBA")
            draw_avatar_floor(draw, scene, scene_time, width, height)

            render_meshes: list[tuple[Any, Any, Any]] = []
            for character in motion_scene.characters:
                sample = sample_character_pose(character, scene_time, motion_library)
                if sample is None:
                    continue
                pose_sample, stage_root, facing_degrees = sample
                draw_avatar_contact_shadow(draw, scene, scene_time, stage_root, width, height)
                asset = avatar_cache[character.character_id]
                local_rotations = pose_sample_to_asset_local_rotations(asset, pose_sample)
                world_rotations, world_positions = transform_world_pose(
                    asset,
                    local_rotations,
                    pose_sample.root_offset,
                    stage_root,
                    facing_degrees,
                )
                if asset.asset_kind == "rigid":
                    render_meshes.append(rigid_asset_frame_mesh(asset, world_rotations, world_positions))
                    continue
                mesh_vertices = skin_smpl_mesh(
                    asset.skinned_model_data,
                    world_rotations,
                    world_positions,
                    use_blended_weights=True,
                )
                render_meshes.append(
                    (
                        mesh_vertices,
                        asset.mesh_faces,
                        avatar_vertex_colors[character.character_id],
                    )
                )

            if render_meshes:
                overlay = avatar_renderer.render(scene, scene_time, render_meshes)
                image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
            yield image
            if progress_callback is not None:
                progress_callback(frame_index + 1, frame_count)

    try:
        stream_mp4(path, fps, width, height, frames())
    finally:
        avatar_renderer.close()
    return path


def draw_avatar_floor(draw: Any, scene: dict[str, Any], scene_time: float, width: int, height: int) -> None:
    camera_position, look_at = camera_pose(scene, scene_time)
    top_down = str(scene.get("camera", {}).get("preset", "")) == "top_down"
    center, radius = scene_center_and_radius(scene)
    grid_extent = math.ceil(radius + 1.0)
    for index in range(-grid_extent, grid_extent + 1):
        for a, b in (
            ((index, -grid_extent, 0.0), (index, grid_extent, 0.0)),
            ((-grid_extent, index, 0.0), (grid_extent, index, 0.0)),
        ):
            pa = project_point((a[0] + center[0], a[1] + center[1], a[2]), camera_position, look_at, width, height, top_down=top_down)
            pb = project_point((b[0] + center[0], b[1] + center[1], b[2]), camera_position, look_at, width, height, top_down=top_down)
            if pa and pb:
                draw.line((pa[0], pa[1], pb[0], pb[1]), fill=(36, 43, 45, 38), width=1)


def draw_avatar_contact_shadow(draw: Any, scene: dict[str, Any], scene_time: float, root: Vec3, width: int, height: int) -> None:
    camera_position, look_at = camera_pose(scene, scene_time)
    top_down = str(scene.get("camera", {}).get("preset", "")) == "top_down"
    point = project_point((float(root[0]), float(root[1]), 0.018), camera_position, look_at, width, height, top_down=top_down)
    if point is None:
        return
    x, y, scale = point
    shadow_width = clamp(0.24 * scale, 9.0, width * 0.1)
    shadow_height = clamp((0.11 if top_down else 0.075) * scale, 4.0, height * 0.05)
    y += 0.018 * scale
    draw.ellipse(
        (x - shadow_width, y - shadow_height, x + shadow_width, y + shadow_height),
        fill=(20, 23, 25, AVATAR_CONTACT_SHADOW_ALPHA),
    )
    inner_width = shadow_width * 0.62
    inner_height = shadow_height * 0.58
    draw.ellipse(
        (x - inner_width, y - inner_height, x + inner_width, y + inner_height),
        fill=(12, 14, 15, max(10, AVATAR_CONTACT_SHADOW_ALPHA - 22)),
    )
