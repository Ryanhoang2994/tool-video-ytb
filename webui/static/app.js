// Cold Case Studio – giao diện web (gọi API của webui/server.py)
const $ = (s, el = document) => el.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const app = $("#app");
let poll = null, logOffset = 0, presets = [], envKeys = [];

const STEPS = [
  ["research", "Tư liệu", "Tìm nguồn: Wikipedia, báo cũ, link bạn đưa"],
  ["script", "Kịch bản", "Claude viết kịch bản + storyboard"],
  ["voice", "Giọng đọc", "Đọc lời từng cảnh"],
  ["media", "Hình ảnh", "Ảnh/video có bản quyền + ảnh AI"],
  ["render", "Dựng video", "Ghép hình, chuyển động, nhạc, hiệu ứng"],
  ["check", "Kiểm tra", "Soát phép tính, nguồn, phụ đề, âm lượng"],
  ["capcut", "CapCut", "Xuất bản nháp để chỉnh tay"],
];
const PRESET_NAME = {
  crime_doc: "Vụ án / tư liệu", ocean_creatures: "Đại dương & sinh vật", psychology_2d: "Tâm lý học 2D",
  housing_finance_2d: "Nhà ở / tài chính 2D", mystery_horror: "Bí ẩn / kinh dị",
};
const OPT = {
  visual_type: ["archival_photo", "location", "document", "newspaper", "map", "atmosphere", "person", "evidence", "video_broll",
    "board", "quote", "character", "diagram", "species", "chart", "insert"],
  fx: ["auto", "none", "shudder", "action", "impact", "reveal", "glitch"],
  mood: ["auto", "neutral", "night", "rain", "warm", "phone", "tense", "sad", "hopeful", "dawn"],
  music: ["", "calm", "sad", "tense", "hopeful", "dark", "light", "action", "horror", "silence"],
  camera: ["auto", "push_in", "pull_out", "pan_lr", "pan_rl", "tilt_down", "tilt_up", "punch", "snap_zoom", "float", "shake",
    "slam", "torch", "hold"],
  expression: ["", "neutral", "happy", "smile", "worried", "sad", "surprised", "thinking", "smug", "angry", "nervous", "scared",
    "tired", "crying", "anxious", "panic", "empty", "determined", "relieved", "smirk"],
  pose: ["", "stand", "wave", "think", "point", "shrug", "hold", "cheer", "sit", "phone", "hug", "cover", "slump"],
  framing: ["auto", "wide", "closeup"],
};
const LABEL = {
  fx: { auto: "tự đoán", none: "không", shudder: "rùng mình", action: "hành động", impact: "chấn động", reveal: "tiết lộ", glitch: "nhiễu" },
  music: { "": "(giữ nhạc trước)", calm: "êm", sad: "buồn", tense: "căng thẳng", hopeful: "hi vọng", dark: "u tối", light: "nhẹ nhàng",
    action: "hành động", horror: "kinh dị", silence: "tắt nhạc" },
  mood: { auto: "tự động", neutral: "bình thường", night: "đêm", rain: "mưa", warm: "đèn ấm", phone: "ánh điện thoại", tense: "căng thẳng",
    sad: "buồn", hopeful: "hi vọng", dawn: "bình minh" },
};

async function api(url, opt = {}) {
  const r = await fetch(url, { headers: { "Content-Type": "application/json" }, ...opt });
  if (!r.ok) {
    let msg = r.statusText;
    try { const t = await r.text(); const m = t.match(/<p>(.*?)<\/p>/s); msg = m ? m[1] : t.slice(0, 200); } catch (e) { }
    throw new Error(msg);
  }
  return r.json();
}
function toast(msg, ms = 3000) {
  const t = $("#toast"); t.textContent = msg; t.classList.add("show");
  clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove("show"), ms);
}
const fmtDur = s => s ? `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}` : "";
const sel = (name, val, opts, labels = {}) =>
  `<select data-f="${name}">${opts.map(o => `<option value="${esc(o)}" ${o === (val ?? "") ? "selected" : ""}>${esc(labels[o] ?? (o || "—"))}</option>`).join("")}</select>`;

function nav(which) { document.querySelectorAll("[data-nav]").forEach(a => a.classList.toggle("on", a.dataset.nav === which)); }

// ---------------------------------------------------------------- router
async function route() {
  clearInterval(poll); poll = null;
  const h = location.hash.slice(1) || "/";
  try {
    if (h === "/") { nav("home"); await viewHome(); }
    else if (h === "/new") { nav("new"); await viewNew(); }
    else if (h === "/settings") { nav("settings"); await viewSettings(); }
    else if (h === "/help") { nav("help"); viewHelp(); }
    else if (h.startsWith("/p/")) { nav(""); await viewProject(decodeURIComponent(h.slice(3))); }
    else { app.innerHTML = `<div class="empty">Không có trang này</div>`; }
  } catch (e) { app.innerHTML = `<div class="warn">Lỗi: ${esc(e.message)}</div>`; }
}
addEventListener("hashchange", route);

