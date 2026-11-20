# Báo cáo Day 09 — Nguyễn Thế Anh, 2A202603242

## 1. Kết luận trước
Pipeline tự động kết luận: **Hold** (mã thoát 10).
- **Số lượng ảnh đầu vào**: 224 ảnh thô (`data/raw`). Tại Bước 1 (Intake), bộ lọc loại bỏ 21 ảnh lỗi (2 ảnh hỏng không mở được, 3 ảnh kích thước nhỏ dưới 250px, 8 ảnh trùng tuyệt đối MD5, 3 ảnh trùng gần đúng pHash, 5 ảnh rò rỉ từ tập test/val). Nhận 203 ảnh sạch vào luồng kiểm tra.
- **Số lượng ảnh xuất ra**: 203 ảnh được xuất ra thư mục `submission/export/clean_v1/` kèm `manifest.json`. Bản này được gắn cờ là bản nháp thử nghiệm (chưa phát hành chính thức).
- **Lý do chính**: Không còn lỗi bắt buộc nào (`n_errors = 0` sau khi máy tự động sửa 35 lỗi và người duyệt giải quyết 6 ảnh thiếu nhãn). Tuy nhiên, sau khi hoàn thành ngân sách duyệt 80 ảnh, vẫn còn **44/203 ảnh mang cảnh báo ngữ nghĩa chưa được duyệt** (tỉ lệ cảnh báo là 21.67%), vượt ngưỡng cho phép `warn_ratio_hold = 10.00%`. Vì vậy, cổng an toàn kích hoạt trạng thái **Hold**; không được phát hành bản này.

---

## 2. Lỗi và phân việc
Tổng hợp các lỗi phát hiện từ `02_error_list_v1` (tổng số lỗi ban đầu trên 203 ảnh):

