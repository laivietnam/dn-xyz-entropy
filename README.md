# DN funding trade.xyz × Entropy — skill chia sẻ

Skill giúp anh em **tự đo** cơ hội delta-neutral ăn chênh funding giữa hai sàn con
**trade.xyz** và **Entropy** trên Hyperliquid (mua một sàn, bán sàn kia cùng mã,
cùng khối lượng), và **tự đọc** vị thế, lãi/lỗ thật của ví mình.

Repo: [github.com/laivietnam/dn-xyz-entropy](https://github.com/laivietnam/dn-xyz-entropy)

**Không phải tín hiệu mua bán. Không phải bot đặt lệnh. Không phải gửi tiết kiệm.**

Mình share những gì đã đo và chạy thật trên ví thật (29/10 → 01/11/2026):
cách chấm một cặp, chi phí vào/ra, rủi ro, thiết kế bot canh ký quỹ, các bẫy đã gặp.
Anh em tự chọn đòn bẩy, tự chịu rủi ro, tự kê khai thuế.

---

## Đọc trên GitHub trước khi clone

| File | Việc gì |
|---|---|
| `SKILL.md` | Hướng dẫn cho AI (Claude / Grok) |
| `references/huong-dan.md` | Hướng dẫn cho anh em — đọc trước khi bỏ tiền |
| `references/kien-truc-bot.md` | Thiết kế bot mở/đóng/canh đã chạy thật + bẫy (chỉ mô tả, không code gửi lệnh) |
| `scripts/dn.py` | 5 lệnh đọc số từ API |
| `LICENSE` | Không bảo hành, không phải tư vấn đầu tư |

Script `dn.py`:

- Chỉ thư viện chuẩn Python 3.9+ — không cài thêm gì.
- Chỉ gọi `https://api.hyperliquid.xyz/info` (đọc). **Không** gọi `/exchange`.
- **Không** xin, không lưu private key / API key. Đọc ví chỉ cần địa chỉ công khai.

Trên GitHub, bấm search trong repo: `exchange`, `private`, `key`, `.env` — không có
chỗ gửi lệnh hay lấy khóa.

---

## Cài vào Claude / Grok

Đã đọc file xong:

```bash
git clone https://github.com/laivietnam/dn-xyz-entropy.git ~/.claude/skills/dn-xyz-entropy
```

Không dùng Claude thì clone vào `~/.grok/skills/dn-xyz-entropy`.

Mở chat, hỏi kiểu: *"chấm cặp NBIS mua xyz bán io 3x margin 1000"*,
*"backtest funding SNDK 30 ngày cả 2 chiều"*, *"đọc vị thế DN của ví 0x…"*.

Cập nhật sau này:

```bash
cd ~/.claude/skills/dn-xyz-entropy && git pull
```

## Chạy thẳng không cần AI

```bash
cd ~/.claude/skills/dn-xyz-entropy
python3 scripts/dn.py ma-chung
python3 scripts/dn.py funding NBIS --long xyz --short io --days 30 --size 10000
python3 scripts/dn.py cham NBIS --long xyz --short io --lev 3 --margin 1000
python3 scripts/dn.py vi-the --user 0xĐỊA_CHỈ_VÍ
python3 scripts/dn.py pnl --user 0xĐỊA_CHỈ_VÍ --since 2026-11-01
```

Không đưa private key cho AI hay cho ai. Skill **cấm** đặt lệnh.