// ---------------------------------------------------------------- danh sách dự án
async function viewHome() {
  const items = await api("/api/projects");
  app.innerHTML = `
    <div class="row"><div class="grow"><h1>Dự án</h1><div class="sub">${items.length} video · bấm vào để mở, sửa cảnh, dựng lại</div></div>
    <a class="btn primary" href="#/new">＋ Tạo video mới</a></div>
    ${items.length ? `<div class="grid">${items.map(card).join("")}</div>` :
      `<div class="empty">Chưa có dự án nào.<br><br><a class="btn primary" href="#/new">Tạo video đầu tiên</a></div>`}`;
  app.querySelectorAll("[data-slug]").forEach(el => el.onclick = () => location.hash = "#/p/" + el.dataset.slug);
  if (items.some(i => i.running)) poll = setInterval(async () => {
    const again = await api("/api/projects");
    if (!again.some(i => i.running)) route();
  }, 3000);
}
function card(p) {
  const done = STEPS.slice(0, 6).map(([k]) => `<i class="${p.status[k] ? "on" : ""}"></i>`).join("");
  return `<div class="card link" data-slug="${esc(p.slug)}">
    <div class="thumb" style="${p.thumb ? `background-image:url('${p.thumb}')` : ""}">${p.thumb ? "" : "🎬"}
      ${p.duration ? `<span class="dur">${fmtDur(p.duration)}</span>` : ""}</div>
    <div class="body"><div class="title">${esc(p.title)}</div>
      <span class="pill">${esc(PRESET_NAME[p.preset] || p.preset)}</span>
      ${p.scenes ? `<span class="pill">${p.scenes} cảnh</span>` : ""}
      ${p.running ? `<span class="pill run">● đang chạy</span>` : p.status.render ? `<span class="pill ok">✓ có video</span>` : ""}
      <div class="steps">${done}</div></div></div>`;
}