| Mã lỗi | Số ảnh/dòng | Ai sửa (máy/người) | Vì sao |
|---|---:|---|---|
| `CORRUPT_IMAGE` | 2 ảnh | Máy (autofix) | Ảnh hỏng file không mở được (`OSError`, `UnidentifiedImageError`), không thể hiển thị hay huấn luyện; máy tự xoá an toàn (`remove_image`). |
| `BAD_SIZE` | 3 ảnh | Máy (autofix) | Cạnh ngắn ảnh < 250px, vi phạm quy định kích thước đầu vào của dự án; máy tự loại bỏ (`remove_image`). |
| `DUP_IMAGE_EXACT` | 8 ảnh | Máy (autofix) | Ảnh trùng khớp từng byte (MD5 giống hệt ảnh đã có); máy giữ ảnh đầu tiên và tự xoá các bản trùng lặp (`remove_image`). |
| `DUP_IMAGE_NEAR` | 3 ảnh | Máy (autofix) | Ảnh chụp gần trùng (khoảng cách Hamming pHash ≤ 8); máy tự xoá ảnh lặp để tránh bias dữ liệu (`remove_image`). |
| `LEAK_TEST` | 5 ảnh | Máy (autofix) | Ảnh trùng với kho test/gold_val; máy loại bỏ ngay lập tức để tránh data leakage gây sai lệch đánh giá (`remove_image`). |
| `BAD_CLASS_NAME` | 2 lỗi | Máy (autofix) | Tên lớp trong `data.yaml` bị viết hoa sai chuẩn (`Person`, `Bus`); máy tự chuẩn hoá lại theo `cfg["classes"]` (`rename_classes`). |
| `BAD_FORMAT` | 3 dòng | Máy (autofix) | Dòng nhãn thiếu cột toạ độ hoặc chứa giá trị NaN; máy tự xoá dòng hỏng khỏi file nhãn (`drop_line`). |
| `BAD_CLASS_ID` | 6 dòng | Máy (autofix) | ID lớp nằm ngoài phạm vi 0..3 (vd: 93, 7, 4, -1); máy tự xoá dòng sai cú pháp (`drop_line`). |
| `BOX_ZERO` | 4 dòng | Máy (autofix) | Bounding box có chiều rộng hoặc chiều cao ≤ 0; máy tự xoá dòng rỗng (`drop_line`). |
| `BOX_OUT_OF_IMAGE` | 8 dòng | Máy (autofix) | Box có mép tràn ra ngoài khung ảnh [0, 1] vượt dung sai; máy tự động cắt toạ độ mép về đúng biên [0, 1] (`clip_box`). |
| `DUP_BOX` | 7 dòng | Máy (autofix) | Cùng lớp và trùng lặp với box trước đó trong cùng ảnh (IoU > 0.9); máy tự xoá dòng lặp đứng sau (`drop_line`). |
| `MISSING_LABEL_FILE` | 6 ảnh | Người (hàng đợi) | Ảnh thô không có file nhãn; máy không được phép bịa nhãn (kể cả tạo file rỗng vì rỗng nghĩa là ảnh nền); bắt buộc chuyển người gán (`needs_label`). |
| `BOX_HUGE` | 3 dòng | Người (hàng đợi) | Box chiếm > 95% khung ảnh; người duyệt cần kiểm tra xem là vật thể cận cảnh thật hay do gán nhãn cẩu thả trùm toàn màn hình. |
| `BOX_TINY` | 6 dòng | Người (hàng đợi) | Cạnh ngắn box < 12px; người duyệt kiểm tra xem có phải chi tiết quá nhỏ/nhiễu vi phạm guideline nhận diện hay không. |
| `CLASS_RARE` | 4 ảnh | Người (hàng đợi) | Lớp xuất hiện quá ít (< 5 box trong toàn bộ dataset); người duyệt cần xem xét để bổ sung mẫu cân bằng lớp. |
| `EMPTY_LABEL` | 12 ảnh | Người (hàng đợi) | File nhãn rỗng; người duyệt cần xác nhận đây thực sự là ảnh nền (negative image) hay do người gán nhãn bỏ quên. |
| `POSSIBLE_FALSE_POS` | 29 dòng | Người (hàng đợi) | Box nhãn không khớp với bất kỳ phát hiện nào của model yolo26l; người duyệt kiểm tra xem có phải nhãn ảo/nhãn vẽ sai vị trí. |
| `POSSIBLE_LOOSE_BOX` | 31 dòng | Người (hàng đợi) | Đúng lớp nhưng IoU giữa nhãn và model < 0.5; người duyệt căn chỉnh lại mép bounding box cho khít với vật thể. |
| `POSSIBLE_MISSING` | 68 lỗi | Người (hàng đợi) | Model checker phát hiện vật thể rõ nét (conf ≥ 0.50, diện tích ≥ 600px²) nhưng nhãn bị thiếu; người duyệt cần vẽ bổ sung box. |
| `POSSIBLE_WRONG_CLASS` | 18 dòng | Người (hàng đợi) | Box khớp vị trí nhưng khác lớp (vd: truck vs car, car vs person); người duyệt xác định nhãn ngữ nghĩa chuẩn xác. |

