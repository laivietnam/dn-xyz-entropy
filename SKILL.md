---
name: dn-xyz-entropy
description: >
  Delta-neutral ăn chênh funding giữa trade.xyz (dex `xyz`) và Entropy (dex `io`)
  trên Hyperliquid: mua một sàn, bán sàn kia cùng mã (NBIS, SNDK, DRAM, EWY…),
  cùng khối lượng. Dùng khi hỏi cặp nào có lợi thế funding, chấm một cặp trước khi
  vào (thanh khoản Entropy, funding 30 ngày, rút được ký quỹ, khoảng cách thanh lý),
  backtest funding, chi phí vào/ra lệnh, đọc vị thế DN hay lãi/lỗ thật của một ví,
  hoặc khi muốn tự xây bot mở/đóng/canh ký quỹ. Chỉ đọc API, không đặt lệnh.
---

# DN funding trade.xyz × Entropy

Bạn đang giúp người dùng **tự đo và tự quyết**. Đây không phải bot đặt lệnh và
không phải tín hiệu mua bán.

- `references/huong-dan.md` — giải thích chiến lược, rủi ro, chi phí cho người đọc.
- `references/kien-truc-bot.md` — thiết kế bot mở/đóng/canh đã chạy thật + các bẫy.
  Chỉ đọc khi người dùng muốn tự xây bot hoặc hỏi "bot làm sao để không bị thanh lý".
- `scripts/dn.py` — 5 lệnh chỉ đọc (bên dưới). Chỉ thư viện chuẩn Python.

## Cấm

- Không xin, không nhận, không lưu private key / API key. Không gọi `/exchange`.
  Chỉ đọc `https://api.hyperliquid.xyz/info`.
- Không viết hộ code gửi lệnh thật. Người dùng muốn tự xây bot thì đưa thiết kế
  trong `kien-truc-bot.md`, nhắc họ chạy thử bằng tài khoản giả trước, và tự chịu.
- Không nói "nên vào NBIS 5x". Số trong skill là **số đo**, không phải lệnh.
- Không hứa lợi nhuận. Funding quá khứ không hứa hẹn gì cho tương lai.
- NBIS, NVDA, EWY… là **hợp đồng mô phỏng giá cổ phiếu**, do bên triển khai sàn con
  vận hành. Nhắc người dùng tự tìm hiểu quy định nơi họ sống và tự kê khai thuế.

## Chiến lược trong 5 dòng

1. Cùng một mã niêm yết ở 2 sàn con của Hyperliquid, funding mỗi bên một khác.
2. Mua bên funding thấp, bán bên funding cao, cùng khối lượng → giá chạy đâu hai chân bù nhau.
3. Lợi nhuận = chênh funding − phí vào/ra − chênh giá 2 sàn lúc vào/ra.
4. Funding ròng mỗi giờ = rate(chân bán) − rate(chân mua). Dương = mình nhận.
5. Rủi ro chính: chỉ có **Isolated Margin** (chân lời không tự cứu chân lỗ) và
   **sổ lệnh Entropy mỏng** (vào/ra chậm).

## Quy trình khi được hỏi về một cặp

```bash
python3 scripts/dn.py ma-chung                         # mã có ở cả 2 sàn, đòn bẩy tối đa, loại ký quỹ
python3 scripts/dn.py funding NBIS --long xyz --short io --days 30 --size 10000
python3 scripts/dn.py cham NBIS --long xyz --short io --lev 3 --margin 1000
```

Luôn chạy script để lấy số **lúc này**. Không dùng số trong tài liệu làm số hiện tại.

Thử **cả hai chiều** (`--long io --short xyz`) — chiều có lợi khác nhau theo từng mã.

### 4 tiêu chí của lệnh `cham`

| Tiêu chí | Đạt khi | Vì sao |
|---|---|---|
| Thanh khoản Entropy | ước tính chờ khớp ≤ 30 phút | Entropy là chân chậm; vào/ra quá lâu là hở rủi ro |
| Funding 30 ngày | tổng dương **và** có ≥ 28 ngày dữ liệu | mã mới lên vài ngày thì chưa nói được gì |
| Rút được ký quỹ | không chân nào `strictIsolated` | phải rút lời chân thắng nạp chân thua được |
| Giá thanh lý | chân yếu nhất cách thanh lý xa hơn dao động ngày lớn nhất 30 ngày | một ngày xấu không được đủ để mất 1 chân |

