async function api(url, options = {}) {
  const headers = { "X-Requested-With": "XMLHttpRequest", ...options.headers };
  if (options.body && !(options.body instanceof FormData)) headers["Content-Type"] = "application/json";
  const response = await fetch(url, { ...options, headers });
  if (!response.ok) {
    let message = `İstek başarısız (${response.status}).`;
    try { const data = await response.json(); if (typeof data.detail === "string") message = data.detail; } catch (_) { /* Non-JSON response. */ }
    throw new Error(message);
  }
  return response.json();
}
function escapeHtml(value) {
  const node = document.createElement("span");
  node.textContent = String(value ?? "");
  return node.innerHTML.replaceAll('"', "&quot;").replaceAll("'", "&#39;");
}
let toastTimer;
function toast(message) {
  const element = document.getElementById("toast");
  element.textContent = message;
  element.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => element.classList.add("hidden"), 5000);
}
async function copyText(text) {
  if (!navigator.clipboard || !window.isSecureContext) throw new Error("Kopyalama için HTTPS gereklidir; listeyi elle seçip kopyalayabilirsiniz.");
  await navigator.clipboard.writeText(text);
  toast("Liste kopyalandı.");
}
