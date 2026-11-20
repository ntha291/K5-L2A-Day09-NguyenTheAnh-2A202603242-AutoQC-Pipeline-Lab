"""CHECK 6 — Ý kiến thứ hai: so nhãn với một model LỚN HƠN (yolo26l).   ★★★ (khó nhất, đáng điểm nhất)

Test:  pytest tests/test_second_opinion.py -q

Máy kiểm quy tắc, người kiểm ý nghĩa (slide). Các lỗi như thiếu nhãn / gán nhầm lớp hợp lệ / box lỏng
KHÔNG bắt được bằng quy tắc cú pháp. Ta nhờ một model mạnh hơn "nhìn lại" và CHỈ CẢNH BÁO (model cũng có thể sai):
những ảnh bị cờ sẽ vào hàng đợi cho NGƯỜI duyệt.

`preds[stem]` = list `[id_lớp, conf, cx, cy, w, h]` của model (lấy qua `get_preds(ds, cfg, "checker")` nếu preds=None).
`L = ds.valid_boxes(stem)` = list `(id_lớp, cx, cy, w, h)` của nhãn (đã bỏ dòng hỏng).
Ngưỡng ở `cfg["second_opinion"]`: conf, min_area_px, fp_conf, iou_missing, iou_match, iou_loose.

Thuật toán gợi ý, với từng ảnh (bỏ qua ảnh không có trong preds hoặc không có file nhãn):
  P = dự đoán có conf >= conf  VÀ diện tích px (w*W * h*H) >= min_area_px
  Với mỗi dự đoán r trong P: lấy các nhãn có IoU(r, nhãn) >= iou_missing  (cands)
   - không có cands                            -> POSSIBLE_MISSING     (model thấy vật mà nhãn không có box)
   - có cands cùng lớp, tốt nhất IoU < iou_loose -> POSSIBLE_LOOSE_BOX  (đúng vật, box lỏng/lệch)
   - không có cands cùng lớp, nhưng cands tốt nhất IoU >= iou_match (khác lớp) -> POSSIBLE_WRONG_CLASS
  Với mỗi dòng nhãn hợp lệ: nếu IoU với MỌI dự đoán (conf >= fp_conf, không lọc diện tích) đều < iou_missing
                                             -> POSSIBLE_FALSE_POS  (box nhãn không khớp vật nào model thấy; Issue.line = số dòng)
"""
from ..common import WARN, Issue, iou_xywh, parse_yolo_line
from ..model_cache import get_preds