### Phân tích hàng đợi duyệt (`05_review_queue.csv`)
- **Vì sao xếp các ảnh đầu hàng như vậy**: Thuật toán `build_queue` chấm điểm ưu tiên dựa trên trọng số lỗi dự án (`review.weights`). Điểm số cao nhất thuộc về `NEEDS_LABEL` (trọng số 10) vì ảnh thiếu nhãn là lỗi bắt buộc chặn đứng pipeline (Rework). Do đó, toàn bộ 6 ảnh thiếu nhãn (`img_0031`, `img_0053`, `img_0126`, `img_0135`, `img_0170`, `img_0219`) đều đứng đầu hàng đợi. Tiếp theo là các ảnh có nhiều cảnh báo ngữ nghĩa nặng như `POSSIBLE_WRONG_CLASS` (hệ số 3), `POSSIBLE_MISSING` (hệ số 2), `POSSIBLE_FALSE_POS` (hệ số 2) kết hợp nhân thêm hệ số tin cậy `(1 + conf)` của model dự đoán.
- **Khả năng xử lý với ngân sách 80 ảnh**: Hàng đợi có tổng cộng 130 ảnh cần duyệt. Với ngân sách 80 ảnh, người duyệt (mô phỏng theo `06_review_log.csv`) đã:
  + Gán nhãn cho toàn bộ 6 ảnh thiếu nhãn, loại trừ hoàn toàn nguy cơ Rework.
  + Giải quyết 14/18 lỗi `POSSIBLE_WRONG_CLASS` (giảm xuống còn 4 lỗi).
  + Giải quyết 42/68 lỗi `POSSIBLE_MISSING` (giảm xuống còn 26 lỗi).
  + Giải quyết 9/29 lỗi `POSSIBLE_FALSE_POS` (giảm xuống còn 20 lỗi).
  + Giải quyết 7/31 lỗi `POSSIBLE_LOOSE_BOX` (giảm xuống còn 24 lỗi).
  Tuy nhiên, do giới hạn 80 ảnh, vẫn còn 50 ảnh chưa được chạm tới, trong đó có 44 ảnh chứa cảnh báo ngữ nghĩa tồn đọng.

---

## 3. Calibration (2 ngưỡng)
Bảng kết quả hiệu chuẩn trên bộ dữ liệu `data/calib/` (39 ảnh có đáp án chèn lỗi):

| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Lý do (đánh đổi) |
|---|---|---|---|---|
| `duplicates.phash_dist` | 2 | 8 | Exact: 1.00/1.00 → 1.00/1.00<br>Near: 1.00/0.50 (F1=0.67) → 1.00/0.67 (F1=0.80) | `phash_dist = 2` quá chặt, bỏ sót 50% số ảnh gần trùng (Recall chỉ đạt 0.50). Tăng lên `8` giúp Recall tăng lên 0.67 mà Precision vẫn giữ nguyên 1.00 tuyệt đối. Không nâng lên 16 vì trên tập raw sẽ dẫn đến xóa nhầm ảnh khác nhau. |
| `second_opinion.conf` | 0.25 | 0.50 | Wrong class: 0.56/0.83 → 0.56/0.83<br>Missing: 0.50/1.00 (F1=0.67) → 0.57/1.00 (F1=0.73)<br>Loose box: 0.29/0.40 → 0.20/0.20<br>False pos: 0.31/1.00 → 0.31/1.00 | Chọn `conf = 0.50` như một đánh đổi: trên calib, precision của Missing tăng từ 0.50 lên 0.57 và recall giữ ở 1.00; nhưng chỉ số Loose box giảm. Đây không phải ngưỡng tối ưu cho mọi loại cảnh báo, và các cảnh báo từ model vẫn cần người xác minh. |

### Điểm đánh lừa của calibration và bằng chứng thực tế
Tập calibration chỉ có 39 ảnh (kích thước nhỏ). Khi nhìn vào bảng sweep `duplicates.phash_dist`:
- Tại `phash_dist = 16`, trên tập calib chỉ số F1 của `DUP_IMAGE_NEAR` đạt đỉnh 0.91 (Precision 1.00, Recall 0.83, bắt được 5/6 trường hợp chèn).
- **Đây là cảnh báo về khả năng tổng quát hóa ngưỡng**: thử nghiệm intake trên `data/raw` cho thấy tại `phash_dist = 8` có 8 ảnh `DUP_IMAGE_EXACT`, 3 `DUP_IMAGE_NEAR`, 5 `LEAK_TEST`; tại `phash_dist = 16` các số tương ứng là 8, 7 và 11. Tổng các cờ trùng/rò rỉ tăng từ 16 lên 26. Chỉ số trên calib không chứng minh 10 cờ tăng thêm đều là false positive; chúng cần được đối chiếu thủ công trước khi chấp nhận ngưỡng cao hơn.
- **Bài học**: Vì `autofix` loại ảnh có cờ trùng/rò rỉ, tăng ngưỡng dựa riêng vào F1 của calib có thể làm thay đổi đáng kể số ảnh bị loại trên raw. Với thao tác loại ảnh, cần kiểm tra các cặp bị gắn cờ để cân bằng bỏ sót trùng lặp với nguy cơ loại nhầm ảnh tốt.