// ---------------------------------------------------------------- tạo mới
async function viewNew() {
  if (!presets.length) presets = await api("/api/presets");
  envKeys = await api("/api/env");
  const cc = await api("/api/claude-code").catch(() => ({ installed: false }));
  const hasClaude = envKeys.find(k => k.key === "ANTHROPIC_API_KEY")?.set || cc.installed;
  let cur = "crime_doc";
  app.innerHTML = `
    <h1>Tạo video mới</h1><div class="sub">Chọn phong cách, nhập chủ đề – tool tự tìm tư liệu, viết kịch bản, đọc, tìm hình và dựng.</div>
    <div class="panel"><label style="margin-top:0">Phong cách (preset)</label><div class="presets" id="pr">
      ${presets.map(p => `<div class="preset ${p.id === cur ? "on" : ""}" data-id="${p.id}"><b>${esc(PRESET_NAME[p.id] || p.id)}</b><span>${esc(p.description)}</span></div>`).join("")}
    </div>
    <label>Chủ đề / câu hỏi của video *</label>
    <input type="text" id="topic" placeholder="vd: Vụ không tặc D. B. Cooper  ·  Vì sao có người rất khó mở lời nhờ giúp đỡ?">
    <div class="sub" style="margin:6px 0 0;font-size:12px">Nhập chủ đề <b>cụ thể</b> (tên vụ việc / nhân vật, năm, địa điểm). Chủ đề chung chung như "vụ án thảm sát" thì Claude không biết viết về vụ nào.</div>
    <div class="cols">
      <div><label>Thời lượng (phút)</label><input type="number" id="minutes" min="1" max="60" value="10"></div>
      <div><label>Ngôn ngữ</label><select id="language"><option value="vi">Tiếng Việt</option><option value="en">English</option></select></div>
      <div style="grid-column: span 2"><label>Người xem</label><input type="text" id="audience" placeholder="vd: người 18-35 tuổi, chưa biết gì về chủ đề"></div>
    </div>
    <div id="extra"></div>
    <details style="margin-top:12px"><summary style="cursor:pointer;color:var(--info)">Thêm tư liệu / kịch bản có sẵn</summary>
      <label>Link bài báo / tư liệu (mỗi dòng 1 link)</label><textarea id="urls" rows="2"></textarea>
      <label>Ghi chú / tư liệu của bạn</label><textarea id="notes" rows="3"></textarea>
      <label>Kịch bản có sẵn (tuỳ chọn) – dán văn bản, hoặc JSON theo mẫu trong thư mục <code>examples/</code>. Có kịch bản thì bỏ qua bước tìm tư liệu + Claude viết.</label>
      <textarea id="own" rows="6" placeholder="# Chương 1&#10;Đoạn lời đọc..."></textarea>
    </details>
    ${hasClaude ? "" : `<div class="warn"><b>Chưa kết nối Claude.</b> Cách dễ nhất: cài <b>Claude Code</b> và đăng nhập tài khoản Claude của bạn (không cần API key) – xem trang <a href="#/settings">Claude / API key</a>.<br><b>Hoặc làm tay:</b> Tool vẫn tự tìm tư liệu, sau đó đưa bạn một <b>lời nhắc</b> để dán vào
      <a href="https://claude.ai" target="_blank" rel="noopener">claude.ai</a> (dùng gói Claude bạn đang có). Dán kết quả trả về vào ô trên trang dự án là tool chạy tiếp
      giọng đọc → hình → dựng video. Muốn tự động hoàn toàn thì thêm <b>ANTHROPIC_API_KEY</b> ở trang <a href="#/settings">API key</a>.</div>`}
    <div class="cols" style="margin-top:6px">
      <div><label>Giọng đọc</label><select id="backend"><option value="">Theo cấu hình (VieNeu – miễn phí)</option><option value="vieneu">VieNeu (máy bạn)</option>
        <option value="google">Google Chirp 3 HD</option><option value="elevenlabs">ElevenLabs</option><option value="edge">Edge TTS</option></select></div>
      <div><label>Kiểu hình</label><select id="look"><option value="">Theo preset</option><option value="collage">Cắt dán tư liệu</option>
        <option value="dark">Tối (crime doc)</option><option value="noir_red">Tối đỏ</option><option value="vintage">Phim cũ</option>
        <option value="deep_blue">Xanh đại dương</option><option value="bright">Sáng</option></select></div>
    </div>
    <label style="display:flex;gap:8px;align-items:center;color:var(--text);margin-top:14px"><input type="checkbox" id="runall" checked> Chạy luôn toàn bộ: giọng đọc → hình ảnh → dựng video → kiểm tra</label>
    <div class="row" style="margin-top:16px"><button class="btn primary" id="go">Tạo video</button><span class="sub" style="margin:0">Video 10 phút mất khoảng 15–40 phút tuỳ máy.</span></div>
    </div>`;
  const extra = () => {
    const p = presets.find(x => x.id === cur) || {};
    $("#minutes").value = p.minutes || 10;
    $("#extra").innerHTML =
      cur === "housing_finance_2d" ? `<div class="cols"><div><label>Quốc gia</label><input type="text" id="country" value="${esc(p.project.country || "")}"></div>
        <div><label>Tiền tệ</label><input type="text" id="currency" value="${esc(p.project.currency || "")}"></div>
        <div><label>Thời điểm dữ liệu</label><input type="text" id="data_date" placeholder="vd 2026-10"></div></div>` :
      cur === "mystery_horror" ? `<div class="cols"><div><label>Loại truyện</label><select id="story_type"><option value="fiction">Hư cấu tự viết</option>
        <option value="legend">Truyền thuyết đô thị</option><option value="real_event">Sự kiện có thật</option></select></div></div>` :
      cur === "crime_doc" ? `<div class="cols"><div><label>Từ khoá tiếng Anh (tìm ảnh/báo cũ)</label><input type="text" id="en" placeholder="vd D. B. Cooper hijacking"></div>
        <div><label>Khoảng năm</label><input type="text" id="years" placeholder="vd 1971-1980"></div></div>` : "";
  };
  extra();
  $("#pr").onclick = e => {
    const el = e.target.closest(".preset"); if (!el) return;
    cur = el.dataset.id; app.querySelectorAll(".preset").forEach(x => x.classList.toggle("on", x === el)); extra();
  };
  $("#go").onclick = async () => {
    const v = id => $("#" + id)?.value ?? "";
    const body = {
      topic: v("topic").trim(), preset: cur, minutes: v("minutes"), language: v("language"), audience: v("audience"),
      country: v("country"), currency: v("currency"), data_date: v("data_date"), story_type: v("story_type"), en: v("en"), years: v("years"),
      urls: v("urls"), notes: v("notes"), own_script: v("own"), run_all: $("#runall").checked,
      options: { backend: v("backend"), look: v("look") },
    };
    if (!body.topic) return toast("Nhập chủ đề trước đã");
    $("#go").disabled = true;
    try { const r = await api("/api/projects", { method: "POST", body: JSON.stringify(body) }); location.hash = "#/p/" + r.slug; }
    catch (e) { toast(e.message, 6000); $("#go").disabled = false; }
  };
}