Trượt tiêu chí không có nghĩa là cấm vào. Nói rõ cái giá phải trả, người dùng tự quyết.

Chờ khớp ước tính = giá trị 1 chân ÷ (khối lượng $ trung bình 7 ngày ÷ 1440 ÷ 2).
Đây là ước tính thô; đo bằng **khối lượng $**, không đếm số lần khớp (Entropy hay có
nhiều lần khớp $13 trông đông mà tổng ít).

## Đọc ví người dùng (chỉ cần địa chỉ công khai)

```bash
python3 scripts/dn.py vi-the --user 0x...
python3 scripts/dn.py pnl --user 0x... --since 2026-10-29
```

- `vi-the`: 2 chân, ký quỹ còn bao nhiêu % so với lúc mở, cách thanh lý, số TP/SL trên
  sàn, phần lời chân thắng rút được. Cảnh báo khi chỉ có 1 chân, 2 chân lệch, không có TP/SL.
- `pnl`: tách từng vòng DN từ lịch sử khớp thật (mở khi cả 2 chân từ 0, đóng khi cả 2 về 0)
  + funding thật − phí thật. Phần đang mở tính theo **giá giữa sổ lệnh**, không theo mark.
- Sai địa chỉ thì API trả rỗng, trông như "không có vị thế". Luôn đọc lại địa chỉ in ra.
- Ví dùng chung với bot/giao dịch tay khác cùng mã → các lệnh đó bị gộp vào vòng. Nói rõ.

## Số đã kiểm thật (29–31/10/2026, có thể đã đổi — kiểm lại khi cần)

- Lệnh dưới **$10** (tính theo giá đặt) bị sàn từ chối.
- `marginUsed` trong `clearinghouseState` **đã gồm** lãi/lỗ chưa chốt.
- Rút ký quỹ lệnh riêng quá mức → sàn từ chối "insufficient margin for reduction".
  Mức rút được theo tài liệu: phần trên max(ký quỹ ban đầu, 10% giá trị vị thế).
  **Chưa kiểm** ở đòn bẩy > 5x (10% có thể tính trên mọi vị thế, khi đó gần như không rút được).
- Tài khoản chế độ `unifiedAccount`: USDC nằm ở spot làm ký quỹ chung mọi sàn con →
  `withdrawable` từng sàn con báo 0 là bình thường; tiền rảnh = spot USDC total − hold.
  Không cần chuyển tiền giữa sàn con khi cân ký quỹ.
- Phí NBIS trên UI (mức cơ bản, Growth mode): Taker 0,90 bps / Maker 0,30 bps.
  Mã không bật Growth mode: script ước tính gấp 10 lần — **chưa kiểm trên UI**.
  Phí thật của mỗi người khác nhau (ref, stake, hạng) → dùng `--taker` / `--maker`.
- Hạn mức hỏi API: 1200 điểm/phút/IP. `clearinghouseState`, `l2Book` = 2 điểm;
  `frontendOpenOrders`, `userFills`, `userFunding` = 20; `userRole` = 60.
  Lỗi 429 = hỏi quá dày; 502/504 = máy chủ Hyperliquid không trả lời (bảo trì), tự hết.
- Con số APY trên các trang tổng hợp funding (vd Loris) là funding **của giờ hiện tại**.
  Luôn kiểm lịch sử bằng `funding` trước khi tin.

## Công thức

- Giá chạy ngược bao nhiêu thì bị thanh lý (ký quỹ riêng):
  `l = 1/(2 × đòn bẩy tối đa)`, `a = 1/đòn bẩy − l`, chân mua `a/(1−l)`, chân bán `a/(1+l)`.
- Chi phí cả vòng (cách khuyến nghị: Maker Entropy + Taker trade.xyz theo phần $500):
  `giá trị × (2×maker + 2×taker) + trượt giá khớp $500 hai phía trên trade.xyz`.
- Lãi trên vốn theo năm = funding %/năm trên giá trị × đòn bẩy ÷ 2
  (vốn là ký quỹ của **cả hai** chân). Đòn bẩy cao thì lãi trên vốn cao,
  và khoảng cách tới thanh lý ngắn lại — nói cả hai vế.

## Khi giải thích cho người dùng

Câu ngắn, số bằng số, nói cả cái giá phải trả. Gợi ý 3 cách vào lệnh và đánh đổi
(chi tiết trong `huong-dan.md` mục 4). Không dùng chữ "chắc chắn", "an toàn tuyệt đối".
