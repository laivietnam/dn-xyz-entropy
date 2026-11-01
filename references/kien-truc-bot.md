# Kiến trúc bot mở/đóng/canh DN trade.xyz × Entropy

Thiết kế của bot Telegram mình đã chạy thật trên ví thật (29/10 → 01/11/2026).
Ghi lại để ai muốn tự xây thì đi đường ngắn hơn. **Không kèm code gửi lệnh.**

Tự xây bot đặt lệnh = tự chịu rủi ro mất tiền. Chạy thử bằng tài khoản giả trước,
rồi tiền nhỏ ($10–20/chân), rồi mới tăng.

---

## 1. Nguyên tắc nền

- **Sàn là nguồn sự thật, không phải file.** Vị thế, ký quỹ, lệnh chờ luôn đọc lại từ
  sàn. File trên máy chỉ nhớ thứ sàn không nhớ hộ (ký quỹ lúc mở, mức TP/SL dự phòng,
  việc mở/đóng đang dở). Bài học từ bot khác: file ghi "đang mở" suốt 10 ngày trong khi
  vị thế đã đóng tay từ lâu.
- **Chế độ thật/thử chỉ nằm ở một chỗ** (`DRY_RUN` trong file cấu hình). Mặc định là THỬ;
  chỉ khi ghi đúng `false` mới chạy thật. Không có cờ dòng lệnh nào ghi đè được.
- **Khóa ký nằm file riêng**, quyền 600, không bao giờ in ra log hay chat.
  Dùng **ví phụ (API wallet)** chỉ ký lệnh, không rút được tiền.
- Ví phụ phải được cấp quyền trên ví giao dịch (`extraAgents`), có ngày hết hạn —
  hết hạn là mọi lệnh bị từ chối. Ghi ngày hết hạn ra chỗ dễ thấy.
- Phân loại lỗi khi gửi lệnh:
  - **Rõ ràng** (sàn trả `status: err`, HTTP 4xx trừ 429): lệnh chắc chắn không chạy.
  - **Mơ hồ** (timeout, mất mạng, 429, 5xx, phản hồi lạ): **không gửi lại**. Đọc sàn
    trước rồi mới quyết, không thì dễ đặt trùng lệnh.

## 2. Các khối

| Khối | Việc |
|---|---|
| Cấu hình | đọc file môi trường, mọi ngưỡng ở một chỗ |
| Lớp sàn | đọc sổ lệnh/funding/nến/vị thế; gửi lệnh qua ví phụ; tài khoản giả khi THỬ |
| Lõi | tách lệnh chữ, chấm 4 tiêu chí, việc mở/đóng, vòng canh, tính lãi/lỗ |
| Telegram | nhận lệnh từ đúng 1 người, nút Xác nhận/Hủy, `/status` `/pnl` `/stop` |

Lệnh chữ ví dụ: `nbis, long xyz, short io, 3x, margin $1000` (margin = mỗi chân),
`close nbis`. Trước khi chạy, bot in kết quả chấm 4 tiêu chí + phí ước tính + giá
thanh lý → người dùng bấm **Xác nhận** (hết hạn 60 giây, bấm thì kiểm lại số).

## 3. Mở / đóng: chờ Entropy, khớp ngay trade.xyz theo phần

Mỗi lúc chỉ một việc mở/đóng (một luồng riêng, có nút dừng).

1. Đặt đòn bẩy **Isolated** cho cả 2 chân (kể cả mã cho phép Cross — một kiểu logic
   cân ký quỹ cho mọi mã).
2. Đặt lệnh **ALO** (chỉ làm Maker) bên Entropy ở giá tốt nhất phía mình.
3. Vòng lặp mỗi ~1,5 giây:
   - Lượng đã khớp bên Entropy = **vị thế thật hiện tại − lúc bắt đầu**.
   - Phần chưa phòng hộ ≥ $500 → lệnh **IOC** bên trade.xyz (trần trượt giá ~10 bps).
   - Giá tốt nhất đổi → hủy và đặt lại lệnh chờ, tối đa 1 lần/5 giây.
   - Không đặt chờ Entropy tệ hơn giá giữa trade.xyz quá ~15 bps (không đuổi giá).
   - Chân trade.xyz khớp lỗi liên tục, hở quá 3 phần → ngưng đặt chờ, báo người dùng.
