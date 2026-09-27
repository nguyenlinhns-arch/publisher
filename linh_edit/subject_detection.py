from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from statistics import median


@dataclass(frozen=True, slots=True)
class SubjectDetection:
    kind: str
    x: float
    y: float
    width: float
    height: float
    confidence: float


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _cv2():
    try:
        import cv2  # type: ignore
    except Exception:
        return None
    return cv2


def _detect_bgr(
    image,
    cv2,
    *,
    detect_person: bool = True,
) -> SubjectDetection | None:
    if image is None:
        return None
    height, width = image.shape[:2]
    if width <= 0 or height <= 0:
        return None
    # Detection uses normalized coordinates, so downscaling large review frames
    # greatly reduces CPU cost without changing reframe geometry.
    if width > 640:
        scale = 640.0 / width
        image = cv2.resize(
            image,
            (640, max(2, int(round(height * scale)))),
            interpolation=cv2.INTER_AREA,
        )
        height, width = image.shape[:2]

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)

    # Prefer faces because they are the most important mobile-reframe anchor.
    cascade_path = str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml")
    cascade = cv2.CascadeClassifier(cascade_path)
    faces = ()
    if not cascade.empty():
        faces = cascade.detectMultiScale(
            gray,
            scaleFactor=1.10,
            minNeighbors=5,
            minSize=(max(24, width // 16), max(24, height // 16)),
        )
    if len(faces):
        # Use an area-weighted center so two nearby faces keep the group framed.
        total_area = sum(max(1, int(w) * int(h)) for x, y, w, h in faces)
        cx = sum((x + w / 2) * (w * h) for x, y, w, h in faces) / total_area
        cy = sum((y + h / 2) * (w * h) for x, y, w, h in faces) / total_area
        left = min(x for x, y, w, h in faces)
        top = min(y for x, y, w, h in faces)
        right = max(x + w for x, y, w, h in faces)
        bottom = max(y + h for x, y, w, h in faces)
        largest_ratio = max((w * h) / (width * height) for x, y, w, h in faces)
        confidence = min(0.99, 0.72 + min(0.25, largest_ratio * 2.5))
        return SubjectDetection(
            kind="face",
            x=_clamp(cx / width),
            y=_clamp(cy / height),
            width=_clamp((right - left) / width),
            height=_clamp((bottom - top) / height),
            confidence=round(confidence, 4),
        )

    # Fall back to a local HOG person detector. This is slower than face
    # detection, so tracking can disable it during the fast face-only pass.
    if not detect_person:
        return None
    try:
        hog = cv2.HOGDescriptor()
        hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        rects, weights = hog.detectMultiScale(
            image,
            winStride=(8, 8),
            padding=(8, 8),
            scale=1.05,
        )
    except Exception:
        return None
    if len(rects):
        best_index = max(
            range(len(rects)),
            key=lambda index: float(weights[index]) if len(weights) > index else 0.0,
        )
        x, y, w, h = [int(value) for value in rects[best_index]]
        weight = float(weights[best_index]) if len(weights) > best_index else 0.0
        return SubjectDetection(
            kind="person",
            x=_clamp((x + w / 2) / width),
            y=_clamp((y + h / 2) / height),
            width=_clamp(w / width),
            height=_clamp(h / height),
            confidence=round(_clamp(0.45 + min(0.45, max(0.0, weight) / 4)), 4),
        )
    return None


def detect_subject(frame: Path) -> SubjectDetection | None:
    frame = frame.expanduser().resolve()
    cv2 = _cv2()
    if cv2 is None or not frame.is_file():
        return None
    return _detect_bgr(cv2.imread(str(frame)), cv2)


def track_subject_video(
    source: Path,
    *,
    start: float,
    end: float,
    samples: int = 5,
) -> SubjectDetection | None:
    source = source.expanduser().resolve()
    cv2 = _cv2()
    if cv2 is None or not source.is_file():
        return None
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        return None
    samples = max(3, min(9, int(samples)))
    start = max(0.0, float(start))
    end = max(start, float(end))
    if end - start < 0.05:
        points = [start]
    else:
        points = [
            start + (end - start) * index / (samples - 1)
            for index in range(samples)
        ]
    sampled_images = []
    faces: list[SubjectDetection] = []
    try:
        for timestamp in points:
            capture.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000.0)
            ok, image = capture.read()
            if not ok:
                continue
            sampled_images.append(image)
            detected = _detect_bgr(
                image,
                cv2,
                detect_person=False,
            )
            if detected is not None:
                faces.append(detected)
    finally:
        capture.release()

    if faces:
        chosen = faces
        kind = "face"
    else:
        # Person HOG is substantially slower. Run it only on up to three
        # representative frames when the fast face pass found nothing.
        detections: list[SubjectDetection] = []
        if sampled_images:
            indices = sorted(
                set(
                    [
                        0,
                        len(sampled_images) // 2,
                        len(sampled_images) - 1,
                    ]
                )
            )
            for index in indices:
                detected = _detect_bgr(
                    sampled_images[index],
                    cv2,
                    detect_person=True,
                )
                if detected is not None:
                    detections.append(detected)
        if not detections:
            return None
        chosen = detections
        kind = max(chosen, key=lambda item: item.confidence).kind
    return SubjectDetection(
        kind=kind,
        x=round(median(item.x for item in chosen), 4),
        y=round(median(item.y for item in chosen), 4),
        width=round(median(item.width for item in chosen), 4),
        height=round(median(item.height for item in chosen), 4),
        confidence=round(sum(item.confidence for item in chosen) / len(chosen), 4),
    )


def track_subject(frames: tuple[Path, ...]) -> SubjectDetection | None:
    detections = [item for item in (detect_subject(path) for path in frames) if item is not None]
    if not detections:
        return None

    # Prefer face detections when at least half of available detections are faces.
    faces = [item for item in detections if item.kind == "face"]
    chosen = faces if len(faces) >= max(1, len(detections) // 2) else detections
    return SubjectDetection(
        kind="face" if chosen is faces else chosen[0].kind,
        x=round(median(item.x for item in chosen), 4),
        y=round(median(item.y for item in chosen), 4),
        width=round(median(item.width for item in chosen), 4),
        height=round(median(item.height for item in chosen), 4),
        confidence=round(sum(item.confidence for item in chosen) / len(chosen), 4),
    )



def subject_runtime_status() -> dict[str, object]:
    cv2 = _cv2()
    if cv2 is None:
        return {
            "available": False,
            "opencv_version": "",
            "face_model": False,
            "person_model": False,
        }
    cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
    return {
        "available": True,
        "opencv_version": str(getattr(cv2, "__version__", "")),
        "face_model": cascade_path.is_file(),
        "person_model": bool(hasattr(cv2, "HOGDescriptor_getDefaultPeopleDetector")),
    }
