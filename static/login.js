document.getElementById("login-form").addEventListener("submit", async event => {
  event.preventDefault();
  const button = event.currentTarget.querySelector("button");
  button.disabled = true;
  try {
    await api("/api/login", { method: "POST", body: JSON.stringify({ password: document.getElementById("password").value }) });
    location.href = "/admin";
  } catch (error) { toast(error.message); button.disabled = false; }
});
