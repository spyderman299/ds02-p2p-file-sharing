"""Trang trinh bay + theo doi demo truc tiep. Chay: python scripts/dashboard.py  roi mo http://127.0.0.1:8080
Trang chi DOC log trong demo_data/logs (khong sua he thong). Nut "Chay demo" goi scripts/demo.py."""
import glob, json, os, re, subprocess, sys, threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS = os.path.join(ROOT, "demo_data", "logs")
LINE = re.compile(r"^(\d\d:\d\d:\d\d\.\d+) \[(\w+)\] (\w+) (.*)$")
run = {"proc": None, "out": []}


def read_lines():
    out = []
    for path in glob.glob(os.path.join(LOGS, "*.log")):
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                for l in f:
                    m = LINE.match(l.strip())
                    if m:
                        out.append(m.groups())
        except OSError:
            pass
    return sorted(out)


def explain(node, msg):
    """Doi mot dong log thanh cau giai thich tieng Viet (None = khong hien)."""
    pats = [
        (r"Tracker chay", "Tracker khởi động, đã bật xác thực API key"),
        (r"REGISTER file (\w+) \(.*?, (\d+) chunk\)", "Tracker nhận đăng ký metadata: file {0}, {1} mảnh"),
        (r"JOIN peer (\w+) .*\(co (\d+)/(\d+)", "Tracker ghi {0} vào danh sách (đang có {1}/{2} mảnh)"),
        (r"LEAVE peer (\w+)", "{0} tải xong, chủ động rời nhóm"),
        (r"TIMEOUT peer (\w+)", "{0} quá 10 giây không gửi heartbeat → tracker xoá khỏi danh sách"),
        (r"SEED file", node + " là seeder: có sẵn cả file, sẵn sàng gửi"),
        (r"CHUNK KHONG HOP LE (\d+) tu (\w+)", node + ": mảnh {0} nhận từ {1} SAI HASH → bỏ, tải lại nơi khác"),
        (r"LOI tai chunk (\d+) tu (\w+)", node + ": {1} không phản hồi → ĐỔI NGUỒN"),
        (r"TIEP TUC TAI: da co san (\d+)/(\d+)", node + ": khởi động lại, giữ {0}/{1} mảnh cũ → tải tiếp"),
        (r"HASH TOAN FILE KHOP", node + ": ghép đủ mảnh, hash cả file KHỚP ✓"),
        (r"DANG KY LAI", node + ": tracker mất dữ liệu → tự đăng ký lại metadata"),
        (r"UPLOAD chunk (\d+) -> (\w+) \(minh dang co (\d+)/(\d+)\)", None),
    ]
    for p, text in pats:
        m = re.search(p, msg)
        if m:
            if text is None:  # upload khi chua tai xong
                g = m.groups()
                return None if g[2] == g[3] else f"{node} gửi mảnh {g[0]} cho {g[1]} khi mới có {g[2]}/{g[3]} mảnh"
            return text.format(*m.groups())
    return None


