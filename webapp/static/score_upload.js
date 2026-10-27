(() => {
  "use strict";

  const dropzone = document.getElementById("score-dropzone");
  const input = document.getElementById("score-input");
  if (!dropzone || !input) return;

  const filename = document.getElementById("score-filename");
  const message = document.getElementById("score-file-feedback");
  const prompt = dropzone.dataset.prompt || "Choose a PDF or score image.";
  const allowed = input.accept.split(",").map((extension) => extension.trim().toLowerCase());
  const maximumBytes = 20 * 1024 * 1024;

  function clearDisplay() {
    filename.textContent = "";
    filename.hidden = true;
  }

  function clearSelection() {
    input.value = "";
    clearDisplay();
  }

  function report(text, isError = false) {
    message.textContent = text;
    message.dataset.state = isError ? "error" : "ok";
  }

  function acceptFile(file) {
    if (!file) return false;
    const dot = file.name.lastIndexOf(".");
    const extension = dot >= 0 ? file.name.slice(dot).toLowerCase() : "";
    if (!allowed.includes(extension)) {
      clearSelection();
      report(dropzone.dataset.invalid, true);
      return false;
    }
    if (file.size > maximumBytes) {
      clearSelection();
      report(dropzone.dataset.tooLarge, true);
      return false;
    }
    filename.textContent = file.name;
    filename.hidden = false;
    report(dropzone.dataset.selected || "File selected.");
    return true;
  }

  input.addEventListener("change", () => {
    const selected = input.files?.[0];
    clearDisplay();
    if (selected) acceptFile(selected);
  });

  dropzone.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      input.click();
    }
  });

  for (const eventName of ["dragenter", "dragover"]) {
    dropzone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropzone.classList.add("dragover");
    });
  }

  for (const eventName of ["dragleave", "drop"]) {
    dropzone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropzone.classList.remove("dragover");
    });
  }

  dropzone.addEventListener("drop", (event) => {
    const file = event.dataTransfer?.files?.[0];
    if (!file) {
      clearSelection();
      report(dropzone.dataset.invalid, true);
      return;
    }
    if (!acceptFile(file)) return;
    try {
      const transfer = new DataTransfer();
      transfer.items.add(file);
      input.files = transfer.files;
    } catch (_error) {
      try { input.files = event.dataTransfer.files; } catch (_ignored) { /* report below */ }
    }
    if (!input.files?.length || input.files[0].name !== file.name) {
      clearSelection();
      report(dropzone.dataset.failed, true);
      return;
    }
    input.dispatchEvent(new Event("change", { bubbles: true }));
  });
})();