// ---------------------------------------------------------------- một dự án
let P = null, tab = "video";
async function viewProject(slug) {
  P = await api("/api/projects/" + slug);
  if (!presets.length) presets = await api("/api/presets").catch(() => []);
  const st = P.status;
  app.innerHTML = `
    <div class="row"><div class="grow"><a href="#/">← Dự án</a><h1 style="margin-top:6px">${esc(P.title)}</h1>
      <div class="sub" style="margin-bottom:8px"><span class="pill">${esc(PRESET_NAME[P.preset] || P.preset)}</span>
      ${P.scenes ? `<span class="pill">${P.scenes} cảnh</span>` : ""}${P.duration ? `<span class="pill">${fmtDur(P.duration)}</span>` : ""}
      <span class="pill">${esc(P.slug)}</span></div></div>
      <button class="btn primary" id="all">▶ Chạy các bước còn thiếu</button><button class="btn" id="stop">■ Dừng</button>
      ${P.status.script && !P.meta?.translated_from ? `<button class="btn" id="tr" title="Dịch kịch bản sang tiếng Anh, dùng lại hình, đọc giọng tiếng Anh và dựng video riêng">🌐 Tạo bản tiếng Anh</button>` : ""}
      <button class="btn" id="del" title="Xoá hẳn dự án này">🗑 Xoá</button></div>
    <div class="pipeline">${STEPS.map(([k, name, hint], i) => `
      <div class="stepbox ${st[k] ? "done" : ""}" title="${esc(hint)}"><div class="h"><span>${i + 1}. ${name}</span><span class="st">${st[k] ? "✓" : "○"}</span></div>
      ${k === "voice" ? `<select id="o_backend"><option value="">VieNeu (mặc định)</option><option value="google">Google</option><option value="elevenlabs">ElevenLabs</option><option value="edge">Edge</option></select>` : ""}
      ${k === "render" ? `<select id="o_look"><option value="">Kiểu theo preset</option><option value="collage">Cắt dán</option><option value="dark">Tối</option><option value="noir_red">Tối đỏ</option><option value="vintage">Phim cũ</option><option value="deep_blue">Đại dương</option><option value="bright">Sáng</option></select>
        <label style="display:flex;gap:6px;margin:0 0 6px;align-items:center"><input type="checkbox" id="o_preview"> chỉ xem thử</label>` : ""}
      <button class="btn small" data-step="${k}">${st[k] ? "Làm lại" : "Chạy"}</button></div>`).join("")}</div>
    <div id="manual"></div>
    <h2>Nhật ký <span class="sub" id="jobl" style="font-size:12px"></span></h2><div class="log" id="log"></div>
    <div class="tabs">${[["video", "Video"], ["sb", "Storyboard & sửa cảnh"], ["report", "Báo cáo kiểm tra"], ["yt", "Đăng YouTube"], ["files", "Tệp xuất"]]
      .map(([k, n]) => `<button data-tab="${k}" class="${tab === k ? "on" : ""}">${n}</button>`).join("")}</div>
    <div id="tab"></div>`;
  const opts = () => ({ backend: $("#o_backend").value, look: $("#o_look").value, preview: $("#o_preview").checked });
  app.querySelectorAll("[data-step]").forEach(b => b.onclick = () => {
    if (b.dataset.step === "script" && !P.has_claude_key) { drawManual(true); return; }
    run([b.dataset.step], opts());
  });
  drawManual(!st.script);
  $("#all").onclick = () => run(["all"], opts(), "Chạy các bước còn thiếu");
  const trb = $("#tr");
  if (trb) trb.onclick = async () => {
    if (!confirm("Tạo bản tiếng Anh: dịch kịch bản, dùng lại hình của bản này, đọc giọng tiếng Anh và dựng video riêng?")) return;
    try { const r = await api(`/api/projects/${slug}/translate`, { method: "POST", body: JSON.stringify({ to: "en", run_all: true }) });
      toast("Đang tạo bản tiếng Anh…"); location.hash = "#/p/" + r.slug; }
    catch (e) { toast(e.message, 6000); }
  };
  $("#del").onclick = async () => {
    if (!confirm(`Xoá hẳn dự án "${P.title}"? (xoá cả giọng đọc, hình, video đã làm – không lấy lại được)`)) return;
    try { await api(`/api/projects/${slug}`, { method: "DELETE" }); toast("Đã xoá"); location.hash = "#/"; }
    catch (e) { toast(e.message, 5000); }
  };
  $("#stop").onclick = async () => { await api(`/api/projects/${slug}/stop`, { method: "POST" }); toast("Đã gửi lệnh dừng"); };
  app.querySelectorAll("[data-tab]").forEach(b => b.onclick = () => { tab = b.dataset.tab; app.querySelectorAll("[data-tab]").forEach(x => x.classList.toggle("on", x === b)); drawTab(); });
  drawTab();
  logOffset = 0; $("#log").textContent = "";
  await pullLog(true);
}
function drawManual(show) {
  const m = $("#manual"); if (!m) return;
  if (!show) { m.innerHTML = ""; return; }
  const hasRes = P.status.research;
  m.innerHTML = `<div class="panel" style="border-color:var(--accent2);margin-top:16px">
    <h2 style="margin-top:0">✍ Viết kịch bản bằng claude.ai <span class="sub" style="font-size:12px">– không cần API key</span></h2>
    ${hasRes ? "" : `<div class="warn">Đang chờ bước 1 (Tư liệu) chạy xong – xem nhật ký bên dưới. Xong là dùng được khung này.</div>`}
    <div style="line-height:1.8"><b>1.</b> <button class="btn small" id="cpPrompt" ${hasRes ? "" : "disabled"}>📋 Sao chép lời nhắc</button>
      <b>2.</b> Mở <a href="https://claude.ai/new" target="_blank" rel="noopener">claude.ai</a>, dán lời nhắc và gửi (dài thì nói "tiếp" để Claude viết nốt các chương).
      <b>3.</b> Sao chép toàn bộ câu trả lời (có thể nhiều lần trả lời, dán nối tiếp nhau) vào ô dưới.</div>
    <textarea id="pasted" rows="7" placeholder='Dán câu trả lời của Claude vào đây (có thể chứa cả chữ và khối json { "title": ..., "chapters": [...] })'></textarea>
    <div class="row" style="margin-top:10px"><button class="btn primary" id="imp">Nhập kịch bản</button>
      <label style="display:flex;gap:6px;margin:0;align-items:center;color:var(--text)"><input type="checkbox" id="impAll" checked> rồi chạy tiếp: giọng đọc → hình → dựng video → kiểm tra</label></div>
    <details style="margin-top:8px"><summary style="cursor:pointer;color:var(--info);font-size:12px">Xem lời nhắc</summary><pre class="yt" id="promptView" style="max-height:260px;overflow:auto"></pre></details></div>`;
  let cache = "";
  const getPrompt = async () => { if (!cache) cache = (await api(`/api/projects/${P.slug}/prompt`)).prompt; return cache; };
  $("#cpPrompt").onclick = async () => {
    try { const t = await getPrompt(); $("#promptView").textContent = t;
      try { await navigator.clipboard.writeText(t); toast("Đã sao chép lời nhắc – dán vào claude.ai"); }
      catch (e) { toast("Trình duyệt chặn sao chép – mở mục 'Xem lời nhắc' và tự bôi đen sao chép", 6000); }
    } catch (e) { toast(e.message, 6000); }
  };
  m.querySelector("details").ontoggle = async e => { if (e.target.open && hasRes) { try { $("#promptView").textContent = await getPrompt(); } catch (x) { $("#promptView").textContent = x.message; } } };
  $("#imp").onclick = async () => {
    const text = $("#pasted").value.trim(); if (!text) return toast("Dán câu trả lời của Claude vào ô trước");
    try {
      const r = await api(`/api/projects/${P.slug}/script-json`, { method: "POST", body: JSON.stringify({ text, run_all: $("#impAll").checked }) });
      toast(`Đã nhận ${r.chapters} chương, ${r.scenes} cảnh – đang chạy tiếp`); logOffset = 0; $("#log").textContent = ""; pullLog(true);
    } catch (e) { toast(e.message, 7000); }
  };
}
async function run(steps, options, label) {
  try { await api(`/api/projects/${P.slug}/run`, { method: "POST", body: JSON.stringify({ steps, options, label }) }); toast("Đã bắt đầu: " + (label || steps.join(", "))); logOffset = 0; $("#log").textContent = ""; pullLog(true); }
  catch (e) { toast(e.message, 5000); }
}
async function pullLog(start) {
  const r = await api(`/api/projects/${P.slug}/log?from=${logOffset}`);
  const el = $("#log"); if (!el) return;
  if (r.text) { const atEnd = el.scrollTop + el.clientHeight >= el.scrollHeight - 30; el.textContent += r.text; if (atEnd || start) el.scrollTop = el.scrollHeight; }
  logOffset = r.offset;
  $("#jobl").textContent = r.running ? `● đang chạy: ${r.label} ${r.step ? "(" + r.step + ")" : ""}` : r.label ? (r.ok ? `✓ xong: ${r.label}` : r.ok === false ? `✗ lỗi: ${r.label}` : "") : "";
  if (!el.textContent) el.textContent = "Chưa chạy gì. Bấm một bước ở trên để bắt đầu.";
  if (r.running && !poll) poll = setInterval(() => pullLog(), 1200);
  if (!r.running && poll) { clearInterval(poll); poll = null; if (!start) { toast(r.ok ? "Xong!" : "Có lỗi – xem nhật ký"); const keep = el.textContent; await viewProject(P.slug); $("#log").textContent = keep; $("#log").scrollTop = 1e9; } }
}
function drawTab() {
  const t = $("#tab");
  if (tab === "video") {
    t.innerHTML = P.video ? `<video controls preload="metadata" src="${P.video}"></video>
      <div class="dl" style="margin-top:10px"><a class="btn small" href="${P.video.split("?")[0]}?dl=1">⬇ Tải MP4</a>
      ${P.outputs["subtitles.srt"] ? `<a class="btn small" href="${P.outputs["subtitles.srt"].url}?dl=1">⬇ Phụ đề .srt</a>` : ""}
      ${P.outputs["thumbnail.jpg"] ? `<a class="btn small" href="${P.outputs["thumbnail.jpg"].url}?dl=1">⬇ Thumbnail</a>` : ""}</div>`
      : `<div class="empty">Chưa có video. Chạy đủ các bước 1 → 5 ở trên (hoặc bấm "Chạy các bước còn thiếu").</div>`;
  } else if (tab === "sb") drawStoryboard(t);
  else if (tab === "report") t.innerHTML = P.report ? `<div class="panel report">${md(P.report)}</div>` : `<div class="empty">Chưa có báo cáo – chạy bước "Kiểm tra".</div>`;
  else if (tab === "yt") t.innerHTML = P.youtube ? `<button class="btn small" id="cp">Sao chép</button><pre class="yt">${esc(P.youtube)}</pre>` : `<div class="empty">Chưa có – dựng video xong sẽ có tiêu đề, mô tả, mốc chương.</div>`;
  else if (tab === "files") t.innerHTML = `<div class="panel dl">${Object.values(P.outputs).map(o => `<a class="btn small" href="${o.url}" target="_blank">${esc(o.label)}</a>`).join("") || "Chưa có tệp nào."}</div>`;
  const cp = $("#cp"); if (cp) cp.onclick = () => { navigator.clipboard.writeText(P.youtube); toast("Đã sao chép"); };
}
function md(s) {
  return s.split("\n").map(l => l.startsWith("## ") ? `<h3>${esc(l.slice(3))}</h3>` : l.startsWith("# ") ? `<h2>${esc(l.slice(2))}</h2>`
    : l.startsWith("- ") ? `<li>${esc(l.slice(2))}</li>` : l.trim() ? `<p>${esc(l).replace(/\*\*(.*?)\*\*/g, "<b>$1</b>")}</p>` : "").join("");
}
function drawStoryboard(t) {
  if (!P.chapters.length) { t.innerHTML = `<div class="empty">Chưa có kịch bản – chạy bước "Kịch bản".</div>`; return; }
  t.innerHTML = `<div class="sub">Sửa lời đọc, hiệu ứng, cảm xúc của từng cảnh. "Lưu & dựng lại" chỉ làm lại cảnh đó (đọc lại / tìm hình nếu cần) rồi ghép video – phần khác lấy từ bộ nhớ đệm.</div>` +
    P.chapters.map((c, ci) => `<div class="chapter-h">Chương ${ci + 1}: ${esc(c.title)}</div>` + c.scenes.map(sceneCard).join("")).join("");
  t.querySelectorAll(".scene").forEach(el => {
    el.querySelector("[data-save]").onclick = () => saveScene(el, false);
    el.querySelector("[data-rebuild]").onclick = () => saveScene(el, true);
  });
}
function sceneCard(s) {
  const ch = s.character || {};
  const isChar = ["character", "insert"].includes(s.visual_type);
  return `<div class="scene" data-sid="${s.id}">
    <div><div class="thumb" style="${s._thumb ? `background-image:url('${s._thumb}')` : ""}">${s._thumb ? "" : (s.visual_type === "diagram" || s.visual_type === "chart" ? "📊" : "🖼")}</div>
      ${s._audio_url ? `<audio controls preload="none" src="${s._audio_url}" style="width:100%;margin-top:6px;height:30px"></audio>` : ""}
      <div class="meta">${s.id}${s._time ? " · " + fmtDur(s._time[0]) + " (" + s._time[1].toFixed(1) + "s)" : ""}${s.locked ? " · 🔒 khoá" : ""}</div></div>
    <div><label style="margin-top:0">Lời đọc ${esc(s.purpose ? "· " + s.purpose : "")}</label>
      <textarea data-f="narration" rows="3">${esc(s.narration)}</textarea>
      <div class="fields">
        <div><label>Loại hình</label>${sel("visual_type", s.visual_type, OPT.visual_type)}</div>
        <div><label>Hiệu ứng</label>${sel("fx", s.fx || "auto", OPT.fx, LABEL.fx)}</div>
        <div><label>Ánh sáng</label>${sel("mood", s.mood || "auto", OPT.mood, LABEL.mood)}</div>
        <div><label>Nhạc</label>${sel("music", s.music || "", OPT.music, LABEL.music)}</div>
        <div><label>Camera</label>${sel("camera", s.camera || "auto", OPT.camera)}</div>
        <div><label>Lặng sau câu (giây)</label><input type="number" step="0.1" min="0" max="5" data-f="pause_after" value="${s.pause_after || 0}"></div>
      </div>
      <label>Cụm từ nhấn mạnh (nguyên văn trong lời đọc, cách nhau bằng dấu |)</label>
      <input type="text" data-f="emphasis" value="${esc((s.emphasis || []).join(" | "))}">
      <details ${isChar ? "open" : ""}><summary>Nhân vật 2D · chữ trên hình · mô tả ảnh</summary>
        <div class="fields">
          <div><label>Biểu cảm</label>${sel("c.expression", ch.expression || "", OPT.expression)}</div>
          <div><label>Tư thế</label>${sel("c.pose", ch.pose || "", OPT.pose)}</div>
          <div><label>Khung</label>${sel("c.framing", ch.framing || "auto", OPT.framing)}</div>
        </div>
        <label>Bong bóng suy nghĩ</label><input type="text" data-f="c.thought" value="${esc(ch.thought || "")}">
        <label>Giọng nói trong đầu (bóng đen)</label><input type="text" data-f="c.shadow" value="${esc(ch.shadow || "")}">
        <label>Chữ trên hình (ngày / địa điểm)</label><input type="text" data-f="on_screen_text" value="${esc(s.on_screen_text || "")}">
        <label>Bộ đếm góc màn hình (vd SỐ DƯ 2.400$)</label><input type="text" data-f="hud" value="${esc(s.hud || "")}">
        <label>Mô tả hình (tiếng Anh, dùng để tìm/tạo ảnh)</label><textarea data-f="image_prompt_en" rows="2">${esc(s.image_prompt_en || "")}</textarea>
      </details>
      <div class="row" style="margin-top:10px"><button class="btn small" data-save>Lưu</button><button class="btn small primary" data-rebuild>Lưu & dựng lại</button>
        <label style="display:flex;gap:6px;margin:0;align-items:center"><input type="checkbox" data-f="locked" ${s.locked ? "checked" : ""}> khoá cảnh (giữ ảnh/giọng)</label></div>
    </div></div>`;
}
async function saveScene(el, rebuild) {
  const sid = el.dataset.sid, body = { character: {} };
  el.querySelectorAll("[data-f]").forEach(f => {
    let v = f.type === "checkbox" ? f.checked : f.value;
    const k = f.dataset.f;
    if (k === "emphasis") v = v.split("|").map(x => x.trim()).filter(Boolean);
    if (k === "locked") v = v ? true : null;
    if (k.startsWith("c.")) body.character[k.slice(2)] = v; else body[k] = v;
  });
  try {
    const r = await api(`/api/projects/${P.slug}/scenes/${sid}`, { method: "PATCH", body: JSON.stringify(body) });
    toast(`Đã lưu ${sid}` + (r.need.voice ? " · cần đọc lại" : "") + (r.need.media ? " · cần ảnh mới" : ""));
    if (rebuild) { await api(`/api/projects/${P.slug}/scenes/${sid}/rebuild`, { method: "POST" }); logOffset = 0; $("#log").textContent = ""; pullLog(true); scrollTo({ top: 0, behavior: "smooth" }); }
  } catch (e) { toast(e.message, 5000); }
}