def state():
    lines = read_lines()
    peers, members, events, total, fid = {}, {}, [], 64, ""
    stats = {"corrupt": 0, "failover": 0, "early_upload": 0}

    def P(n):
        return peers.setdefault(n, {"chunks": {}, "status": "Đang chờ", "resumed": 0})

    for ts, node, lvl, msg in lines:
        name = "E" if node == "E" else node
        if node != "TRACKER":
            p = P(name)
            if "SEED file" in msg:
                p["status"] = "Seeder (có đủ file)"
                p["seed"] = True
            m = re.search(r"OK chunk (\d+) tu (\w+) \((\d+)/(\d+)\)", msg)
            if m:
                p["chunks"][m.group(1)] = m.group(2)
                total = int(m.group(4))
                if p["status"] == "Đang chờ":
                    p["status"] = "Đang tải"
            if "TIEP TUC TAI" in msg:
                p["resumed"] = int(re.search(r"san (\d+)", msg).group(1))
                p["status"] = "Tải tiếp sau khi khởi động lại"
            if "HASH TOAN FILE KHOP" in msg:
                p["status"] = "Xong ✓ (hash khớp)"
            if "CHUNK KHONG HOP LE" in msg:
                stats["corrupt"] += 1
            if "DOI NGUON" in msg:
                stats["failover"] += 1
            e = explain(node, msg)
            if e and "UPLOAD" in msg:
                stats["early_upload"] += 1
        else:
            m = re.search(r"REGISTER file (\w+) \(.*?, (\d+) chunk", msg)
            if m:
                fid, total = m.group(1), int(m.group(2))
            m = re.search(r"JOIN peer (\w+) .*\(co (\d+)/", msg)
            if m:
                members[m.group(1)] = "trong nhóm"
            m = re.search(r"(LEAVE|TIMEOUT) peer (\w+)", msg)
            if m:
                members[m.group(2)] = "đã rời (LEAVE)" if m.group(1) == "LEAVE" else "bị xoá (TIMEOUT)"
                if m.group(1) == "TIMEOUT":
                    P(m.group(2))["status"] = "Bị tắt đột ngột"
            e = explain(node, msg)
        if e:
            events.append({"t": ts[:8], "node": node, "lvl": lvl, "text": e})
    if any(l.startswith("[3]") for l in run["out"]) and "B" in peers:  # demo da tat dot ngot B
        peers["B"]["status"] = "Bị tắt đột ngột"
        if members.get("B") == "trong nhóm":
            members["B"] = "bị tắt, chờ quá 10 giây sẽ bị xoá"
    early = [e for e in events if "khi mới có" in e["text"]]
    events = [e for e in events if "khi mới có" not in e["text"]] + early[:3]
    events.sort(key=lambda e: e["t"], reverse=True)  # moi nhat len dau
    return {"peers": peers, "members": members, "events": events[:40], "total": total, "fid": fid,
            "stats": stats, "running": run["proc"] is not None and run["proc"].poll() is None, "out": run["out"][-30:]}


def start_demo():
    if run["proc"] is not None and run["proc"].poll() is None:
        return
    run["out"] = []
    env = {**os.environ, "DEMO_SLOW": "0.4"}  # cham lai de nguoi xem kip theo doi
    run["proc"] = subprocess.Popen([sys.executable, "-u", os.path.join(ROOT, "scripts", "demo.py")], cwd=ROOT, env=env,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="ignore")

    def pump(p):
        for l in p.stdout:
            run["out"].append(l.rstrip())
    threading.Thread(target=pump, args=(run["proc"],), daemon=True).start()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            return self.send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        if self.path == "/api/state":
            return self.send(200, json.dumps(state(), ensure_ascii=False).encode("utf-8"), "application/json")
        if self.path.startswith("/img/") and self.path[5:] in ("arch.png", "flow.png", "bench.png"):
            with open(os.path.join(ROOT, "docs", "img", self.path[5:]), "rb") as f:
                return self.send(200, f.read(), "image/png")
        self.send(404, b"not found", "text/plain")

    def do_POST(self):
        if self.path == "/api/run":
            start_demo()
            return self.send(200, b"{}", "application/json")
        self.send(404, b"not found", "text/plain")


