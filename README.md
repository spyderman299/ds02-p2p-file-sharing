# DS02 – Hệ thống chia sẻ file P2P mô phỏng BitTorrent

File được chia thành các chunk 64 KB. Mỗi chunk có mã băm SHA-256 riêng và được tải song song từ nhiều peer. Peer nào đã có chunk thì phục vụ lại chunk đó cho peer khác ngay cả khi chưa tải xong. Tracker chỉ quản lý metadata và danh sách peer, **không bao giờ giữ hay gửi nội dung file**.

## Kiến trúc

```
                 +-----------------------------+
                 |  TRACKER (HTTP/JSON :8000)  |
                 |  metadata + danh sách peer  |
                 +--------------+--------------+
        register / announce /   |   leave (heartbeat 3s, timeout 10s)
     +-------------+------------+-------------+
     |             |                          |
+----+----+   +----+----+                +----+----+
| Peer A  |<->| Peer C  |<-------------->| Peer D  |
| (seed)  |   | tải + gửi|   GET /chunk   | tải + gửi|
+----+----+   +----+----+                +----+----+
     ^             ^                          ^
     +-------------+---------- Peer B (seed) -+
```

| Thành phần | File | Vai trò |
|---|---|---|
| Dùng chung | `src/common.py` | Tạo metadata, băm SHA-256, gọi HTTP/JSON, ghi log |
| Tracker | `src/tracker.py` | `POST /register`, `POST /announce`, `POST /leave`, `GET /meta/<id>`, `GET /peers/<id>`, `GET /files` |
| Peer | `src/peer.py` | Server `GET /chunk/<file_id>/<i>` (upload) và bộ tải song song (download) |

**Giao thức:** HTTP/1.1 trên TCP, dữ liệu điều khiển dạng JSON, nội dung chunk là dữ liệu nhị phân.

**Metadata** gồm `file_id`, `name`, `size`, `chunk_size`, `num_chunks`, `chunk_hashes[]`, `file_hash`, `tracker`.

## Yêu cầu môi trường

- Python 3.8 trở lên, **không cần cài thư viện ngoài**.
- (Tuỳ chọn) Docker và Docker Compose.

## Cấu hình khoá xác thực (bắt buộc, làm 1 lần)

Tracker và các peer xác thực lẫn nhau bằng khoá bí mật dùng chung `TRACKER_API_KEY`, gửi trong header `X-API-Key`. Khoá nằm trong file `.env`, file này **không được commit** (đã có trong `.gitignore`).

```bash
cp .env.example .env              # Windows PowerShell: Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_hex(16))"   # tạo khoá ngẫu nhiên, dán vào TRACKER_API_KEY trong .env
```

`scripts/demo.py`, `scripts/benchmark.py` và bộ test tự dùng khoá tạm nếu chưa có `.env`.

## Chạy nhanh toàn bộ demo (1 lệnh)

```bash
python scripts/demo.py
```

Lệnh này tự khởi động 1 tracker và 5 peer, chạy toàn bộ kịch bản bắt buộc rồi in kết quả. Log của từng node nằm trong `demo_data/logs/`.

## Trang theo dõi trực quan (dashboard)

```bash
python scripts/dashboard.py
```

Mở trình duyệt tại `http://127.0.0.1:8080`. Trang có 4 tab: Tổng quan, Luồng hoạt động, **Demo trực tiếp**, Bảo mật và kiểm thử. Ở tab Demo, bấm **Chạy demo** để chạy `scripts/demo.py` ở chế độ chậm; mỗi peer hiện thành một hàng 64 ô, ô sáng lên khi tải được mảnh và tô màu theo peer đã gửi mảnh đó. Bên cạnh là danh sách peer trong tracker và các sự kiện (mảnh hỏng, đổi nguồn, timeout...) được giải thích bằng tiếng Việt. Trang chỉ đọc log trong `demo_data/logs`, không thay đổi hệ thống.

## Chạy thủ công (mỗi lệnh một cửa sổ terminal, chạy trong thư mục `src/`)

```bash
python tracker.py --port 8000
python peer.py seed ../share/video.bin --id A --port 9001 --slow 0.15
python peer.py seed ../share/video.bin --id B --port 9002 --slow 0.15 --corrupt 0-31
python peer.py get <file_id> --id C --port 9003 --slow 0.15
python peer.py get <file_id> --id D --port 9004 --slow 0.15
```

`file_id` được in ra trong log của seeder. Tạo file mẫu bằng `python scripts/make_share.py`.

## Chạy trên nhiều máy thật (cùng mạng Wi-Fi hoặc hotspot)

Mọi máy phải có **cùng file `.env`** (cùng khoá). Xem IP của máy bằng `ipconfig` (Windows), ví dụ máy 1 là `192.168.1.10`, máy 2 là `192.168.1.20`. Lần đầu chạy, Windows hỏi tường lửa thì chọn **Allow access**.

```bash
# Máy 1 (tracker + seeder A), trong thư mục src/
python tracker.py --port 8000
python peer.py seed ../share/video.bin --id A --port 9001 --host 192.168.1.10 --tracker http://192.168.1.10:8000

# Máy 2 (peer C tải về), trong thư mục src/
python peer.py get <file_id> --id C --port 9003 --host 192.168.1.20 --tracker http://192.168.1.10:8000
```

`--host` là địa chỉ máy mình để các peer khác kết nối tới; `--tracker` là địa chỉ máy chạy tracker.

| Tham số | Ý nghĩa |
|---|---|
| `--workers` | Số kết nối tải đồng thời tối đa (mặc định 4) |
| `--upload-slots` | Số lượt upload đồng thời tối đa (giới hạn băng thông) |
| `--slow` | Độ trễ mỗi lần gửi chunk, giúp demo dễ quan sát |
| `--corrupt 0-3,7` | Giả lập peer gửi chunk hỏng |
| `--exit-when-done` | Tải xong thì thoát, không seed tiếp |

