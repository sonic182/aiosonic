document.addEventListener("DOMContentLoaded", () => {
  const button = document.querySelector("[data-markdown-url]");
  if (!button) return;
  const status = button.parentElement.querySelector('[role="status"]');
  button.addEventListener("click", async () => {
    button.disabled = true;
    status.textContent = "Loading Markdown…";
    try {
      const response = await fetch(button.dataset.markdownUrl);
      if (!response.ok) throw new Error("Markdown unavailable");
      const markdown = await response.text();
      if (!navigator.clipboard || !window.isSecureContext) {
        throw new Error("Clipboard unavailable");
      }
      await navigator.clipboard.writeText(markdown);
      status.textContent = "Markdown copied.";
    } catch (error) {
      status.textContent = "Could not copy. Use Download Markdown or allow clipboard access.";
    } finally {
      button.disabled = false;
    }
  });
});