4. Hết (hoặc quá 60 phút, hoặc bị dừng) → quét sạch lệnh chờ → khớp nốt phần lẻ ≥ $10
   → đọc lại 2 chân trên sàn, lệch thì chỉnh chân trade.xyz cho bằng → đặt TP/SL dự phòng.
5. **Đóng — kể cả đóng khẩn cấp — cũng làm đúng cách này** (lệnh giảm vị thế).
   **Không hủy TP/SL trước khi đóng:** đóng có thể mất tới 60 phút, TP/SL phải còn suốt
   lúc đó. Đóng xong hết mới hủy.

### Hẹn giờ tự hủy (`scheduleCancel`)

Trong lúc mở/đóng, cứ ~20 giây hẹn sàn "60 giây nữa tự hủy mọi lệnh chờ". Bot chết
giữa chừng → sàn tự dọn lệnh chờ.

⚠️ **Hẹn giờ này hủy CẢ TP/SL dự phòng** (đã thử thật). Nên mở/đóng xong phải gỡ hẹn
ngay. Tối đa 10 lần kích hoạt/ngày.

### Quét lệnh chờ trước khi gỡ hẹn

Lệnh gửi lúc mất mạng có thể vẫn nằm trên sàn mà bot không biết số lệnh. Trước khi gỡ
hẹn giờ: chờ ~2 giây → đọc **mọi** lệnh chờ thường (không phải TP/SL) của mã đó trên sàn
→ hủy hết → đọc lại. Còn sót thì **giữ** hẹn giờ để sàn tự hủy, báo người dùng.

### Dừng vì lỗi

Hủy lệnh chờ, gỡ hẹn giờ, rồi **nhận canh phần đã khớp** (ghi sổ + đặt TP/SL) và gửi tin
kèm 2 nút: "Cân lại chân" (IOC trade.xyz cho bằng Entropy) và "Đóng hết".

Khởi động lại mà thấy việc mở/đóng dở → **không tự làm tiếp**. Hủy lệnh chờ, đọc 2 chân,
báo kèm 2 nút trên, người dùng bấm mới chạy.

## 4. Vòng canh (mỗi 15 giây)

Với mỗi mã đang giữ DN:

1. **2 chân lệch** (≥ $10, hoặc mất 1 chân) → báo kèm nút, 10 phút/lần.
2. **DN cân nhưng chưa có sổ** (mở tay, lỗi giữa chừng) → nhận canh: ghi ký quỹ ban
   đầu theo hiện tại + đặt TP/SL.
3. **Cân ký quỹ:** chân thua còn < 80% ký quỹ ban đầu →
   - rút **tiền lời** chân thắng: tối đa `ký quỹ − max(giá trị/đòn bẩy, 10% giá trị)`,
     và không quá một nửa chênh lệch ký quỹ 2 chân;
   - sàn từ chối thì thử rút một nửa, tới khi được hoặc dưới $1;
   - nạp sang chân thua; tài khoản không phải `unifiedAccount` thì chuyển tiền giữa
     2 sàn con trước (lệnh này ký kiểu "người dùng" — ví phụ có thể không ký được);
   - lỗi thì 2 phút sau thử lại, tin báo lỗi tối đa 1 lần/30 phút.
4. **Tự đóng khẩn cấp:** không cân được và chân thua còn < 30% quãng đường tới thanh lý
   (so với lúc mở) → mở việc đóng như mục 3.
5. **TP/SL dự phòng:** 4 lệnh trigger (2 chân × chốt lời/cắt lỗ), **cùng mức giá cho
   2 chân**, ở 85% quãng đường từ giá hiện tại tới giá thanh lý của chân yếu mỗi phía.
   Giá chạm mức trên → chân bán cắt lỗ, chân mua chốt lời cùng lúc; ngược lại tương tự.
   Đặt lại khi giá thanh lý dịch > 1% (sau mỗi lần cân ký quỹ). Kiểm đủ 4 lệnh trên sàn
   tối đa 1 lần/phút; ngay sau mở/đóng thì kiểm mọi vòng trong 90 giây.
   Sàn từ chối TP/SL → báo to ("vị thế đang THIẾU lớp bảo vệ"), thử lại mỗi phút.