// ---------------------------------------------------------------- API key
async function viewSettings() {
  envKeys = await api("/api/env");
  const cc = await api("/api/claude-code").catch(() => ({ installed: false }));
  app.innerHTML = `<h1>Claude & API key</h1>
    <div class="panel" style="border-color:${cc.installed ? "rgba(61,214,140,.45)" : "var(--accent2)"}">
      <h2 style="margin-top:0">Claude Code – dùng gói Claude của bạn, không cần API key ${cc.installed ? `<span class="pill ok">✓ đã cài</span>` : `<span class="pill">chưa cài</span>`}</h2>
      ${cc.installed ? `<div class="sub" style="margin-bottom:8px">Tool sẽ tự gọi Claude Code để viết kịch bản (tính vào gói Pro/Max). Lần đầu cần đăng nhập.</div>
        <div class="row"><button class="btn small" id="cctest">Kiểm tra đăng nhập</button><span id="ccres" class="sub" style="margin:0"></span></div>`
      : `<div style="line-height:1.8">
        <b>1.</b> Bấm phím Windows, gõ <b>PowerShell</b>, mở lên rồi dán lệnh này (cài Claude Code chính chủ của Anthropic):<br>
        <code style="font-size:13px;user-select:all">irm https://claude.ai/install.ps1 | iex</code><br>
        <b>2.</b> Cài xong, mở <b>cmd mới</b>, gõ <code>claude</code> → chọn đăng nhập bằng <b>tài khoản Claude (Claude.ai subscription)</b> → làm theo trên trình duyệt → gõ <code>/exit</code> để thoát.<br>
        <b>3.</b> Tắt cửa sổ đen của tool rồi bấm đúp <code>start_ui.bat</code> lại. Trang này sẽ hiện "✓ đã cài".</div>`}
    </div>
    <h2>API key (tuỳ chọn)</h2><div class="sub">Lưu vào file <code>.env</code> trên máy bạn (không đẩy lên GitHub). Không key nào bắt buộc – mỗi key mở thêm một chức năng.
      Đã dùng Claude Code thì <b>không cần</b> ANTHROPIC_API_KEY.</div>
    <div class="panel"><table class="keys">${envKeys.map(k => `<tr>
      <td style="width:220px"><b>${k.key}</b><br><span class="sub" style="font-size:12px">${esc(k.price)}</span></td>
      <td>${esc(k.desc)}<br><a href="https://${k.where}" target="_blank" rel="noopener" style="font-size:12px">${esc(k.where)}</a></td>
      <td style="width:110px">${k.set ? `<span class="pill ok">✓ đã có</span>` : `<span class="pill">chưa có</span>`}</td>
      <td style="width:280px"><input type="password" autocomplete="off" data-key="${k.key}" placeholder="${k.set ? "nhập để thay key mới" : "dán key vào đây"}"></td>
      <td style="width:60px">${k.set ? `<button class="btn small" data-clear="${k.key}">Xoá</button>` : ""}</td></tr>`).join("")}</table>
    <div class="row" style="margin-top:14px"><button class="btn primary" id="save">Lưu key</button></div></div>`;
  const ct = $("#cctest");
  if (ct) ct.onclick = async () => {
    $("#ccres").textContent = "Đang hỏi thử Claude…"; ct.disabled = true;
    const r = await api("/api/claude-code?test=1").catch(e => ({ ok: false, message: e.message }));
    $("#ccres").innerHTML = r.ok ? `<span style="color:var(--ok)">✓ Đã đăng nhập, dùng được</span>`
      : `<span style="color:var(--accent2)">Chưa dùng được: ${esc(r.message || "")} – mở cmd, gõ <code>claude</code> để đăng nhập.</span>`;
    ct.disabled = false;
  };
  $("#save").onclick = async () => {
    const body = {}; app.querySelectorAll("[data-key]").forEach(i => { if (i.value.trim()) body[i.dataset.key] = i.value.trim(); });
    await api("/api/env", { method: "POST", body: JSON.stringify(body) }); toast("Đã lưu"); viewSettings();
  };
  app.querySelectorAll("[data-clear]").forEach(b => b.onclick = async () => {
    await api("/api/env", { method: "POST", body: JSON.stringify({ [b.dataset.clear]: "__clear__" }) }); toast("Đã xoá"); viewSettings();
  });
}