def run(ds, cfg, preds=None):
    if preds is None:
        preds = get_preds(ds, cfg, "checker")

    so_cfg = cfg.get("second_opinion", {})
    conf_thresh = so_cfg.get("conf", 0.25)
    min_area_px = so_cfg.get("min_area_px", 600)
    fp_conf = so_cfg.get("fp_conf", 0.1)
    iou_missing = so_cfg.get("iou_missing", 0.3)
    iou_match = so_cfg.get("iou_match", 0.5)
    iou_loose = so_cfg.get("iou_loose", 0.5)

    num_classes = len(ds.classes)
    issues = []

    for img_path in ds.image_files():
        stem = img_path.stem
        if stem not in preds:
            continue
        if not ds.label_path(stem).exists():
            continue

        im_size = ds.image_size(stem)
        img_w, img_h = im_size if im_size is not None else (1, 1)

        raw_preds = preds.get(stem, [])

        # Lấy danh sách các dòng nhãn hợp lệ (giữ số dòng 1-based)
        label_lines = ds.read_label_lines(stem) or []
        valid_label_items: list[tuple[int, int, tuple[float, float, float, float]]] = []
        for line_num, line_str in label_lines:
            try:
                c, cx, cy, w, h = parse_yolo_line(line_str)
            except ValueError:
                continue
            if 0 <= c < num_classes:
                valid_label_items.append((line_num, c, (cx, cy, w, h)))

        # 1. Lọc dự đoán P: conf >= conf_thresh VÀ diện tích >= min_area_px
        P = []
        for p in raw_preds:
            cls_p, conf_p, cx_p, cy_p, w_p, h_p = p[0], p[1], p[2], p[3], p[4], p[5]
            area_px = (w_p * img_w) * (h_p * img_h)
            if conf_p >= conf_thresh and area_px >= min_area_px:
                P.append((int(cls_p), float(conf_p), (float(cx_p), float(cy_p), float(w_p), float(h_p))))

        # 2. Với mỗi dự đoán r trong P: so sánh với các nhãn
        for cls_r, conf_r, box_r in P:
            # cands: các nhãn có IoU >= iou_missing
            cands = []
            for _, lbl_c, lbl_box in valid_label_items:
                iou_val = iou_xywh(box_r, lbl_box)
                if iou_val >= iou_missing:
                    cands.append((lbl_c, lbl_box, iou_val))

            if not cands:
                issues.append(
                    Issue(
                        "second_opinion",
                        WARN,
                        "POSSIBLE_MISSING",
                        stem,
                        f"model thấy vật lớp {cls_r} ({ds.classes[cls_r]}) conf={conf_r:.2f} nhưng không có nhãn",
                        line=None,
                        extra={"conf": conf_r, "pred_class": cls_r},
                    )
                )
            else:
                same_class_cands = [c for c in cands if c[0] == cls_r]
                if same_class_cands:
                    best_same_iou = max(c[2] for c in same_class_cands)
                    if best_same_iou < iou_loose:
                        issues.append(
                            Issue(
                                "second_opinion",
                                WARN,
                                "POSSIBLE_LOOSE_BOX",
                                stem,
                                f"nhãn lớp {cls_r} có IoU={best_same_iou:.2f} < {iou_loose} với dự đoán",
                                line=None,
                                extra={"iou": best_same_iou, "conf": conf_r, "class": cls_r},
                            )
                        )
                    # Nếu best_same_iou >= iou_loose -> đúng vật, không cờ gì
                else:
                    # Không có cands cùng lớp
                    best_other_iou = max(c[2] for c in cands)
                    if best_other_iou >= iou_match:
                        best_cand = max(cands, key=lambda c: c[2])
                        other_cls = best_cand[0]
                        issues.append(
                            Issue(
                                "second_opinion",
                                WARN,
                                "POSSIBLE_WRONG_CLASS",
                                stem,
                                f"nhãn ghi lớp {other_cls} ({ds.classes[other_cls]}) nhưng model đoán lớp {cls_r} ({ds.classes[cls_r]}) conf={conf_r:.2f}, IoU={best_other_iou:.2f}",
                                line=None,
                                extra={
                                    "conf": conf_r,
                                    "iou": best_other_iou,
                                    "pred_class": cls_r,
                                    "label_class": other_cls,
                                },
                            )
                        )
                    # Nếu best_other_iou < iou_match -> mơ hồ, không cờ gì

        # 3. Với mỗi dòng nhãn hợp lệ: kiểm tra POSSIBLE_FALSE_POS
        # Dự đoán dùng để kiểm tra false positive: conf >= fp_conf (không lọc diện tích)
        fp_preds = [
            (int(p[0]), float(p[1]), (float(p[2]), float(p[3]), float(p[4]), float(p[5])))
            for p in raw_preds
            if p[1] >= fp_conf
        ]

        for line_num, lbl_c, lbl_box in valid_label_items:
            has_match = any(
                iou_xywh(lbl_box, p_box) >= iou_missing
                for _, _, p_box in fp_preds
            )
            if not has_match:
                issues.append(
                    Issue(
                        "second_opinion",
                        WARN,
                        "POSSIBLE_FALSE_POS",
                        stem,
                        f"box nhãn không khớp dự đoán nào của model (dòng {line_num})",
                        line=line_num,
                        extra={"line": line_num, "class": lbl_c},
                    )
                )

    return issues