### Ngân sách hỏi sàn

1200 điểm/phút/IP, **chung cả máy** (bot khác trên cùng máy cũng tính).
Canh 5 giây/lần từng dính 429 (~624 điểm/phút cho 1 cặp). 15 giây/lần + kiểm TP/SL
1 phút/lần còn ~88 điểm/phút/cặp. Thêm cặp hay thêm lệnh đọc thì tính lại.

Vòng canh lỗi lẻ tẻ chỉ ghi log; lỗi liên tục > 2 phút mới báo, 15 phút/lần, báo khi
đã chạy lại. Tin báo phân biệt: 429 = hỏi quá dày; 502/503/504 = máy chủ Hyperliquid
không trả lời (thường do bảo trì, có thông báo trước trên Discord).

## 5. Lãi/lỗ thật (`/pnl`)

App tính lãi/lỗ theo giá mark — khác giá khớp thật lúc đóng.

- Tách vòng từ lịch sử khớp (`userFillsByTime`): vòng mở khi cả 2 chân của mã từ 0,
  đóng khi cả 2 về 0. Gom các lần khớp cùng mã cùng mili-giây trước khi cộng.
- Lật trang lịch sử: trang sau bắt đầu từ mốc giờ cuối trang trước (**không** +1, vì
  nhiều lần khớp chung 1 mili-giây), rồi bỏ trùng theo mã giao dịch.
- Funding thật (`userFunding`) gán vào vòng đang giữ lúc nhận.
- Phần đang mở: theo giá giữa sổ lệnh; thêm dòng "nếu đóng ngay" (Entropy đóng ở giá
  tốt nhất phía mình, trade.xyz ăn vào sổ) + phí đóng.
- Chỉ tính từ ngày bot chạy, để không lẫn giao dịch tay cũ.

## 6. Bẫy đã gặp

- ⚠️ **SDK Python 0.24.0:** `market_open()` / `_slippage_price()` coi mã ≥ 10000 là spot
  → làm tròn giá sai cho sàn con (mã ~110000+). Tự tính giá: ≤ 5 chữ số có nghĩa **và**
  ≤ (6 − szDecimals) chữ số lẻ.
- Làm tròn size: `floor(round(sz × 10^dec, 9)) / 10^dec` — thiếu `round(…, 9)` thì
  61.812 × 1000 = 61811.999 bị cắt mất 1 bước. 2 sàn có szDecimals khác nhau → dùng
  mức thô hơn cho cả 2 chân.
- `query_order_by_oid` **trễ vài giây** (lệnh đã hủy vẫn báo `open`) → đừng dùng để
  theo dõi khớp; đọc lượng đã khớp từ vị thế thật.
- Python 3.12: lớp kế thừa `threading.Thread` mà đặt thuộc tính tên `_stop` là hỏng
  (đè hàm có sẵn). Đặt tên khác (`_halt`).
- Chữ từ sàn/lỗi chèn vào tin Telegram dạng HTML phải escape, không thì tin bị từ chối
  đúng lúc cần cảnh báo nhất. Gửi lỗi lần 1 → gửi lại dạng chữ thường.
- Tắt log URL của thư viện HTTP: URL Telegram chứa token bot.
- **Ví dùng chung với bot khác:** bot DN tưởng vị thế của bot khác là DN của mình và
  báo "2 chân lệch". Chỉ coi là mã DN nếu có chân Entropy hoặc đã có sổ do chính bot ghi.
- Mỗi token Telegram chỉ chạy **một máy**. Hai bản cùng nhận tin = hai bản cùng đặt lệnh.
- Ví giao dịch là **sub-account** thì có thể mất giảm phí giới thiệu — kiểm lại trước khi
  chọn. Bot từ chối chạy nếu loại tài khoản (`userRole`) khác loại mình đã chọn.
