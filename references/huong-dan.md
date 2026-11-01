# Hướng dẫn cho anh em: DN funding trade.xyz × Entropy

Đọc hết trước khi bỏ tiền. Đây là chia sẻ những gì mình đã đo và chạy thật,
không phải tín hiệu mua bán, không phải lời khuyên đầu tư.

---

## 1. Chiến lược là gì

Trên Hyperliquid có nhiều sàn con (HIP-3). Hai sàn con **trade.xyz** và **Entropy**
cùng niêm yết một số mã, ví dụ NBIS (cổ phiếu Nebius).

Cùng một mã, nhưng funding hai bên khác nhau.

Cách làm: mua bên funding thấp, bán bên funding cao, khối lượng bằng nhau.

- Giá lên: chân mua lãi, chân bán lỗ. Giá xuống: ngược lại. Hai chân bù nhau.
- Lợi nhuận tới từ **chênh lệch funding** giữa hai sàn.

Ví dụ đã đo: NBIS mua trade.xyz / bán Entropy, 28/08 → 30/10/2026, funding ròng
khoảng **+$245 trên mỗi $10.000/chân** (~14%/năm trên giá trị). Riêng tháng 10
chậm lại còn ~10%/năm. Lợi thế có thật, nhưng **mỏng dần** — tự chạy lại số mới nhất.

## 2. Tự đo bằng script

```bash
python3 scripts/dn.py ma-chung
python3 scripts/dn.py funding NBIS --long xyz --short io --days 30 --size 10000
python3 scripts/dn.py cham NBIS --long xyz --short io --lev 3 --margin 1000
```

`--margin` là ký quỹ **mỗi chân**. Vốn bỏ ra = 2 × margin.

## 3. Hai rủi ro phải hiểu

### Rủi ro 1: chỉ có Isolated Margin

Các mã này chỉ cho **Isolated Margin**: mỗi chân một khoản ký quỹ riêng.

Tiền lời của chân thắng **không tự chạy sang** cứu chân thua.

Giá chạy một chiều đủ xa → chân thua bị thanh lý → chân còn lại thành vị thế trần,
không còn phòng hộ.

| Đòn bẩy | Vốn cho $10.000/chân | Lãi/năm trên vốn (ở ~14%/năm) | Chân thua bị thanh lý khi giá chạy |
|---|---|---|---|
| 2x | $10.000 | ~14% | ~43–47% |
| 3x | $6.667 | ~21% | ~27–30% |
| 5x | $4.000 | ~36% | ~14–16% |
| 10x | $2.000 | ~71% | ~5% |

NBIS 28/08 → 30/10/2026: dao động trong ngày trung bình ~7%, lớn nhất ~19%;
3 ngày chạy xa nhất ~22%. Nghĩa là ở 10x, một ngày bình thường đã đủ thanh lý.

**Cột cuối mới là cột quan trọng nhất.**

Không mở rồi để đó. Phải canh, và khi chân thua mỏng đi thì:
rút **tiền lời** chân thắng → nạp sang chân thua (trên app: Positions → Margin).

### Rủi ro 2: sổ lệnh Entropy rất mỏng

Khối lượng NBIS (đo 30 ngày tới 30/10/2026): trade.xyz ~$20 triệu/ngày,
Entropy ~$4 triệu/ngày, có ngày chỉ $0,8 triệu.

Có sáng cả 20 mức giá phía mua trên Entropy cộng lại chỉ ~$5.5k.

- Bên Entropy phải đặt lệnh chờ rồi đợi khớp. $10.000 mất ~6–12 phút, có lúc lâu hơn.
- Lúc cần thoát gấp, Entropy là chân chậm nhất.
- Size càng lớn càng khó.

Thêm một chi phí ẩn: **giá hai sàn không bằng nhau**. Thường lệch vài bps,
có lúc tới vài chục bps. Lệch 20 bps trên $10.000 là $20 — bằng cả tuần funding.

## 4. Ba cách vào lệnh ($10.000/chân, đo 29–30/10/2026)

| Cách | Chi phí cả vòng (mở + đóng) | Thời gian khớp |
|---|---|---|
| 1. Taker cả 2 chân | ~$24; có lúc sổ Entropy không đủ để Taker $10.000 | vài giây |
| 2. Maker cả 2 chân | ~$1 phí | ~6–12 phút, hai chân khớp lệch giờ nhau |
| 3. Maker Entropy, Taker trade.xyz theo phần $500 | ~$4 | ~6–12 phút, chờ phía Entropy |

- **Cách 1** nhanh nhất, đắt nhất, size lớn gần như không vào được.
- **Cách 2** rẻ nhất, nhưng hai lệnh chờ không khớp cùng lúc. Trong lúc chờ có
  $10.000 nằm một chiều. Giá NBIS chạy trong 15 phút: một nửa số lần dưới $16/$10k,
  nhưng 1/10 số lần trên $68, có lần $640.
- **Cách 3** cân bằng: chờ bên Entropy (chân khó khớp), khớp được tới đâu thì
  Taker bên trade.xyz tới đó theo phần $500. Phần chưa cân không bao giờ quá $500.
  Đây là cách bot của mình đã dùng.

## 5. Checklist trước khi vào

- [ ] Chạy `funding` cả 2 chiều, chiều đã chọn dương **và** có đủ 30 ngày dữ liệu.
- [ ] Chạy `cham`: đọc kỹ cột "bị thanh lý khi giá chạy" so với dao động ngày.
- [ ] Không chân nào `strictIsolated` (không rút/nạp ký quỹ được → loại).
- [ ] Đã tính chi phí cả vòng + chênh giá 2 sàn: cần bao nhiêu ngày funding để hoà?
- [ ] Biết mình sẽ canh bằng gì (bot riêng, cảnh báo giá, hay mở app mỗi ngày).
- [ ] Đặt TP/SL dự phòng cho cả 2 chân, cùng mức giá, trước giá thanh lý —
      lớp cứu khi mình không kịp phản ứng.
- [ ] Ví giao dịch không có lệnh tay khác cùng mã (làm `pnl` tính sai, dễ nhầm chân).

## 6. Theo dõi

```bash
python3 scripts/dn.py vi-the --user 0xĐỊA_CHỈ_VÍ
python3 scripts/dn.py pnl --user 0xĐỊA_CHỈ_VÍ --since 2026-11-01
```

Chỉ cần địa chỉ ví công khai. **Không bao giờ** đưa private key cho AI hay cho ai.

Lãi/lỗ trên app tính theo giá mark — khác giá khớp thật khi đóng.
`pnl` tính theo giá khớp thật + funding thật − phí thật.

## 7. Thuế và pháp lý

- NBIS, NVDA, EWY… là hợp đồng mô phỏng giá cổ phiếu, do bên triển khai sàn con
  vận hành, có rủi ro riêng của từng nền tảng (dừng mã, đổi luật, sự cố oracle).
- Lãi từ funding và chênh giá là thu nhập — tự tìm hiểu và kê khai theo quy định
  nơi anh em sống.
- Đây là đòn bẩy. Không phải gửi tiết kiệm.
