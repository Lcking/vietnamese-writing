# Vietnamese Writing Skill

**Giúp AI viết tiếng Việt tự nhiên như người Việt bản địa — đặc biệt cho bình luận bóng đá.**

**让 AI 写出地道越南语 —— 尤其擅长足球解说与体育新闻。**

**Helps AI write natural, native-sounding Vietnamese — with a focus on football commentary.**

语言 / Ngôn ngữ / Language: [Tiếng Việt](#vietnamese) · [中文](#中文) · [English](#english)

---

<a name="vietnamese"></a>
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
# 2) Trích xuất thật (~10GB) — cần CẢ --yes VÀ export VIET_REBUILD_OK=1
export VIET_REBUILD_OK=1
python bin/extract_corpus.py --raw /path/to/.../raw --out ./viet_football --yes
# 3) Chọn bài mẫu vào examples/
python bin/extract_corpus.py --pick ./viet_football/football_corpus.jsonl --examples ./examples/football
```

Ai chạy, người đó tốn dung lượng (ngữ liệu lưu trên máy **của bạn**, không ảnh
hưởng repo hay người khác). Không có `--yes` **hoặc** không có `VIET_REBUILD_OK=1`
thì chỉ thống kê, không ghi gì.

## Ghi công

Kiến thức (`references/`) và ví dụ (`examples/`) được trích xuất từ bộ dữ liệu
**WanJuan-Vietnamese** của Shanghai Artificial Intelligence Laboratory (OpenDataLab),
giấy phép **CC BY 4.0**.

## Giấy phép

Mã nguồn: MIT. Nội dung kiến thức trích từ WanJuan: CC BY 4.0.
Xem [LICENSE](LICENSE).

---

<a name="中文"></a>
## 中文

一个让任意大语言模型(LLM)写出**地道、自然、符合越南人读写习惯**越南语的 skill —— **尤其擅长足球解说与体育新闻**。

做法是把从 303GB 原生越南语语料(**WanJuan-Vietnamese**)中提炼出的越南语写作规范,"注入"到任意 OpenAI 兼容端点的 LLM 提示中 —— **无需训练、无需 GPU**。

### 特点

- ⚽ **以足球为核心**:术语表、解说风格、比赛新闻稿、转会新闻、国家队报道、球员/教练人物
- ✅ 适配**任意 LLM**(GPT / Gemini / Kimi / Claude / 本地 Qwen…… 只要 OpenAI 兼容)
- ✅ 13 个写作 genre(7 通用 + 6 足球)+ 6 组通用规范
- ✅ 160 篇真实越南语足球文章作 few-shot 范例
- ✅ 知识源自 **303GB 越南语语料**(WanJuan-Vietnamese,CC BY 4.0)
- ✅ 轻量(约 750KB),易安装、易集成 —— 只是提示词 + Python 脚本

### 安装

```bash
git clone https://github.com/Lcking/vietnamese-writing.git
cd vietnamese-writing
# 无需第三方库(仅用 Python 3.8+ 标准库)。
# 可选:pip install pyyaml   # 若想用 config.yaml
```

### 配置

skill 需要一个 LLM 端点。设置环境变量:

```bash
export VIET_LLM_BASE_URL="https://api.openai.com/v1"
export VIET_LLM_API_KEY="sk-..."
export VIET_LLM_MODEL="gpt-4o"
```

或使用配置文件:`cp config.example.yaml config.yaml`

| 供应商 | BASE_URL | MODEL |
|--------------|----------|-------|
| OpenAI | `https://api.openai.com/v1` | `gpt-4o` |
| Google Gemini | `https://generativelanguage.googleapis.com/v1beta/openai` | `gemini-2.5-pro` |
| Moonshot Kimi | `https://api.moonshot.cn/v1` | `kimi-k2-0905-preview` |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| 本地 Qwen (vLLM) | `http://localhost:8005/v1` | `qwen-3.8-27b-awq` |

> 提示:若使用带思考链的模型(如本地 Qwen3),建议开启 `disable_thinking` 选项,速度可提升数倍且质量不降。

### 使用

```bash
# ⚽ 足球解说(自动识别足球主题)
python bin/viet_writer.py --task "Bình luận trận Việt Nam - Thái Lan ở AFF Cup"

# ⚽ 足球新闻稿
python bin/viet_writer.py --genre football_tin_tuc \
  --task "Viết bản tin MU thắng 3-1, Rashford lập cú đúp"

# ⚽ 转会新闻
python bin/viet_writer.py --genre football_chuyen_nhuong \
  --task "Viết tin Real Madrid chiêu mộ tiền đạo mới"

# 通用文体
python bin/viet_writer.py --task "Viết bài giới thiệu về ẩm thực Huế" --genre doi_song

# 交互模式
python bin/viet_writer.py --interactive
```

### 支持的 genre

**足球 / 体育(核心):**
`football_thuat_ngu`(术语)、`football_binh_luan`(解说/直播)、`football_tin_tuc`(新闻稿)、`football_chuyen_nhuong`(转会)、`football_doi_tuyen`(国家队)、`football_nhan_vat`(球员/教练人物)

**通用文体:**
`van_hoc`(文学)、`bao_chi`(新闻)、`bach_khoa`(百科)、`cong_van`(公文)、`mang_xa_hoi`(网络口语)、`doi_song`(生活)、`chuyen_mon`(专业)

### 集成到其他系统

本 skill 可被任意 agent 框架(OpenClaw、Pi Harness、Hermes……)通过 `SKILL.md`(含 `name` / `description` frontmatter 供框架路由)调用,也可作为 Python 库通过 `src/llm_client.py` 调用。

```python
import sys; sys.path.insert(0, "src")
from llm_client import LLMClient
client = LLMClient({"base_url": "https://api.openai.com/v1",
                    "api_key": "sk-...", "model": "gpt-4o"})
print(client.chat(system_prompt, user_task))
```

### 语料(可选)

skill **不需要**原始语料即可运行 —— 它只读 repo 内已有的 `references/` 和 `examples/`(约 750KB)。你**无需**下载 303GB 语料。

只有当你想**重新提炼 / 扩展到其他领域**时,才需要手动运行 `bin/extract_corpus.py`(**clone 后不会自动运行**):

```bash
# 前提:自行下载 WanJuan-Vietnamese raw(~303GB,CC BY 4.0)到本机。
# 1) 预览(dry-run,不写任何文件)
python bin/extract_corpus.py --raw /path/to/WanJuan-Vietnamese/raw
# 2) 真提取(~10GB)—— 需要同时满足 --yes 与 export VIET_REBUILD_OK=1
export VIET_REBUILD_OK=1
python bin/extract_corpus.py --raw /path/to/.../raw --out ./viet_football --yes
# 3) 精选范文进 examples/
python bin/extract_corpus.py --pick ./viet_football/football_corpus.jsonl --examples ./examples/football
```

谁运行谁占用磁盘(语料存在**你自己**的机器上,不影响 repo 或他人)。不加 `--yes` **或**不设 `VIET_REBUILD_OK=1`,则只做统计、不写任何内容。

### 致谢

知识(`references/`)与范例(`examples/`)提炼自 **WanJuan-Vietnamese** 数据集(上海人工智能实验室 / OpenDataLab),许可 **CC BY 4.0**。

### 许可

代码:MIT。知识内容提炼自 WanJuan:CC BY 4.0。详见 [LICENSE](LICENSE)。

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
your own machine. Dry-run by default; writing requires **both** `--yes` **and**
`VIET_REBUILD_OK=1` in the environment.
