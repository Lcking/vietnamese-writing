---
name: vietnamese-writing
description: Use when writing Vietnamese text that must read naturally to native Vietnamese speakers - football commentary, news, formal docs, literature, social posts. Injects Vietnamese writing norms (pronouns, North/South, Sino-Vietnamese, genre conventions) extracted from 300GB native corpus.
---

# Vietnamese Writing (越南语写作)

Bộ công cụ giúp AI viết tiếng Việt tự nhiên, chuẩn phong cách, phù hợp với người đọc Việt Nam.
Kiến thức được trích xuất từ kho ngữ liệu bản ngữ **WanJuan-Vietnamese** (303GB).

## Khi nào dùng

Dùng skill này khi cần viết bất kỳ văn bản tiếng Việt nào đọc "tự nhiên như người Việt viết", đặc biệt:

- **Bình luận / tường thuật bóng đá** (足球解说/评论) — xem `football_*`
- Tin tức, bài báo
- Công văn, văn bản hành chính, chính sách
- Văn học, kể chuyện
- Nội dung mạng xã hội, quảng cáo, marketing
- Tài liệu chuyên môn, kỹ thuật

## Cách dùng

### 1. Cấu hình LLM (bắt buộc)

Skill hoạt động với **bất kỳ LLM nào có API tương thích OpenAI** (GPT, Gemini, Kimi, Claude, DeepSeek, hoặc model local như Qwen).

Cách 1 - biến môi trường:
```bash
export VIET_LLM_BASE_URL="https://api.openai.com/v1"
export VIET_LLM_API_KEY="sk-..."
export VIET_LLM_MODEL="gpt-4o"
```

Cách 2 - file config:
```bash
cp config.example.yaml config.yaml   # rồi sửa
python bin/viet_writer.py -c config.yaml --task "viết bài ..."
```

### 2. Viết văn bản

```bash
# Bình luận bóng đá
python bin/viet_writer.py --genre football_binh_luan \
  --task "Viết bình luận trận Việt Nam - Thái Lan ở AFF Cup"

# Bản tin bóng đá
python bin/viet_writer.py --genre football_tin_tuc \
  --task "Viết bản tin MU thắng 3-1, Rashford lập cú đúp"

# Văn bản hành chính
python bin/viet_writer.py --genre cong_van \
  --task "Viết công văn xin lỗi khách hàng vì giao hàng trễ"

# Chế độ tương tác
python bin/viet_writer.py --interactive
```

### 3. Dùng như thư viện Python

```python
import sys; sys.path.insert(0, "src")
from llm_client import LLMClient

client = LLMClient({"base_url": "http://localhost:8005/v1",
                    "api_key": "local", "model": "qwen-3.8-27b-awq"})
print(client.chat("Bạn là bình luận viên bóng đá Việt Nam.",
                  "Bình luận 3 câu về một bàn thắng phút 90."))
```

## Các thể loại được hỗ trợ (genre)

### Bóng đá / thể thao (trọng tâm)
| genre | Thể loại |
|-------|----------|
| `football_thuat_ngu` | Thuật ngữ bóng đá (术语表) |
| `football_binh_luan` | Phong cách bình luận / tường thuật (解说) |
| `football_tin_tuc` | Bản tin bóng đá (新闻稿) |
| `football_chuyen_nhuong` | Tin chuyển nhượng (转会) |
| `football_doi_tuyen` | Tuyển quốc gia Việt Nam (国家队) |
| `football_nhan_vat` | Chân dung cầu thủ / HLV (人物) |

### Đa thể loại
| genre | Thể loại |
|-------|----------|
| `van_hoc` | Văn học / sách |
| `bao_chi` | Tin tức báo chí |
| `bach_khoa` | Bách khoa |
| `cong_van` | Văn bản hành chính / chính sách |
| `mang_xa_hoi` | Ngôn ngữ mạng / văn bản ngắn |
| `doi_song` | Đời sống / phong cách mềm |
| `chuyen_mon` | Chuyên môn / kỹ thuật |

## Kiến thức nền (references/)

Quy tắc viết được trích xuất từ kho ngữ liệu **WanJuan-Vietnamese** (CC BY 4.0):

**Bóng đá:**
- `football_thuat_ngu.md` — thuật ngữ: vị trí, hành động, luật, chiến thuật
- `football_binh_luan.md` — phong cách bình luận, ngôn từ cao trào, nhịp câu
- `football_tin_tuc.md` — cấu trúc bản tin, cách viết tiêu đề có tỷ số
- `football_chuyen_nhuong.md` — từ vựng và cấu trúc tin chuyển nhượng
- `football_doi_tuyen.md` — cách truyền thông đưa tin về tuyển Việt Nam
- `football_nhan_vat.md` — viết chân dung cầu thủ / huấn luyện viên

**Theo thể loại:** `van_hoc.md`, `bao_chi.md`, `bach_khoa.md`, `cong_van.md`, `mang_xa_hoi.md`, `doi_song.md`, `chuyen_mon.md`

**Dùng chung (global):**
- `_global_xung_ho.md` — hệ thống xưng hô
- `_global_bac_nam.md` — khác biệt Bắc / Nam
- `_global_han_viet.md` — cách dùng từ Hán-Việt
- `_global_van_hoa.md` — yếu tố văn hóa bản địa
- `_global_loi_thuong_gap.md` — lỗi thường gặp
- `_global_gioi_tu_tro.md` — giới từ, trợ từ, từ nối

## Ví dụ mẫu (examples/)

`examples/football/*.jsonl` — 160 bài báo bóng đá thật, 8 chủ đề (tuyển VN, World Cup,
ngoại hạng Anh, Champions League, chuyển nhượng, V-League, châu Á, phân tích chiến thuật).
Dùng làm few-shot khi cần giọng văn cụ thể.

## Cấu trúc

```
vietnamese-writing/
├── SKILL.md
├── README.md
├── LICENSE
├── config.example.yaml
├── requirements.txt
├── bin/viet_writer.py            # CLI entry
├── src/llm_client.py             # LLM adapter (OpenAI-compatible)
├── prompts/system_vi_writer.md   # core system prompt
├── references/*.md               # writing norms by genre (incl. football)
└── examples/football/*.jsonl     # real Vietnamese football articles
```

## Ghi công (Attribution)

Kiến thức và ví dụ trong `references/` và `examples/` được trích xuất từ bộ dữ liệu
**WanJuan-Vietnamese** (Shanghai Artificial Intelligence Laboratory / OpenDataLab),
giấy phép **CC BY 4.0**. Xem `LICENSE` để biết chi tiết.