## Chạy bằng Docker (mỗi node một container)

```bash
export FILE_ID=$(python scripts/make_share.py)        # Windows PowerShell: $env:FILE_ID = python scripts/make_share.py
export TRACKER_API_KEY=<khoá trong .env>              # Windows PowerShell: $env:TRACKER_API_KEY = "<khoá>"
docker compose -f deploy/docker-compose.yml up --build
docker compose -f deploy/docker-compose.yml kill seeder-b   # tắt một nguồn giữa chừng
```

## Kịch bản demo bắt buộc

| # | Kịch bản | Cách thực hiện | Dấu hiệu trong log |
|---|---|---|---|
| 1 | Tạo metadata, chia sẻ file | `peer.py seed` | `SEED file ... file_id=`, tracker: `REGISTER` |
| 2 | Tải song song từ ≥ 2 peer | C và D cùng chạy `get` | `OK chunk i tu A` / `tu B` / `tu D` |
| 3 | Upload khi chưa tải xong | Xem log của C và D | `UPLOAD chunk i -> D (minh dang co 36/64)` |
| 4 | Tắt một nguồn khi đang tải | Ctrl+C hoặc kill peer B | `LOI tai chunk ... -> DOI NGUON` |
| 5 | Chuyển sang nguồn khác | Tự động | Chunk tiếp theo được tải từ A hoặc D |
| 6 | Phát hiện chunk hỏng | B chạy với `--corrupt` | `CHUNK KHONG HOP LE ... sai SHA-256` |
| 7 | Ghép file, kiểm tra hash | Tự động khi đủ chunk | `GHEP FILE ... HASH TOAN FILE KHOP` |
| + | Tải tiếp sau khi khởi động lại | Tắt C giữa chừng rồi chạy lại | `TIEP TUC TAI: da co san x/64 chunk` |

## Tính năng nâng cao đã làm

- **Rarest-first:** chunk có ít peer giữ nhất được tải trước.
- **Giới hạn băng thông:** dùng `--upload-slots` và `--slow`.
- **Tải tiếp (resume):** khi khởi động lại, peer quét các chunk đã có trên đĩa và kiểm tra lại hash.
- **Mô phỏng churn:** tracker tự xoá peer không gửi heartbeat quá 10 giây.

## Bảo mật

- **Xác thực:** mọi request tới tracker và tới peer phải có header `X-API-Key` đúng khoá; sai hoặc thiếu trả `401` và được ghi log (không ghi giá trị khoá). So sánh bằng `hmac.compare_digest`.
- **Bí mật qua biến môi trường:** khoá đọc từ `.env` hoặc biến môi trường, không có trong mã nguồn.
- **Kiểm tra dữ liệu vào:** metadata phải đúng định dạng (hash 64 ký tự hex, số chunk khớp), `peer_id` chỉ gồm chữ, số, `-`, `_`; dữ liệu sai trả `400`.
- **Giới hạn kích thước:** request JSON tối đa 1 MB (vượt thì `413`), chunk tối đa 4 MB, peer chỉ đọc tối đa `chunk_size` byte từ nguồn.
- **Toàn vẹn:** SHA-256 từng chunk và toàn file.

## Kiểm thử và đo hiệu năng

```bash
python -m unittest discover tests -v  # 20 test, khoảng 30–90 giây
python scripts/benchmark.py           # đo hiệu năng đầy đủ, ghi kết quả ra docs/benchmark.md
```

Các test dựng tracker và peer thật (mỗi node một tiến trình, giao tiếp qua mạng):

| File | Nhóm (mục 9 của đề) | Số test |
|---|---|---|
| `test_functional.py` | Chức năng: metadata, register, announce, leave, tải 1 nguồn, tải song song 2 nguồn, upload khi chưa xong, tải tiếp | 8 |
| `test_concurrency.py` | Đồng thời: 30 peer announce cùng lúc; 2 peer tải đồng thời và trao đổi chunk | 2 |
| `test_fault.py` | Lỗi và phục hồi: nguồn bị tắt giữa chừng (đổi nguồn); tracker khởi động lại | 2 |
| `test_security.py` | Bảo mật, dữ liệu sai: sai khoá; JSON hỏng, metadata sai, request quá lớn; chunk hỏng; đường dẫn và chỉ số sai | 4 |
| `test_performance.py` | Hiệu năng: 3 nguồn tải nhanh hơn 1 nguồn | 1 |
| `test_core.py` | Test đơn vị hàm cơ bản | 3 |

## Cấu trúc thư mục

```
src/        mã nguồn (common.py, tracker.py, peer.py)
deploy/     Dockerfile, docker-compose.yml
tests/      20 test tự động (helpers.py dựng cụm tracker + peer)
scripts/    demo.py, dashboard.py, benchmark.py, make_share.py
docs/       report (pdf/docx/md), slides (pdf/pptx), benchmark.md, GIAI_THICH.md, img/
```

## Phân công

| Thành viên | MSSV | Công việc |
|---|---|---|
| Nguyễn Lê Hoàng | B23DCVT172 | Tracker, metadata, băm SHA-256, xác thực API key, test chức năng và bảo mật, đo hiệu năng; báo cáo, slide, README |
| Lê Anh Vũ | B23DCAT342 | Peer (upload/download song song, đổi nguồn, rarest-first, resume), script demo, trang dashboard, test đồng thời, lỗi và hiệu năng, Docker |

## Khai báo sử dụng AI

Nhóm có dùng công cụ AI để hỗ trợ viết mã và tài liệu. Toàn bộ mã đã được nhóm chạy thử, đọc hiểu và chịu trách nhiệm.