function viewHelp() {
  app.innerHTML = `<h1>Hướng dẫn nhanh</h1><div class="panel" style="line-height:1.7">
    <b>1.</b> Vào <a href="#/settings">API key</a> điền key (ít nhất Anthropic để Claude viết kịch bản; Pexels, Pixabay miễn phí để có thêm video).<br>
    <b>2.</b> <a href="#/new">Tạo video mới</a>: chọn phong cách, nhập chủ đề, bấm "Tạo video". Nhật ký hiện trực tiếp từng bước.<br>
    <b>3.</b> Xong thì xem video ở tab <b>Video</b>. Cảnh nào chưa ưng: tab <b>Storyboard</b> → sửa lời đọc / hiệu ứng / cảm xúc → "Lưu & dựng lại".<br>
    <b>4.</b> Tab <b>Báo cáo kiểm tra</b>: các lỗi cần sửa trước khi đăng. Tab <b>Đăng YouTube</b>: tiêu đề, mô tả, mốc chương, nguồn ảnh.<br>
    <b>5.</b> Muốn chỉnh tay: bước 7 xuất bản nháp CapCut.<br><br>
    Hiệu ứng mỗi cảnh: <b>rùng mình</b> (cảnh man rợ), <b>hành động</b> (truy đuổi, nổ súng), <b>chấn động</b>, <b>tiết lộ</b>, <b>nhiễu</b>. Nhạc: bỏ file có bản quyền vào
    <code>assets/music/&lt;buồn|căng thẳng…&gt;</code> theo tên tiếng Anh: sad, tense, hopeful, calm, action, horror.<br>
    Dòng lệnh vẫn dùng được như cũ: <code>python studio.py --help</code>.</div>`;
}