PAGE = r"""<!DOCTYPE html><html lang="vi"><head><meta charset="utf-8"><title>DS02 – P2P File Sharing</title>
<style>
:root{--navy:#0b2545;--teal:#13a89e;--bg:#f4f7f9;--ink:#1b2430;--mut:#5b6672}
*{box-sizing:border-box}body{margin:0;font-family:Segoe UI,Arial,sans-serif;color:var(--ink);background:var(--bg)}
header{background:var(--navy);color:#fff;padding:14px 28px;display:flex;align-items:center;gap:24px}
header h1{font-size:20px;margin:0}header span{color:#9fd8d2;font-size:14px}
nav{display:flex;gap:6px;margin-left:auto}nav button{background:transparent;color:#cfe3ea;border:1px solid #3d5a7a;padding:8px 14px;border-radius:6px;cursor:pointer;font-size:14px}
nav button.on{background:var(--teal);color:#fff;border-color:var(--teal)}
main{padding:22px 28px;max-width:1400px;margin:auto}.tab{display:none}.tab.on{display:block}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:20px}.card{background:#fff;border-radius:10px;padding:18px 20px;box-shadow:0 1px 3px #0001}
h2{margin:0 0 12px;font-size:20px;color:var(--navy)}h3{margin:0 0 8px;font-size:16px;color:var(--navy)}
p,li{line-height:1.55;font-size:15px}dl{margin:0}dt{font-weight:700;margin-top:10px;color:var(--navy)}dd{margin:2px 0 0 0;font-size:15px;line-height:1.5}
.tag{display:inline-block;background:#e6f4f3;color:#0d6f68;border-radius:4px;padding:1px 7px;font-size:13px;font-weight:600}
ol.steps{counter-reset:s;list-style:none;padding:0;margin:0}ol.steps li{counter-increment:s;position:relative;padding:10px 12px 10px 48px;margin-bottom:8px;background:#fff;border-radius:8px}
ol.steps li:before{content:counter(s);position:absolute;left:12px;top:10px;width:26px;height:26px;border-radius:50%;background:var(--teal);color:#fff;text-align:center;line-height:26px;font-weight:700}
table{border-collapse:collapse;width:100%;font-size:14px}th,td{border:1px solid #dde3e8;padding:7px 9px;text-align:left}th{background:#eef3f6}
.run{background:var(--teal);color:#fff;border:0;padding:12px 22px;border-radius:8px;font-size:16px;cursor:pointer}.run:disabled{background:#9aa5ad}
.demo{display:grid;grid-template-columns:1.6fr 1fr;gap:20px;margin-top:16px}
.peer{display:flex;align-items:center;gap:12px;margin:10px 0}.pname{width:34px;height:34px;border-radius:50%;color:#fff;font-weight:700;display:flex;align-items:center;justify-content:center;flex:none}
.cells{display:grid;grid-template-columns:repeat(32,1fr);gap:2px;flex:1}.cells div{height:13px;border-radius:2px;background:#e3e8ec}
.pstat{width:190px;font-size:13px;color:var(--mut)}.legend span{display:inline-flex;align-items:center;gap:5px;margin-right:14px;font-size:13px}.legend i{width:12px;height:12px;border-radius:2px;display:inline-block}
.ev{font-size:13.5px;padding:5px 0;border-bottom:1px solid #eef1f3}.ev b{color:var(--mut);font-weight:500;margin-right:6px}.ev.warn{color:#b3361d}.ev.ok{color:#0d6f68}
.stats{display:flex;gap:12px;margin-top:12px}.stat{flex:1;background:#fff;border-radius:8px;padding:10px;text-align:center}.stat div{font-size:26px;font-weight:700;color:var(--teal)}.stat small{color:var(--mut)}
.mem{font-size:14px;margin:4px 0}.muted{color:var(--mut);font-size:13px}
</style></head><body>
<header><h1>DS02 · Hệ thống chia sẻ file P2P mô phỏng BitTorrent</h1><span>Nguyễn Lê Hoàng · Lê Anh Vũ</span>
<nav><button class="on" data-t="t1">1. Tổng quan</button><button data-t="t2">2. Luồng hoạt động</button><button data-t="t3">3. Demo trực tiếp</button><button data-t="t4">4. Bảo mật &amp; kiểm thử</button></nav></header>
<main>
<section id="t1" class="tab on"><div class="grid2">
<div class="card"><h2>Bài toán</h2><p>Nhiều người cùng tải một file. Mô hình <b>client–server</b> (tải từ một máy chủ): đông người thì máy chủ quá tải, máy chủ sập thì không ai tải được.</p>
<p>Giải pháp: mô hình <b>P2P</b> (<i>peer-to-peer</i>, ngang hàng): các máy gửi dữ liệu trực tiếp cho nhau, mỗi máy vừa tải về vừa gửi đi.</p>
<h2 style="margin-top:18px">Định nghĩa</h2><dl>
<dt>Peer</dt><dd>Mỗi máy tham gia chia sẻ; vừa tải về vừa gửi đi. Peer có sẵn cả file gọi là <b>seeder</b>.</dd>
<dt>Tracker</dt><dd>Server lưu <b>metadata</b> và <b>danh sách peer</b> kèm các mảnh mỗi peer đang có. <b>Không lưu, không gửi nội dung file.</b></dd>
<dt>Chunk (mảnh)</dt><dd>File chia thành các mảnh 64 KB (file 4 MB = 64 mảnh) để tải song song từ nhiều peer.</dd>
<dt>Hash SHA-256</dt><dd>Chuỗi 64 ký tự đại diện cho nội dung; sửa 1 byte là hash đổi hoàn toàn. Dùng để kiểm tra mảnh nhận được.</dd>
<dt>Metadata</dt><dd>Thông tin mô tả file: file_id, tên, kích thước, kích thước mảnh, số mảnh, <b>hash từng mảnh</b>, <b>hash cả file</b>, địa chỉ tracker.</dd>
<dt>file_id</dt><dd>16 ký tự đầu của hash cả file → cùng nội dung thì cùng mã.</dd></dl></div>
<div class="card"><h2>Kiến trúc</h2><img src="/img/arch.png" style="width:100%"><p class="muted">Nét đứt: peer đăng ký và thông báo với tracker. Nét liền: peer tải mảnh trực tiếp từ nhau. Mỗi thành phần là một tiến trình riêng, giao tiếp qua HTTP.</p></div>
</div></section>

<section id="t2" class="tab"><div class="grid2">
<div><h2>Một lượt chia sẻ</h2><ol class="steps">
<li><b>Đăng ký</b> <span class="tag">register</span>: seeder gửi metadata lên tracker.</li>
<li><b>Thông báo</b> <span class="tag">announce</span>: peer báo tracker danh sách mảnh mình có; tracker trả về danh sách peer khác.</li>
<li><b>Tải song song</b>: peer tải nhiều mảnh cùng lúc trực tiếp từ các peer khác, ưu tiên mảnh ít người có (<i>rarest-first</i>).</li>
<li><b>Kiểm tra</b>: mỗi mảnh tính SHA-256 và so với metadata; sai thì bỏ, tải lại từ peer khác.</li>
<li><b>Vừa tải vừa gửi</b>: mảnh đã có được gửi ngay cho peer khác, dù chưa đủ file.</li>
<li><b>Hoàn tất</b>: ghép mảnh theo thứ tự, kiểm tra hash cả file, báo tracker rời nhóm <span class="tag">leave</span>.</li></ol></div>
<div class="card"><h2>Khi có sự cố</h2><table><tr><th>Sự cố</th><th>Hệ thống xử lý</th></tr>
<tr><td>Peer ngừng hoạt động đột ngột</td><td>Peer gửi <b>heartbeat</b> (thông báo định kỳ) mỗi 3 giây; quá 10 giây không có → tracker xoá</td></tr>
<tr><td>Nguồn bị tắt khi đang tải</td><td>Peer phát hiện lỗi kết nối → đổi sang nguồn khác</td></tr>
<tr><td>Nguồn gửi mảnh hỏng</td><td>Phát hiện qua hash → bỏ, tải lại nơi khác</td></tr>
<tr><td>Peer đang tải bị tắt</td><td>Mảnh đã lưu trên đĩa → chạy lại thì tải tiếp</td></tr>
<tr><td>Tracker khởi động lại</td><td>Peer tự đăng ký lại metadata</td></tr></table>
<h3 style="margin-top:16px">Đồng thời</h3><p>Tracker xử lý mỗi yêu cầu trên một <b>luồng</b> (thread) riêng; dữ liệu dùng chung được bảo vệ bằng <b>khoá</b> (lock) để các luồng không ghi đè nhau.</p></div>
</div></section>

<section id="t3" class="tab">
<div style="display:flex;align-items:center;gap:18px"><button class="run" id="run">▶ Chạy demo</button>
<div class="muted">Kịch bản: A là nguồn tốt, B cố tình gửi mảnh hỏng. C và D tải cùng lúc (đồng thời). Giữa chừng tắt đột ngột B (lỗi). E bị tắt rồi chạy lại (tải tiếp).</div></div>
<div class="stats"><div class="stat"><div id="s1">0</div><small>mảnh hỏng bị phát hiện</small></div><div class="stat"><div id="s2">0</div><small>lần đổi nguồn</small></div><div class="stat"><div id="s3">0</div><small>lần gửi khi chưa tải xong</small></div><div class="stat"><div id="s4">–</div><small>file_id</small></div></div>
<div class="demo"><div class="card"><h3>Mảnh của từng peer (màu = mảnh lấy từ peer nào)</h3><div class="legend" id="legend"></div><div id="peers"></div></div>
<div><div class="card"><h3>Danh sách trong tracker</h3><div id="members" class="muted">Chưa chạy</div></div>
<div class="card" style="margin-top:14px;max-height:430px;overflow:auto"><h3>Sự kiện mới nhất (giải thích từ log)</h3><div id="events" class="muted">Chưa chạy</div></div></div></div>
</section>

<section id="t4" class="tab"><div class="grid2">
<div class="card"><h2>Bảo mật</h2><table><tr><th>Biện pháp</th><th>Cách làm</th></tr>
<tr><td>Xác thực</td><td>Mọi yêu cầu kèm mã khoá <b>API key</b> (header X-API-Key); sai → 401</td></tr>
<tr><td>Giữ bí mật</td><td>Khoá trong file .env, không đưa lên GitHub</td></tr>
<tr><td>Kiểm tra dữ liệu</td><td>Sai định dạng → 400; tên peer chỉ gồm chữ, số, -, _</td></tr>
<tr><td>Giới hạn kích thước</td><td>Yêu cầu tối đa 1 MB (413), mảnh tối đa 4 MB</td></tr>
<tr><td>Toàn vẹn</td><td>SHA-256 từng mảnh và cả file</td></tr>
<tr><td>Ghi log</td><td>Đăng ký, vào/rời nhóm, timeout, từ chối xác thực</td></tr></table></div>
<div class="card"><h2>Kiểm thử: 20 test tự động, đều đạt</h2><table><tr><th>Nhóm (mục 9 của đề)</th><th>Số test</th><th>Ví dụ</th></tr>
<tr><td>Chức năng</td><td>8</td><td>Tải từ 2 nguồn, tải tiếp sau khi tắt</td></tr>
<tr><td>Đồng thời</td><td>2</td><td>30 peer thông báo cùng lúc</td></tr>
<tr><td>Lỗi, phục hồi</td><td>2</td><td>Tắt nguồn giữa chừng, tracker khởi động lại</td></tr>
<tr><td>Bảo mật</td><td>4</td><td>Sai khoá 401, quá lớn 413, mảnh hỏng</td></tr>
<tr><td>Hiệu năng</td><td>1</td><td>3 nguồn nhanh hơn 1 nguồn</td></tr>
<tr><td>Đơn vị</td><td>3</td><td>Hàm tạo metadata, phát hiện byte bị sửa</td></tr></table>
<h3 style="margin-top:14px">Hiệu năng (file 4 MB)</h3><img src="/img/bench.png" style="width:100%"></div>
</div></section>
</main>
<script>
const COL={A:"#2a6f97",B:"#e76f51",C:"#13a89e",D:"#8ab17d",E:"#f4a261"};
document.querySelectorAll("nav button").forEach(b=>b.onclick=()=>{document.querySelectorAll("nav button,.tab").forEach(x=>x.classList.remove("on"));b.classList.add("on");document.getElementById(b.dataset.t).classList.add("on")});
document.getElementById("run").onclick=()=>fetch("/api/run",{method:"POST"});
document.getElementById("legend").innerHTML=Object.entries(COL).map(([k,v])=>`<span><i style="background:${v}"></i>từ ${k}</span>`).join("")+'<span><i style="background:#0b2545"></i>có sẵn (seeder)</span>';
async function tick(){try{const s=await (await fetch("/api/state")).json();
document.getElementById("run").disabled=s.running;document.getElementById("run").textContent=s.running?"Đang chạy...":"▶ Chạy demo";
s1.textContent=s.stats.corrupt;s2.textContent=s.stats.failover;s3.textContent=s.stats.early_upload;s4.textContent=s.fid||"–";
const names=Object.keys(s.peers).sort();
document.getElementById("peers").innerHTML=names.length?names.map(n=>{const p=s.peers[n];let c="";for(let i=0;i<s.total;i++){const src=p.seed?"seed":p.chunks[i];c+=`<div style="background:${src==="seed"?"#0b2545":(COL[src]||"#e3e8ec")}"></div>`}
return `<div class="peer"><div class="pname" style="background:${COL[n]||"#666"}">${n}</div><div class="cells">${c}</div><div class="pstat">${p.status}<br>${p.seed?s.total:Object.keys(p.chunks).length}/${s.total} mảnh</div></div>`}).join(""):'<p class="muted">Bấm "Chạy demo"</p>';
const m=Object.entries(s.members);document.getElementById("members").innerHTML=m.length?m.map(([k,v])=>`<div class="mem"><b style="color:${COL[k]}">${k}</b>: ${v}</div>`).join(""):"Chưa có";
document.getElementById("events").innerHTML=s.events.length?s.events.map(e=>`<div class="ev ${/SAI|ĐỔI|xoá/.test(e.text)?"warn":/KHỚP|tải tiếp/.test(e.text)?"ok":""}"><b>${e.t}</b>${e.text}</div>`).join(""):"Chưa có";
}catch(e){}setTimeout(tick,400)}tick();
</script></body></html>"""


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", 8080), H)
    print("Mo trinh duyet: http://127.0.0.1:8080   (Ctrl+C de dung)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
