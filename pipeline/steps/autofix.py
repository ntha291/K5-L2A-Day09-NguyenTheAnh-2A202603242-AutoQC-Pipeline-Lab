"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |
"""
from collections import defaultdict

import yaml

from ..common import ERROR, parse_yolo_line

REMOVE_IMAGE_CODES = {
    "DUP_IMAGE_EXACT",
    "DUP_IMAGE_NEAR",
    "LEAK_TEST",
    "CORRUPT_IMAGE",
    "BAD_SIZE",
}
DROP_LINE_CODES = {
    "BAD_FORMAT",
    "BAD_CLASS_ID",
    "BOX_ZERO",
    "DUP_BOX",
}


def fix(ds, issues, cfg):
    # Lọc chỉ các lỗi bắt buộc (severity ERROR)
    error_issues = [i for i in issues if i.severity == ERROR]
    if not error_issues:
        return []

    fixes: list[dict] = []
    removed_stems: set[str] = set()

    # 1. Xử lý lỗi cấp dataset (data.yaml)
    has_bad_class_name = any(i.code == "BAD_CLASS_NAME" for i in error_issues)
    if has_bad_class_name and ds.yaml_path.exists():
        try:
            data = yaml.safe_load(ds.yaml_path.read_text(encoding="utf-8")) or {}
        except Exception:
            data = {}
        before_names = data.get("names", "")
        data["names"] = {i: name for i, name in enumerate(cfg["classes"])}
        ds.yaml_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        fixes.append({
            "image": "data.yaml",
            "line": "",
            "action": "rename_classes",
            "before": str(before_names),
            "after": str(cfg["classes"]),
        })

    # 2. Xử lý xoá ảnh (DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE)
    for issue in error_issues:
        code = issue.code
        if code in REMOVE_IMAGE_CODES or code.startswith("DUP_IMAGE_"):
            stem = issue.image
            if stem not in removed_stems:
                removed_stems.add(stem)
                img_path = ds.image_path(stem)
                if img_path and img_path.exists():
                    try:
                        img_path.unlink()
                    except OSError:
                        pass
                lbl_path = ds.label_path(stem)
                if lbl_path.exists():
                    try:
                        lbl_path.unlink()
                    except OSError:
                        pass
                ds._size_cache.pop(stem, None)
                fixes.append({
                    "image": stem,
                    "line": "",
                    "action": "remove_image",
                    "before": f"ảnh/nhãn {stem}",
                    "after": "(đã xoá)",
                })

    # 3. Xử lý MISSING_LABEL_FILE (needs_label)
    for issue in error_issues:
        if issue.code == "MISSING_LABEL_FILE":
            stem = issue.image
            if stem not in removed_stems:
                fixes.append({
                    "image": stem,
                    "line": "",
                    "action": "needs_label",
                    "before": "(không có file)",
                    "after": "chuyển người gán",
                })

    # 4. Gom các lỗi theo file nhãn và theo từng dòng
    # file_line_issues[stem][line_num] = list[Issue]
    file_line_issues: dict[str, dict[int, list]] = defaultdict(lambda: defaultdict(list))
    for issue in error_issues:
        if issue.code in DROP_LINE_CODES or issue.code == "BOX_OUT_OF_IMAGE":
            stem = issue.image
            if stem in removed_stems or issue.line is None:
                continue
            file_line_issues[stem][int(issue.line)].append(issue)

    # 5. Duyệt và sửa từng file nhãn
    for stem, line_issues in file_line_issues.items():
        lbl_path = ds.label_path(stem)
        if not lbl_path.exists():
            continue

        raw_lines = lbl_path.read_text(encoding="utf-8", errors="replace").splitlines()
        new_lines: list[str] = []
        file_fixes: list[dict] = []

        for line_idx, raw_line in enumerate(raw_lines, 1):
            if line_idx not in line_issues:
                new_lines.append(raw_line)
                continue

            current_issues = line_issues[line_idx]
            has_drop = any(i.code in DROP_LINE_CODES for i in current_issues)
            has_overflow = any(i.code == "BOX_OUT_OF_IMAGE" for i in current_issues)

            if has_drop:
                # Xoá dòng thắng
                file_fixes.append({
                    "image": stem,
                    "line": line_idx,
                    "action": "drop_line",
                    "before": raw_line,
                    "after": "",
                })
            elif has_overflow:
                # Thử cắt box về [0, 1]
                try:
                    c, cx, cy, w, h = parse_yolo_line(raw_line)
                    x1 = cx - w / 2.0
                    x2 = cx + w / 2.0
                    y1 = cy - h / 2.0
                    y2 = cy + h / 2.0

                    cx1 = max(0.0, min(1.0, x1))
                    cx2 = max(0.0, min(1.0, x2))
                    cy1 = max(0.0, min(1.0, y1))
                    cy2 = max(0.0, min(1.0, y2))

                    new_w = cx2 - cx1
                    new_h = cy2 - cy1

                    if new_w <= 0.0 or new_h <= 0.0:
                        # Box nằm hẳn ngoài ảnh -> xoá dòng
                        file_fixes.append({
                            "image": stem,
                            "line": line_idx,
                            "action": "drop_line",
                            "before": raw_line,
                            "after": "",
                        })
                    else:
                        new_cx = (cx1 + cx2) / 2.0
                        new_cy = (cy1 + cy2) / 2.0
                        clipped_line = f"{c} {new_cx:.6f} {new_cy:.6f} {new_w:.6f} {new_h:.6f}"
                        new_lines.append(clipped_line)
                        file_fixes.append({
                            "image": stem,
                            "line": line_idx,
                            "action": "clip_box",
                            "before": raw_line,
                            "after": clipped_line,
                        })
                except ValueError:
                    # Nếu dòng không parse được mà có BOX_OUT_OF_IMAGE, xoá dòng
                    file_fixes.append({
                        "image": stem,
                        "line": line_idx,
                        "action": "drop_line",
                        "before": raw_line,
                        "after": "",
                    })
            else:
                new_lines.append(raw_line)

        # Ghi lại file nhãn
        lbl_path.write_text(
            "\n".join(new_lines) + ("\n" if new_lines else ""),
            encoding="utf-8",
        )
        fixes.extend(file_fixes)

    return fixes
