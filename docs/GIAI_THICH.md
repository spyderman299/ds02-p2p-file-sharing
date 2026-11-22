# Giải thích dự án và chuẩn bị vấn đáp

## 1. Phân công và ai commit file nào

| Đường dẫn | Nội dung | Ai commit |
|---|---|---|
| `.gitignore`, `.env.example` | Cấu hình mẫu (file `.env` thật KHÔNG commit) | Hoàng |
| `src/common.py` | Đọc `.env`, băm SHA-256, tạo metadata, gọi HTTP kèm khoá, ghi log | Hoàng |
| `src/tracker.py` | Tracker: xác thực, kiểm tra dữ liệu, register/announce/leave | Hoàng |
| `tests/helpers.py`, `tests/test_core.py`, `tests/test_functional.py`, `tests/test_security.py` | Tiện ích dựng cụm, 3 test đơn vị, 8 test chức năng, 4 test bảo mật | Hoàng |
| `scripts/benchmark.py`, `docs/benchmark.md` | Đo hiệu năng | Hoàng |
| `README.md`, `docs/img/`, `docs/report.*`, `docs/slides.*`, `docs/GIAI_THICH.md` | Tài liệu | Hoàng |
| `src/peer.py` | Peer (upload và download) | Vũ |
| `scripts/demo.py`, `scripts/make_share.py` | Demo tự động, tạo file mẫu | Vũ |
| `tests/test_concurrency.py`, `tests/test_fault.py`, `tests/test_performance.py` | 2 test đồng thời, 2 test lỗi, 1 test hiệu năng | Vũ |
| `deploy/Dockerfile`, `deploy/docker-compose.yml` | Docker | Vũ |

## 2. Chạy thử trên máy

```bash
copy .env.example .env                     # Windows CMD (PowerShell: Copy-Item .env.example .env)
python -m unittest discover tests -v       # 20 test, khoảng 25 giây, cuối cùng phải ra OK
python scripts/demo.py                      # demo toàn bộ, khoảng 10 giây
python scripts/benchmark.py                 # đo hiệu năng, khoảng 30 giây
```

## 3. Giải thích code theo từng file

### `common.py`
- `load_env()`: đọc file `.env` ở thư mục gốc và nạp vào biến môi trường. Nhờ vậy khoá bí mật không nằm trong code.
- `API_KEY`: khoá dùng chung của cả hệ thống, lấy từ `TRACKER_API_KEY`.
- `MAX_BODY = 1 MB`, `MAX_CHUNK = 4 MB`: giới hạn kích thước.
- `sha(b)`: mã băm SHA-256 dạng hex.
- `make_meta(path, tracker, chunk_size)`: đọc file từng khối 64 KB, băm từng khối và cộng dồn vào hash toàn file. `file_id` = 16 ký tự đầu của hash toàn file.
- `http_json(url, data)`: gửi POST nếu có `data`, GET nếu không; **luôn kèm header `X-API-Key`**.
- `log_setup(name)`: log dạng `giờ:phút:giây.mili [TÊN NODE] MỨC nội dung`.

### `tracker.py`
- Hai bảng trong RAM: `files[file_id] = metadata` và `peers[file_id][peer_id] = {peer_id, addr, chunks, seen}`.
- `authed()`: so khoá trong header với khoá của tracker bằng `hmac.compare_digest` (so sánh thời gian hằng số). Sai thì trả 401 và ghi log `AUTH tu choi`, không ghi giá trị khoá.
- `valid_meta()`: kiểm tra metadata đúng định dạng: hash 64 ký tự hex, số hash bằng `num_chunks`.
- `prune()`: xoá peer có `seen` cũ hơn 10 giây. Được gọi ở đầu mọi request, không cần luồng riêng.
- `do_POST`:
  - Đầu tiên kiểm tra khoá, rồi kiểm tra kích thước (lớn hơn 1 MB trả 413), rồi JSON (hỏng trả 400).
  - `/register` lưu metadata.
  - `/announce` kiểm tra `peer_id` (chỉ chữ, số, `-`, `_`), `addr`, chỉ số chunk rồi cập nhật bản ghi peer, trả về danh sách peer. File chưa đăng ký thì trả 404.
  - `/leave` xoá peer.
