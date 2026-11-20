"""CHECK 2 — Dòng nhãn YOLO: sai định dạng, ID lớp lạ, box tràn ảnh, box rỗng, box lặp.   (Script 2 trong slide)   ★★

Test:  pytest tests/test_label_format.py -q

Mỗi dòng nhãn: `id cx cy w h` (5 số, toạ độ 0–1). Trả về list[Issue]; `Issue.line` = số dòng (đếm từ 1).

| code             | severity | khi nào                                                                  |
|------------------|----------|--------------------------------------------------------------------------|
| BAD_FORMAT       | ERROR    | không đúng 5 cột số (dùng `parse_yolo_line`, bắt `ValueError`)           |
| BAD_CLASS_ID     | ERROR    | id lớp ngoài 0..len(ds.classes)-1                                        |
| BOX_ZERO         | ERROR    | w <= 0 hoặc h <= 0                                                       |
| BOX_OUT_OF_IMAGE | ERROR    | mép box vượt [0,1] quá `cfg["label_format"]["overflow_tol"]`; extra={"overflow": mức tràn} |
| DUP_BOX          | ERROR    | cùng lớp với một dòng TRƯỚC ĐÓ và IoU > `dup_box_iou`; báo ở dòng SAU    |
| BOX_TINY         | WARN     | cạnh ngắn của box (px) < `min_box_px`  (cần `ds.image_size(stem)`)       |
| BOX_HUGE         | WARN     | w*h > `max_box_frac`                                                     |
"""
from ..common import ERROR, WARN, Issue, iou_xywh, parse_yolo_line


def run(ds, cfg):
    issues = []
    lf_cfg = cfg.get("label_format", {})
    overflow_tol = lf_cfg.get("overflow_tol", 0.001)
    min_box_px = lf_cfg.get("min_box_px", 12)
    max_box_frac = lf_cfg.get("max_box_frac", 0.95)
    dup_box_iou = lf_cfg.get("dup_box_iou", 0.9)
    num_classes = len(ds.classes)

    for lab_path in ds.label_files():
        stem = lab_path.stem
        lines = ds.read_label_lines(stem)
        if not lines:
            continue

        im_size = ds.image_size(stem)
        valid_boxes: list[tuple[int, tuple[float, float, float, float], int]] = []

        for line_num, line_str in lines:
            try:
                c, cx, cy, w, h = parse_yolo_line(line_str)
            except ValueError:
                issues.append(Issue("label_format", ERROR, "BAD_FORMAT", stem, f"sai định dạng: {line_str!r}", line=line_num))
                continue

            if c < 0 or c >= num_classes:
                issues.append(Issue("label_format", ERROR, "BAD_CLASS_ID", stem, f"id lớp {c} ngoài phạm vi 0..{num_classes-1}", line=line_num))
                continue

            if w <= 0 or h <= 0:
                issues.append(Issue("label_format", ERROR, "BOX_ZERO", stem, f"kích thước không dương: w={w}, h={h}", line=line_num))
                continue

            box = (cx, cy, w, h)
            left = cx - w / 2.0
            top = cy - h / 2.0
            right = cx + w / 2.0
            bottom = cy + h / 2.0

            overflow = max(0.0, -left, -top, right - 1.0, bottom - 1.0)
            if overflow > overflow_tol:
                issues.append(Issue("label_format", ERROR, "BOX_OUT_OF_IMAGE", stem, f"box tràn ảnh (mức tràn {overflow:.4f})", line=line_num, extra={"overflow": overflow}))

            is_dup = False
            for prev_c, prev_box, prev_line in valid_boxes:
                if prev_c == c and iou_xywh(box, prev_box) > dup_box_iou:
                    issues.append(Issue("label_format", ERROR, "DUP_BOX", stem, f"box lặp (IoU > {dup_box_iou}) với dòng {prev_line}", line=line_num))
                    is_dup = True
                    break

            valid_boxes.append((c, box, line_num))

            if im_size is not None:
                img_w, img_h = im_size
                box_w_px = w * img_w
                box_h_px = h * img_h
                short_side_px = min(box_w_px, box_h_px)
                if short_side_px < min_box_px:
                    issues.append(Issue("label_format", WARN, "BOX_TINY", stem, f"box quá nhỏ ({short_side_px:.1f}px < {min_box_px}px)", line=line_num))

            if w * h > max_box_frac:
                issues.append(Issue("label_format", WARN, "BOX_HUGE", stem, f"box quá lớn ({w*h:.3f} > {max_box_frac})", line=line_num))

    return issues
