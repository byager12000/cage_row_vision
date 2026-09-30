import sys, copy, cv2, numpy as np
from cage_vision.config import load_config
from cage_vision.calibration import calibrate, make_detector
from cage_vision.camera_model import estimate_camera
d = sys.argv[1]; CAGE_H, TAPER, BELT, CAM_H = 5.0, 0.18, 0.375, 48.5
cfg = copy.deepcopy(load_config("config.yaml"))
cfg.markers.positions = {0: (0.0, 0.0), 1: (45.125, 0.0), 2: (45.125, 30.0), 3: (0.0, 30.0)}
img = cv2.imread(d + r"\cam0_exp-7.png"); cal = calibrate(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), cfg.markers, make_detector(cfg.markers))
cam = estimate_camera(cal.H, (1920, 1080), CAM_H)
A = np.load(d + r"\A.npy"); out_px = np.load(d + r"\outline.npy").astype(float)
q = np.c_[out_px, np.ones(len(out_px))] @ np.linalg.inv(A).T; obs = q[:, :2] / q[:, 2:]          # floor-plane hits
def corners(c, ang, L, W):
    t = np.radians(ang); u = np.array([np.cos(t), np.sin(t)]); v = np.array([-np.sin(t), np.cos(t)])
    return np.array([c + a * u * L / 2 + b * v * W / 2 for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
def silhouette(p):
    x, y, ang, Lb, Wb = p
    base = cam.from_height(corners(np.array([x, y]), ang, Lb, Wb), BELT)
    rim = cam.from_height(corners(np.array([x, y]), ang, Lb + 2 * TAPER, Wb + 2 * TAPER), BELT + CAGE_H)
    return cv2.convexHull(np.vstack([base, rim]).astype(np.float32))
def cost(p):
    hull = silhouette(p)
    dist = np.array([cv2.pointPolygonTest(hull, (float(a), float(b)), True) for a, b in obs[::3]])
    r = np.sort(dist ** 2); return float(np.mean(r[: int(0.85 * len(r))]))           # trimmed: rounded corners
def nelder_mead(f, x0, step, iters=600):
    n = len(x0); pts = [np.array(x0, float)] + [np.array(x0, float) + np.eye(n)[i] * step[i] for i in range(n)]
    vals = [f(p) for p in pts]
    for _ in range(iters):
        o = np.argsort(vals); pts = [pts[i] for i in o]; vals = [vals[i] for i in o]
        c = np.mean(pts[:-1], axis=0); xr = c + (c - pts[-1]); fr = f(xr)
        if fr < vals[0]:
            xe = c + 2 * (c - pts[-1]); fe = f(xe); pts[-1], vals[-1] = (xe, fe) if fe < fr else (xr, fr)
        elif fr < vals[-2]: pts[-1], vals[-1] = xr, fr
        else:
            xc = c + 0.5 * (pts[-1] - c); fc = f(xc)
            if fc < vals[-1]: pts[-1], vals[-1] = xc, fc
            else:
                pts = [pts[0]] + [pts[0] + 0.5 * (p - pts[0]) for p in pts[1:]]; vals = [vals[0]] + [f(p) for p in pts[1:]]
    return pts[int(np.argmin(vals))], min(vals)
(cx, cy), (a, b), ang = cv2.minAreaRect(obs.astype(np.float32))
L0, W0, ang0 = (a, b, ang) if a >= b else (b, a, ang + 90)
x0 = [cx, cy, ang0, L0 * 0.85, W0 * 0.85]
best, val = nelder_mead(cost, x0, [0.5, 0.5, 3, 0.5, 0.5])
best, val = nelder_mead(cost, best, [0.1, 0.1, 0.5, 0.1, 0.1])
x, y, ang, Lb, Wb = best
print(f"point under camera ({cam.nadir[0]:.2f}, {cam.nadir[1]:.2f}); cage centre is {np.hypot(x - cam.nadir[0], y - cam.nadir[1]):.1f} in away from it")
print(f"CAGE (bottom on belt): centre X {x:.3f}  Y {y:.3f} in, angle {((ang + 90) % 180) - 90:+.2f} deg")
print(f"   bottom {Lb:.2f} x {Wb:.2f} in   rim {Lb + 2*TAPER:.2f} x {Wb + 2*TAPER:.2f} in   fit residual rms {np.sqrt(val):.3f} in")
print(f"   (naive outline box, no 3-D model: {L0:.2f} x {W0:.2f} in)")
vis = img.copy()
for z, col, dims in ((BELT, (255, 0, 0), (Lb, Wb)), (BELT + CAGE_H, (0, 200, 0), (Lb + 2*TAPER, Wb + 2*TAPER))):
    pts = cam.from_height(corners(np.array([x, y]), ang, *dims), z)
    ip = cv2.perspectiveTransform(pts.reshape(-1, 1, 2), cal.H_inv).reshape(-1, 2).astype(np.int32)
    cv2.polylines(vis, [ip], True, col, 2, cv2.LINE_AA)
ipo = cv2.perspectiveTransform(obs.reshape(-1, 1, 2), cal.H_inv).reshape(-1, 2).astype(np.int32)
cv2.polylines(vis, [ipo], True, (0, 0, 255), 1, cv2.LINE_AA)
x_, y_, w_, h_ = cv2.boundingRect(ipo); cv2.imwrite(d + r"\fit3d.jpg", vis[max(y_ - 60, 0):y_ + h_ + 60, max(x_ - 60, 0):x_ + w_ + 60])
