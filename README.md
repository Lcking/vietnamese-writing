# Vietnamese Writing Skill

**Giúp AI viết tiếng Việt tự nhiên như người Việt bản địa — đặc biệt cho bình luận bóng đá.**

[English below](#english)

---

## Giới thiệu

Đây là một skill (gói năng lực) giúp bất kỳ AI/LLM nào viết tiếng Việt chuẩn phong cách,
tự nhiên, phù hợp với thói quen đọc và viết của người Việt Nam.

Nó hoạt động bằng cách "tiêm" (inject) các hướng dẫn viết tiếng Việt được trích xuất
từ kho ngữ liệu tiếng Việt bản địa quy mô lớn (**WanJuan-Vietnamese, 303GB**) vào quá
trình sinh văn bản của LLM — **không cần huấn luyện, không cần GPU mạnh.**

## Đặc điểm

- ⚽ **Trọng tâm bóng đá**: thuật ngữ, phong cách bình luận, bản tin, chuyển nhượng, tuyển Việt Nam
- ✅ Hoạt động với **mọi LLM** có API tương thích OpenAI (GPT / Gemini / Kimi / Claude / Qwen local...)
- ✅ 13 thể loại viết (7 đa thể loại + 6 chuyên bóng đá) + 6 nhóm quy tắc dùng chung
- ✅ 160 bài báo bóng đá thật làm ví dụ mẫu (few-shot)
- ✅ Kiến thức nền trích xuất từ **303GB ngữ liệu tiếng Việt** (WanJuan-Vietnamese, CC BY 4.0)
- ✅ Nhẹ (~750KB), dễ cài, dễ tích hợp — chỉ là prompt + script Python

## Cài đặt

```bash
git clone https://github.com/Lcking/vietnamese-writing.git
cd vietnamese-writing
# Không cần thư viện ngoài (chỉ dùng thư viện chuẩn Python 3.8+).
# Tùy chọn: pip install pyyaml   # nếu muốn đọc config.yaml
```

## Cấu hình

Skill cần một LLM endpoint. Đặt biến môi trường:

```bash
export VIET_LLM_BASE_URL="https://api.openai.com/v1"
export VIET_LLM_API_KEY="sk-..."
export VIET_LLM_MODEL="gpt-4o"
```

Hoặc dùng file config: `cp config.example.yaml config.yaml`

| Nhà cung cấp | BASE_URL | MODEL |
|--------------|----------|-------|
| OpenAI | `https://api.openai.com/v1` | `gpt-4o` |
| Google Gemini | `https://generativelanguage.googleapis.com/v1beta/openai` | `gemini-2.5-pro` |
| Moonshot Kimi | `https://api.moonshot.cn/v1` | `kimi-k2-0905-preview` |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| Qwen local (vLLM) | `http://localhost:8005/v1` | `qwen-3.8-27b-awq` |

## Sử dụng

```bash
# ⚽ Bình luận bóng đá (tự động nhận diện chủ đề bóng đá)
python bin/viet_writer.py --task "Bình luận trận Việt Nam - Thái Lan ở AFF Cup"

# ⚽ Bản tin bóng đá
python bin/viet_writer.py --genre football_tin_tuc \
  --task "Viết bản tin MU thắng 3-1, Rashford lập cú đúp"

# ⚽ Tin chuyển nhượng
python bin/viet_writer.py --genre football_chuyen_nhuong \
  --task "Viết tin Real Madrid chiêu mộ tiền đạo mới"

# Đa thể loại
python bin/viet_writer.py --task "Viết bài giới thiệu về ẩm thực Huế" --genre doi_song

# Chế độ tương tác
python bin/viet_writer.py --interactive
```

## Thể loại hỗ trợ (genre)

**Bóng đá / thể thao (trọng tâm):**
`football_thuat_ngu` (thuật ngữ), `football_binh_luan` (bình luận/tường thuật),
`football_tin_tuc` (bản tin), `football_chuyen_nhuong` (chuyển nhượng),
`football_doi_tuyen` (tuyển quốc gia), `football_nhan_vat` (chân dung cầu thủ/HLV)

**Đa thể loại:**
`van_hoc`, `bao_chi`, `bach_khoa`, `cong_van`, `mang_xa_hoi`, `doi_song`, `chuyen_mon`

## Tích hợp vào hệ thống khác

Skill này có thể được gọi từ bất kỳ agent framework nào (OpenClaw, Pi harness, Hermes...)
thông qua file `SKILL.md` (chứa frontmatter `name` / `description` để framework định tuyến),
hoặc như một thư viện Python qua `src/llm_client.py`.

**Cách gọi như thư viện:**
```python
import sys; sys.path.insert(0, "src")
from llm_client import LLMClient
client = LLMClient({"base_url": "https://api.openai.com/v1",
                    "api_key": "sk-...", "model": "gpt-4o"})
print(client.chat(system_prompt, user_task))
```

## Ngữ liệu (không bắt buộc)

Skill **không cần** ngữ liệu gốc để hoạt động. Khi gọi, nó chỉ đọc `references/`
và `examples/` (đã có sẵn trong repo, ~750KB). Bạn **không cần** tải 303GB ngữ liệu.

Chỉ khi bạn muốn **trích xuất lại / mở rộng** sang lĩnh vực khác, mới cần chạy
`bin/extract_corpus.py` **thủ công** (script này **không tự chạy** khi clone):

```bash
# Điều kiện: tự tải WanJuan-Vietnamese raw (~303GB, CC BY 4.0) về máy bạn.
# 1) Xem trước (dry-run, KHÔNG ghi file)
python bin/extract_corpus.py --raw /path/to/WanJuan-Vietnamese/raw
# 2) Trích xuất thật (~10GB, chỉ chạy khi bạn thêm --yes)
python bin/extract_corpus.py --raw /path/to/.../raw --out ./viet_football --yes
# 3) Chọn bài mẫu vào examples/
python bin/extract_corpus.py --pick ./viet_football/football_corpus.jsonl --examples ./examples/football
```

Ai chạy, người đó tốn dung lượng (ngữ liệu lưu trên máy **của bạn**, không ảnh
hưởng repo hay người khác). Không thêm `--yes` thì chỉ thống kê, không ghi gì.

## Ghi công

Kiến thức (`references/`) và ví dụ (`examples/`) được trích xuất từ bộ dữ liệu
**WanJuan-Vietnamese** của Shanghai Artificial Intelligence Laboratory (OpenDataLab),
giấy phép **CC BY 4.0**.

## Giấy phép

Mã nguồn: MIT. Nội dung kiến thức trích từ WanJuan: CC BY 4.0.
Xem [LICENSE](LICENSE).

---

<a name="english"></a>
## English

A skill that helps any LLM write natural, native-sounding Vietnamese — with a
focus on **football commentary and sports journalism**.

It injects Vietnamese writing norms — extracted from 300GB of native Vietnamese
corpora (WanJuan-Vietnamese) — into any OpenAI-compatible LLM. No training, no
GPU required.

**Coverage:** 6 football genres (terminology, live commentary, match reports,
transfer news, national team, player/coach profiles), 7 general genres
(literature, news, encyclopedia, administrative, social media, lifestyle,
technical), 6 shared norm sets (pronoun systems, North/South differences,
Sino-Vietnamese usage, cultural markers, common errors, connectives), and
160 real Vietnamese football articles as few-shot examples.

**Quick start:**
```bash
export VIET_LLM_BASE_URL="https://api.openai.com/v1"
export VIET_LLM_API_KEY="sk-..."
export VIET_LLM_MODEL="gpt-4o"
python bin/viet_writer.py --task "Bình luận trận Việt Nam - Thái Lan"
```

**Attribution:** Knowledge and examples extracted from the WanJuan-Vietnamese
dataset (Shanghai AI Laboratory / OpenDataLab), CC BY 4.0.

**Corpus (optional):** The skill does **not** need the raw corpus to run — it
only reads `references/` and `examples/` shipped in the repo. Rebuilding the
football corpus from WanJuan is a **manual, optional** step
(`bin/extract_corpus.py`; never runs automatically on clone). It requires you to
obtain the ~303GB WanJuan raw data yourself, and the extracted ~10GB is stored on
your own machine. Dry-run by default; add `--yes` to actually write.