// ---------------------------------------------------------------- phiên bản & cập nhật
async function checkVersion(force) {
  const el = $("#ver"); if (!el) return;
  try {
    const v = await api("/api/version" + (force ? "?force=1" : ""));
    if (!v.git) { el.innerHTML = `<div style="margin-bottom:8px">Bản tải ZIP – muốn cập nhật bằng 1 nút thì cài bằng git clone</div>`; return; }
    el.innerHTML = `<div style="margin-bottom:8px">Phiên bản <code>${esc(v.commit)}</code> · ${esc(v.date || "")}<br>
      ${v.behind ? `<button class="btn small primary" id="upd" style="margin-top:6px">⬆ Có ${v.behind} bản cập nhật – cập nhật ngay</button>`
        : `<a href="#" id="upd" style="font-size:12px">Kiểm tra cập nhật</a>`}</div>`;
    $("#upd").onclick = async e => {
      e.preventDefault();
      if (!v.behind) { toast("Đang kiểm tra…"); return checkVersion(true).then(() => toast("Đã kiểm tra")); }
      if (!confirm("Tải bản mới từ GitHub và cập nhật tool?")) return;
      toast("Đang cập nhật…", 60000);
      try {
        const r = await api("/api/update", { method: "POST" });
        toast(r.changed ? "Cập nhật xong" : "Đang là bản mới nhất", 2500);
        alert(r.changed ? "Đã cập nhật xong:\n\n" + (r.log || r.output) + "\nTắt cửa sổ đen rồi bấm đúp start_ui.bat để chạy bản mới."
          : "Đang là bản mới nhất.");
        checkVersion(true);
      } catch (x) { toast("Cập nhật lỗi", 2500); alert("Cập nhật lỗi: " + x.message); }
    };
  } catch (e) { el.textContent = ""; }
}
checkVersion();
setInterval(checkVersion, 15 * 60 * 1000);
route();