- `lock`: mỗi request chạy trên một luồng riêng, nên mọi truy cập hai bảng đều nằm trong lock.
- `main()`: chưa có khoá thì báo lỗi và dừng, không chạy khi chưa bật xác thực.

### `peer.py`, lớp `Peer`
- `setup(meta)`: kiểm tra `chunk_size ≤ 4 MB`, lưu `meta.json`, quét file chunk đã có; chunk nào đúng hash thì đưa vào `have` (đây là cơ chế **resume**).
- `split(src)`: seeder chia file thành các file chunk.
- `serve()`: HTTP server trả `GET /chunk/<file_id>/<i>`.
  - Kiểm tra `X-API-Key` trước, sai trả 401.
  - Chỉ trả chunk có trong `have`, ngược lại 404.
  - `slots` (Semaphore) giới hạn số lượt gửi cùng lúc.
  - `--corrupt` giả lập peer gửi hỏng.
- `announce()`: gửi danh sách chunk, nhận danh sách peer. Nhận 404 (tracker vừa khởi động lại) thì gửi lại `/register`. Nhận 401 thì báo sai khoá.
- `heartbeat()`: announce mỗi 3 giây.
- `get_chunk(i, cands)`: thử lần lượt từng peer.
  - Lỗi mạng: đánh dấu chết 10 giây, ghi log **DOI NGUON**.
  - Dài hơn `chunk_size` hoặc sai hash: đánh dấu `(i, peer)` xấu, ghi log **CHUNK KHONG HOP LE**.
  - Đúng: ghi file, rồi thêm vào `have` trong lock.
- `download()`: vòng lặp tính chunk thiếu → announce → lọc nguồn → sắp xếp **rarest-first** → ThreadPool W luồng tải lô 2W chunk.
- `merge()`: ghép theo thứ tự 0..n-1, kiểm tra hash toàn file.

### `tests/`
- `helpers.py`, lớp `Cluster`: dựng tracker và peer **thật** (mỗi node một tiến trình, cổng ngẫu nhiên), đọc log, kiểm tra file tải về có đúng hash không.
- Mỗi test tự dựng cụm riêng rồi dọn sạch, nên các test không ảnh hưởng nhau.

## 4. Câu hỏi vấn đáp

**Phần Hoàng (tracker, metadata, bảo mật, test chức năng và bảo mật, hiệu năng)**

1. **Tracker có giữ nội dung file không?** Không. Chỉ có metadata và danh sách peer; không có API nào trả byte của file.
2. **Metadata gồm những gì?** `file_id`, tên, kích thước, kích thước chunk, số chunk, hash từng chunk, hash toàn file, địa chỉ tracker. Hash dùng để kiểm chứng dữ liệu từ peer lạ.
3. **Vì sao dùng SHA-256?** CRC làm giả được, MD5 đã bị phá va chạm; SHA-256 an toàn và có sẵn trong Python.
4. **`file_id` sinh thế nào?** 16 ký tự đầu của hash toàn file. Cùng nội dung thì cùng ID, nên tự vào chung một swarm.
5. **Vì sao chunk 64 KB?** Đủ nhỏ để thấy rõ tải song song, đủ lớn để không quá nhiều request.
6. **Tracker biết peer chết thế nào?** Heartbeat: peer announce mỗi 3 giây; quá 10 giây không thấy thì `prune()` xoá. Trong code là `PEER_TIMEOUT = 10`.
7. **Nhiều peer announce cùng lúc thì sao?** Mỗi request một luồng, nhưng dữ liệu được bảo vệ bằng `with lock:`. Test C1 chứng minh: 30 peer announce cùng lúc, tracker ghi đủ 30.
8. **Tracker sập thì sao?** Peer vẫn tải với danh sách đã biết; tracker chạy lại thì peer tự đăng ký lại metadata (test R2).
9. **Vì sao dùng HTTP?** Chạy trên TCP, có sẵn đóng gói dữ liệu và mã lỗi (401, 404, 413), dễ debug.
10. **Hệ thống xác thực thế nào?** Mọi request tới tracker và tới peer phải có header `X-API-Key` đúng khoá bí mật chung. Sai hoặc thiếu trả 401. So sánh bằng `hmac.compare_digest` để không lộ thông tin qua thời gian phản hồi.
11. **Khoá để ở đâu, có lên GitHub không?** Trong file `.env`, file này nằm trong `.gitignore` nên không bị commit. Repo chỉ có `.env.example` với giá trị mẫu.
12. **Chống dữ liệu xấu thế nào?** Kiểm tra định dạng metadata và `peer_id`, giới hạn request 1 MB (413), chunk tối đa 4 MB, peer chỉ đọc tối đa `chunk_size` byte, đường dẫn và chỉ số chunk sai trả 404. Test S1–S4 chứng minh.
13. **Nhóm test những gì?** Đúng mục 9 của đề: 8 chức năng, 2 đồng thời, 2 lỗi và phục hồi, 4 bảo mật, 1 hiệu năng, cộng 3 test đơn vị, tổng 20 test, đều đạt. Mỗi test dựng tracker và peer thật chạy qua mạng.
14. **Kết quả hiệu năng?** 3 nguồn nhanh hơn 1 nguồn khoảng 33%; 8 kết nối nhanh hơn 1 kết nối hơn 4 lần; tắt 1 nguồn thì khoảng 83 ms sau đã phát hiện, file vẫn đúng hash.

