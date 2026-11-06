const token = document.getElementById("gallery").dataset.token;
const base = `/api/galeri/${encodeURIComponent(token)}`;
let gallery, photos = [], currentIndex = 0, busy = false;
const grid = document.getElementById("photos");
const lightbox = document.getElementById("lightbox");
const submit = document.getElementById("submit");

function isLocked() { return Boolean(gallery?.submitted_at); }
function setBusy(value) {
  busy = value;
  document.querySelectorAll(".selection-control").forEach(control => { control.disabled = value || isLocked(); });
  document.getElementById("lightbox-select").disabled = value || isLocked();
  submit.disabled = value || isLocked() || !photos.some(photo => photo.selected);
}
function counter() {
  const count = photos.filter(photo => photo.selected).length;
  document.getElementById("counter").textContent = isLocked() ? `Seçim İletildi · ${count} / ${gallery.selection_limit}` : `Seçilen: ${count} / ${gallery.selection_limit}`;
  submit.textContent = isLocked() ? "Seçim iletildi ✓" : "Seçimi tamamla →";
  setBusy(busy);
}
function render() {
  document.getElementById("title").textContent = gallery.title;
  document.getElementById("description").textContent = gallery.description;
  grid.innerHTML = photos.length ? photos.map(photo => `<article>
    <div class="photo-frame">
      <button class="open-photo w-full h-full" data-id="${photo.id}" aria-label="${escapeHtml(photo.filename)} fotoğrafını büyüt">
        <img src="${base}/photos/${photo.id}/preview" loading="lazy" decoding="async" alt="${escapeHtml(photo.filename)}">
      </button>
      <button class="photo-toggle selection-control ${photo.selected ? "selected" : ""}" data-id="${photo.id}" aria-label="${photo.selected ? "Seçimi kaldır" : "Fotoğrafı seç"}" aria-pressed="${Boolean(photo.selected)}">${photo.selected ? "✓" : "♡"}</button>
    </div>
    <p class="text-xs mt-2 text-stone-300 break-all">${escapeHtml(photo.filename)}</p>
    <label class="block text-xs text-stone-500 mt-3">Fotoğraf için not
      <textarea class="input selection-control note mt-1 text-xs" rows="2" maxlength="500" data-id="${photo.id}" placeholder="İsteğe bağlı">${escapeHtml(photo.note)}</textarea>
    </label></article>`).join("") : '<p class="muted">Henüz fotoğraf eklenmedi.</p>';
  grid.querySelectorAll(".open-photo").forEach(button => button.onclick = () => {
    currentIndex = photos.findIndex(photo => photo.id === Number(button.dataset.id));
    lightbox.classList.remove("hidden"); document.body.style.overflow = "hidden"; renderLightbox();
    document.getElementById("lightbox-close").focus();
  });
  grid.querySelectorAll(".photo-toggle").forEach(button => button.onclick = () => {
    const photo = photos.find(item => item.id === Number(button.dataset.id));
    savePhoto(photo, !photo.selected, photo.note);
  });
  grid.querySelectorAll(".note").forEach(input => input.onchange = () => {
    const photo = photos.find(item => item.id === Number(input.dataset.id));
    savePhoto(photo, Boolean(photo.selected), input.value);
  });
  counter();
  if (!lightbox.classList.contains("hidden")) renderLightbox();
}
async function load() {
  const data = await api(base);
  gallery = data.gallery; photos = data.photos;
  render();
}
async function savePhoto(photo, selected, note) {
  if (busy || isLocked()) return;
  setBusy(true);
  try {
    await api(`${base}/photos/${photo.id}`, { method: "PUT", body: JSON.stringify({ selected: Boolean(selected), note }) });
    photo.selected = selected; photo.note = note.trim();
    render();
  } catch (error) {
    toast(error.message);
    try { await load(); } catch (loadError) { toast(loadError.message); }
  } finally { setBusy(false); }
}
submit.onclick = async () => {
  if (busy || isLocked() || !confirm("Seçimlerinizi fotoğrafçınıza iletmek istediğinize emin misiniz?")) return;
  setBusy(true);
  try { await api(`${base}/submit`, { method: "POST" }); await load(); }
  catch (error) { toast(error.message); try { await load(); } catch (loadError) { toast(loadError.message); } }
  finally { setBusy(false); }
};
function renderLightbox() {
  const photo = photos[currentIndex];
  if (!photo) return;
  const image = document.getElementById("lightbox-image");
  image.src = `${base}/photos/${photo.id}/preview`; image.alt = photo.filename;
  document.getElementById("lightbox-name").textContent = `${currentIndex + 1} / ${photos.length} · ${photo.filename}`;
  const button = document.getElementById("lightbox-select");
  button.textContent = photo.selected ? "✓ Seçildi" : "♡ Seç";
  button.disabled = busy || isLocked();
  button.onclick = () => savePhoto(photo, !photo.selected, photo.note);
}
function closeLightbox() { lightbox.classList.add("hidden"); document.body.style.overflow = ""; }
function move(delta) { if (photos.length) { currentIndex = (currentIndex + delta + photos.length) % photos.length; renderLightbox(); } }
document.getElementById("lightbox-close").onclick = closeLightbox;
document.getElementById("lightbox-prev").onclick = () => move(-1);
document.getElementById("lightbox-next").onclick = () => move(1);
document.addEventListener("keydown", event => {
  if (lightbox.classList.contains("hidden")) return;
  if (event.key === "Escape") closeLightbox();
  if (event.key === "ArrowLeft") move(-1);
  if (event.key === "ArrowRight") move(1);
});
let touchX = null;
lightbox.addEventListener("touchstart", event => { touchX = event.changedTouches[0].clientX; }, { passive: true });
lightbox.addEventListener("touchend", event => {
  if (touchX === null) return;
  const distance = event.changedTouches[0].clientX - touchX;
  if (Math.abs(distance) > 50) move(distance < 0 ? 1 : -1);
  touchX = null;
}, { passive: true });
load().catch(error => { document.getElementById("title").textContent = "Galeri yüklenemedi."; toast(error.message); });
