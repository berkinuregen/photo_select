let currentId = null;
let uploading = false;
let editing = false;
const list = document.getElementById("gallery-list");
const detail = document.getElementById("detail");
const createForm = document.getElementById("create-form");
document.getElementById("new-toggle").onclick = () => createForm.classList.toggle("hidden");
document.getElementById("logout").onclick = async () => {
  try { await api("/api/logout", { method: "POST" }); location.href = "/admin"; }
  catch (error) { toast(error.message); }
};
createForm.onsubmit = async event => {
  event.preventDefault();
  const data = new FormData(createForm);
  try {
    const gallery = await api("/api/admin/galleries", { method: "POST", body: JSON.stringify({
      title: data.get("title"), description: data.get("description"), selection_limit: Number(data.get("selection_limit"))
    }) });
    createForm.reset(); createForm.classList.add("hidden"); currentId = gallery.id;
    await refresh();
  } catch (error) { toast(error.message); }
};
async function refreshList() {
  const galleries = await api("/api/admin/galleries");
  document.getElementById("gallery-count").textContent = `(${galleries.length})`;
  list.innerHTML = galleries.length ? galleries.map(g => `<button class="gallery-item ${g.id === currentId ? "active" : ""}" data-id="${g.id}">
    <span class="block font-medium">${escapeHtml(g.title)}</span>
    <span class="block text-xs text-stone-400 mt-2">${g.photo_count} fotoğraf · ${g.selected_count}/${g.selection_limit} seçildi</span>
    <span class="block text-xs text-stone-500 mt-1">${g.submitted_at ? "Seçim iletildi" : g.published ? "Yayında" : "Taslak"}</span></button>`).join("") : '<p class="muted">Henüz galeri yok.</p>';
  list.querySelectorAll("[data-id]").forEach(button => button.onclick = async () => {
    currentId = Number(button.dataset.id);
    try { await refresh(); } catch (error) { toast(error.message); }
  });
}
async function refreshDetail() {
  if (!currentId) return;
  const requestedId = currentId;
  const { gallery: g, photos } = await api(`/api/admin/galleries/${requestedId}`);
  if (currentId !== requestedId) return;
  const selected = photos.filter(p => p.selected);
  const url = `${location.origin}/galeri/${g.token}`;
  detail.innerHTML = `<div class="panel">
    <div class="flex flex-wrap justify-between gap-4"><div><p class="eyebrow">${g.submitted_at ? "SEÇİM İLETİLDİ" : g.published ? "YAYINDA" : "TASLAK"}</p><h2 class="text-2xl mt-2">${escapeHtml(g.title)}</h2><p class="muted mt-2">${escapeHtml(g.description)}</p></div>
    <button id="publish" class="button self-start">${g.published ? "Yayından kaldır" : "Yayınla"}</button></div>
    <div class="mt-6"><label class="text-xs text-stone-400" for="gallery-url">Özel galeri bağlantısı</label><div class="flex gap-2 mt-2"><input id="gallery-url" class="input" value="${escapeHtml(url)}" readonly><button id="copy-link" class="button">Kopyala</button></div></div>
    <p class="text-xs text-stone-500 mt-2">Bağlantıya sahip olan herkes galeriye erişebilir. Yalnızca müşterinizle paylaşın.</p>
    <div id="drop-zone" class="empty mt-6 ${g.submitted_at ? "hidden" : ""}"><p>JPG / PNG fotoğrafları buraya sürükleyin</p><p class="text-xs mt-2">Her dosya en fazla 30 MB · Tek tek yüklenir</p><label class="button mt-4">Dosya seç<input id="file-input" type="file" accept=".jpg,.jpeg,.png,image/jpeg,image/png" multiple class="hidden"></label><p id="upload-status" class="text-xs mt-3"></p></div>
    <div class="mt-8"><div class="flex flex-wrap items-center justify-between gap-3"><h3 class="text-lg">Seçimler <span class="text-stone-400">${selected.length} / ${g.selection_limit}</span></h3><button id="copy-names" class="button text-sm" ${selected.length ? "" : "disabled"}>Dosya adlarını kopyala</button></div>
    <textarea id="names" class="input mt-3 text-sm" rows="3" readonly aria-label="Seçilen dosya adları"></textarea><p class="text-xs text-stone-500 mt-2">Lightroom için virgülle ayrılmış dosya adları. Notlar aşağıda gösterilir.</p></div>
    <div class="photo-grid mt-8">${photos.map(p => `<article><div class="photo-frame"><img src="/api/admin/galleries/${g.id}/photos/${p.id}/preview" loading="lazy" decoding="async" alt="${escapeHtml(p.filename)}">${p.selected ? '<span class="photo-toggle selected flex items-center justify-center" aria-label="Seçildi">✓</span>' : ""}</div><p class="text-xs mt-2 break-all">${escapeHtml(p.filename)}</p>${p.note ? `<p class="text-xs text-stone-400 mt-1 whitespace-pre-line">${escapeHtml(p.note)}</p>` : ""}${g.submitted_at ? "" : `<button class="delete-photo text-xs text-red-300 mt-2" data-id="${p.id}">Fotoğrafı sil</button>`}</article>`).join("")}</div>
    ${photos.length ? "" : '<p class="muted mt-6">Bu galeride henüz fotoğraf yok.</p>'}</div>`;
  const names = detail.querySelector("#names");
  names.value = selected.map(p => p.filename).join(", ");
  detail.querySelector("#copy-link").onclick = () => copyText(url).catch(error => toast(error.message));
  detail.querySelector("#copy-names").onclick = () => copyText(names.value).catch(error => toast(error.message));
  detail.querySelector("#publish").onclick = async () => {
    try { await api(`/api/admin/galleries/${g.id}`, { method: "PATCH", body: JSON.stringify({ published: !g.published }) }); await refresh(); }
    catch (error) { toast(error.message); }
  };
  detail.querySelectorAll(".delete-photo").forEach(button => button.onclick = async () => {
    if (!confirm("Bu fotoğraf silinsin mi?")) return;
    try { await api(`/api/admin/galleries/${g.id}/photos/${button.dataset.id}`, { method: "DELETE" }); await refresh(); }
    catch (error) { toast(error.message); }
  });
  const zone = detail.querySelector("#drop-zone");
  zone.ondragover = event => { event.preventDefault(); };
  zone.ondrop = event => { event.preventDefault(); uploadFiles(g.id, event.dataTransfer.files); };
  detail.querySelector("#file-input").onchange = event => uploadFiles(g.id, event.target.files);
}
async function uploadFiles(id, fileList) {
  if (uploading) return;
  const files = Array.from(fileList);
  if (!files.length) return;
  uploading = true;
  let failures = [];
  try {
    for (let i = 0; i < files.length; i++) {
      const status = document.getElementById("upload-status");
      if (status) status.textContent = `Yükleniyor: ${i + 1} / ${files.length}`;
      const form = new FormData(); form.append("file", files[i]);
      try { await api(`/api/admin/galleries/${id}/photos`, { method: "POST", body: form }); }
      catch (error) { failures.push(`${files[i].name}: ${error.message}`); }
    }
    await refresh();
    toast(failures.length ? `Bazı dosyalar yüklenemedi:\n${failures.join("\n")}` : `${files.length} fotoğraf yüklendi.`);
  } catch (error) { toast(error.message); }
  finally { uploading = false; }
}
async function refresh() { await refreshList(); await refreshDetail(); }
detail.addEventListener("focusin", event => { if (event.target.id === "names" || event.target.id === "gallery-url") editing = true; });
detail.addEventListener("focusout", () => { editing = false; });
refresh().catch(error => toast(error.message));
setInterval(() => { if (!uploading && !editing && !document.hidden) refresh().catch(error => toast(error.message)); }, 10000);