**Phần Vũ (peer, demo, test đồng thời, lỗi, hiệu năng, Docker)**

15. **Tải song song thế nào?** `ThreadPoolExecutor` tối đa `--workers` luồng, mỗi luồng tải 1 chunk; nguồn được xáo ngẫu nhiên nên chunk đến từ nhiều peer.
16. **Vì sao giới hạn số kết nối?** Tránh quá tải mình và nguồn. 1 → 8 kết nối nhanh hơn 4,4 lần, nhưng không tăng vô hạn được.
17. **Vì sao peer gửi được chunk khi chưa tải xong?** Server upload chạy song song với bộ tải; chunk nào kiểm tra hash và ghi xong là vào `have`, phục vụ được ngay (test F7).
18. **Rarest-first là gì?** Tải trước chunk có ít peer giữ nhất, để chunk hiếm nhanh có thêm bản sao, không bị mất khi nguồn duy nhất rời mạng.
19. **Nguồn bị tắt thì sao?** Lỗi kết nối hoặc timeout 5 s → đánh dấu chết 10 s → thử ngay nguồn khác (test R1).
20. **Phát hiện chunk hỏng thế nào?** So SHA-256 với `chunk_hashes[i]`; sai thì không ghi, đánh dấu (chunk, peer) xấu, tải từ peer khác (test S3).
21. **Tải tiếp sau khi tắt thế nào?** Chunk đã trên đĩa; khi chạy lại, `setup()` băm lại từng file chunk, chỉ tải phần thiếu (test F8).
22. **Thông điệp trùng lặp hay sai thứ tự thì sao?** announce ghi đè bản cũ nên gửi trùng vô hại; tải trùng chunk thì ghi đè đúng nội dung, `have` là tập hợp; chunk về thứ tự nào cũng được, cuối cùng ghép theo chỉ số.
23. **Có race condition không?** `have` được bảo vệ bằng lock; mỗi chunk một file riêng, ghi xong mới thêm vào `have`.
24. **Docker chạy thế nào?** Mỗi node một container trên mạng `p2p`, gọi nhau bằng tên container; khoá truyền qua biến môi trường `TRACKER_API_KEY`.

## 5. Lệnh demo tay (mỗi lệnh 1 cửa sổ terminal, trong thư mục `src/`, nhớ có file `.env` ở thư mục gốc)

```bash
python tracker.py
python peer.py seed ../share/video.bin --id A --port 9001 --slow 0.15
python peer.py seed ../share/video.bin --id B --port 9002 --slow 0.15 --corrupt 0-15
python peer.py get <file_id> --id C --port 9003 --slow 0.15
python peer.py get <file_id> --id D --port 9004 --slow 0.15
# Ctrl+C cửa sổ B giữa chừng để demo đổi nguồn
```

Tạo file mẫu `share/video.bin` trước bằng `python scripts/make_share.py`. `file_id` in ra trong log của A.