---

## 4. Cửa chặn và điều pipeline KHÔNG bắt được
### (a) Chứng minh cửa chặn hoạt động chính xác
Chạy thử nghiệm mô phỏng không có người duyệt (`budget = 0`):
```bash
python -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb
```
- **Hiện tượng**: Không có ngân sách duyệt, 6 ảnh thiếu file nhãn (`MISSING_LABEL_FILE`) không được gán nhãn thủ công và vẫn tồn tại nguyên vẹn sau vòng sửa tự động (vì máy không được phép bịa nhãn).
- **Kết quả cửa chặn**: Bước gate kiểm tra thấy còn `n_errors = 6` và ngay lập tức trả về kết luận:
  `REWORK — Còn 6 lỗi bắt buộc cần sửa chữa hoặc loại bỏ (Rework)`.
- **Mã thoát**: Lệnh kết thúc với mã thoát `20` (chuẩn mã cho Rework).
- **Cửa chặn thực sự chặn xuất**: Pipeline dừng lại ở bước 5 với thông báo `Bước 5/5 KHÔNG xuất: còn lỗi bắt buộc (Rework) — trả về bước 3`. Toàn bộ thư mục `work/exp_nb/clean_v1` không được tạo ra. Điều này chứng minh cửa chặn hoạt động đúng thiết kế: khi còn lỗi bắt buộc, dữ liệu tuyệt đối không được phát hành.

### (b) Các điểm mù pipeline không bắt được
1. **Box lỏng nhẹ hoặc lệch nhẹ (IoU từ 0.5 đến 0.7)**: Theo cấu hình, `iou_loose = 0.5` và `iou_match = 0.5`. Nếu nhãn của người vẽ box hơi rộng hoặc lệch mép nhưng IoU với dự đoán model vẫn đạt 0.52–0.60, hệ thống coi là "trùng khớp đúng vật" và hoàn toàn im lặng. Các box người đi bộ bao trùm cả nền xung quanh mức độ vừa phải sẽ lọt qua pipeline.
2. **Nhầm lẫn các lớp tương đồng mà cả model lớn cũng nhầm**: Khi gặp các vật thể khó phân biệt (như xe bán tải pickup giữa `truck` và `car`, hoặc xe khách cỡ nhỏ giữa `bus` và `truck`), nếu cả nhãn người và model `yolo26l` đều phân loại sai giống nhau, hệ thống ghi nhận là đồng thuận (`agreement is silent`) và bỏ sót lỗi này hoàn toàn.
3. **Ảnh trùng bị biến đổi hình học mạnh hoặc crop sâu (> 50%)**: Thuật toán pHash 64-bit dựa trên phổ tần số thấp DCT chỉ chịu được nén nhẹ, đổi màu hoặc resize tỷ lệ nhỏ. Nếu ảnh bị xoay góc 45 độ, cắt cụt 60% diện tích hoặc ghép watermark lớn, khoảng cách pHash vượt quá ngưỡng 8 và intake sẽ bỏ sót.

---

## 5. Train: raw vs clean (tùy chọn, chấm riêng)
Chưa chạy phần huấn luyện so sánh mô hình raw vs clean do môi trường máy tính cục bộ hiện tại không trang bị GPU chuyên dụng (CUDA available: False).

Theo đúng hướng dẫn tại `GUIDE.md` (Bước 4, 5) và `RUBRIC.md` (Hạng mục 5: phần train Colab là tùy chọn, được chấm riêng 15 điểm; không làm thì sử dụng `make check-core` và báo cáo "chưa chạy" trung thực vẫn bảo lưu tối đa 85/100 điểm phần lõi), mục này được ghi nhận trung thực là **chưa chạy**. Toàn bộ quy trình kiểm định bài nộp được xác thực qua lệnh:
```bash
python scripts/check_submission.py --no-train
```
(tương đương lệnh `make check-core` trong Makefile).

