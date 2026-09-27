# Environment

- Windows 11 Pro, Python 3.12.10 (per-user), uv 0.12.17. Project venv: `.venv` (`uv sync` recreates it).
- Dependencies (`pyproject.toml` / `uv.lock`): `opencv-contrib-python==4.10.0.84`, `numpy<2.3`, `pyyaml`; dev: `pytest`.

## Known issue: OpenCV 5.0 wheel blocked by Smart App Control

`opencv-contrib-python` 5.0.0.93 installed, but `import cv2` failed with:

> DLL load failed while importing cv2: An Application Control policy has blocked this file.

Smart App Control is on for this machine (`VerifiedAndReputablePolicyState = 1`), and it blocks
DLLs it considers unsigned or without reputation. The fix was to pin 4.10.0.84, which loads normally.
`numpy` is pinned below 2.3 to match that OpenCV build.
**Do not upgrade OpenCV without checking that `uv run python -c "import cv2"` still works.**
Don't turn Smart App Control off for this; it's a system security setting.

## Cameras seen on 2026-09-26

`Get-PnpDevice`: *Surface Camera Front* and *Surface IR Camera Front* only. No USB webcam is attached
yet. The laptop camera can't serve as a fixed overhead camera.
