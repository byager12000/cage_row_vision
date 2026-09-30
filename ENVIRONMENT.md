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

## Known issue: venv .exe launchers blocked by Smart App Control (2026-09-28)

`uv run pytest` and `uv run cage-vision` began failing with "An Application Control policy has
blocked this file (os error 4551)". The blocked files are the small `.exe` launchers uv generates in
`.venv\Scripts`; `python.exe` itself is not blocked. Use the module form instead:

- `uv run python -m pytest -q`
- `uv run python -m cage_vision <command>`

## Bench camera

Stopmotion Explosion HD Pro 1080p on DirectShow index 2 (0 and 1 are the Surface cameras).
When MJPG was requested, the camera still reported YUY2 at 1920×1080. That works, but expect
a low live frame rate over USB 2.0, which is fine for stationary measurement.

## Home bench lighting (2026-09-28)

Ordinary room lighting only, with no dedicated or diffused lights. The room got darker during the
evening; image mean went from about 74 to 56 at exposure −5 with no clipping, and detection was unaffected.
Lighting is not controlled on this bench, so a production station should add its own diffused light.