---

## 6. Quyết định và ghi chú AI
### (a) Quyết định cuối cùng
- **Quyết định hiện tại**: **Hold**. Bộ dữ liệu chưa đủ điều kiện phát hành vì còn 44/203 ảnh chứa cảnh báo chưa được hậu kiểm (tỉ lệ 21.67% > ngưỡng 10%).
- **Điều kiện để chuyển thành Release**:
  1. Giữ nguyên `review.budget_images = 80` và `gate.warn_ratio_hold = 0.10` theo quy định; không nới ngân sách hay ngưỡng để ép Release.
  2. Chỉ chuyển sang **Release** nếu một lần duyệt hợp lệ tiếp theo xác minh được cảnh báo và kết quả cuối còn dưới 20 ảnh cảnh báo chưa xử lý (dưới 10% của 203 ảnh). Với kết quả hiện tại, điều kiện này chưa đạt nên phải giữ **Hold**.

### (b) Ghi chú sử dụng AI
- **Prompt chính**: Yêu cầu AI hiện thực hoá chính xác 4 module theo phong cách Test-Driven Development (TDD): nhận vào Dataset/config/preds, trả về danh sách Issue, dict decision, hoặc list fix theo đúng chuẩn YOLO, xử lý triệt để các trường hợp biên (dòng trống, toạ độ tràn, xoá ảnh trùng, không bịa nhãn).
- **Cách kiểm tra code AI**: Chạy bộ kiểm thử tự động 79 bài test (`python -m pytest -q` đạt 100% passed); rà soát tĩnh bằng `scripts/check_submission.py` để đảm bảo không vi phạm tệp bảo vệ `_protected.json` (không đọc file đáp án, không sửa đổi cấu hình cố định); và chạy thực nghiệm đối chiếu kết quả trên dữ liệu thật `data/raw`.
- **Một lần AI sai**: Khi lập trình hàm `clip_box` trong `autofix.py`, ban đầu AI viết code cắt toạ độ nhưng lại không xử lý trường hợp box nằm hoàn toàn ngoài khung ảnh (`new_w <= 0` hoặc `new_h <= 0`), dẫn đến việc tính toán ra tâm box và toạ độ âm hoặc bằng 0, kích hoạt thêm lỗi `BOX_ZERO`. Sau khi kiểm tra với ca test `test_box_fully_outside_is_dropped_not_negative`, logic đã được sửa đổi: nếu sau khi cắt mà kích thước box ≤ 0 thì phải chuyển action thành `drop_line` để xoá dòng khỏi file nhãn.

---

### *(Thưởng +2, tùy chọn)* Khảo sát bộ lọc kích thước hộp trên CVAT
Theo tài liệu `docs/CVAT_FILTER.md` và tệp cấu hình nhãn `cvat/labels.json`:
- **Áp dụng bộ lọc**: Trong CVAT, sử dụng câu lệnh lọc `width < 20` hoặc `height < 20` để tạo một vòng lọc sơ bộ rộng hơn. Pipeline chỉ gắn cảnh báo `BOX_TINY` khi cạnh ngắn dưới 12px; vì vậy các box 12–20px cần được xem xét theo guideline thay vì mặc định coi là lỗi. Các box nhỏ có thể là người đi bộ hoặc xe cộ ở hậu cảnh xa xôi trong ảnh COCO.
- **Ý nghĩa `can_review`**: Thuộc tính và cơ chế phân quyền `can_review` trong CVAT đảm bảo sự tách biệt trách nhiệm: người gán nhãn sơ bộ (annotator) không thể tự ý xoá hay bỏ qua các box nhỏ bị nghi ngờ, mà quyền phê duyệt/loại bỏ box thuộc về chuyên viên kiểm định chất lượng (reviewer/QA) sau khi đã đối chiếu với tài liệu quy chuẩn kích thước tối thiểu của dự án.
