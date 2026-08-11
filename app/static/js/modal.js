document.addEventListener("DOMContentLoaded", () => {
  const backdrop = document.querySelector("[data-modal]");
  if (!backdrop) return;

  const openBtn = document.querySelector("[data-open-modal]");
  const closeEls = document.querySelectorAll("[data-close-modal]");
  const form = backdrop.querySelector("[data-track-form]");
  const preview = backdrop.querySelector("[data-fetch-preview]");

  function close() {
    backdrop.hidden = true;
    form?.reset();
    if (preview) preview.hidden = true;
  }

  openBtn?.addEventListener("click", () => {
    backdrop.hidden = false;
  });

  closeEls.forEach((el) => el.addEventListener("click", close));

  backdrop.addEventListener("click", (event) => {
    if (event.target === backdrop) close();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !backdrop.hidden) close();
  });

  initFetchDetails();
});

function guessCurrencySymbol(url) {
  try {
    const host = new URL(url).hostname.toLowerCase();
    return host.endsWith(".in") || host.includes("flipkart") ? "₹" : "$";
  } catch {
    return "₹";
  }
}

function initFetchDetails() {
  const form = document.querySelector("[data-track-form]");
  if (!form) return;

  const urlInput = form.querySelector("[data-url-input]");
  const titleInput = form.querySelector("[data-title-input]");
  const fetchBtn = form.querySelector("[data-fetch-details]");
  const preview = form.querySelector("[data-fetch-preview]");
  const previewThumb = form.querySelector("[data-fetch-preview-thumb]");
  const previewStatus = form.querySelector("[data-fetch-preview-status]");
  const previewTitle = form.querySelector("[data-fetch-preview-title]");
  const previewPrice = form.querySelector("[data-fetch-preview-price]");
  const prefetchedUrl = form.querySelector("[data-prefetched-url]");
  const prefetchedPrice = form.querySelector("[data-prefetched-price]");
  const prefetchedOriginalPrice = form.querySelector("[data-prefetched-original-price]");
  const prefetchedImageUrl = form.querySelector("[data-prefetched-image-url]");

  function clearPrefetched() {
    prefetchedUrl.value = "";
    prefetchedPrice.value = "";
    prefetchedOriginalPrice.value = "";
    prefetchedImageUrl.value = "";
  }

  // The preview goes stale the moment the URL changes underneath it, so the
  // create endpoint must fall back to its own scrape instead of trusting it.
  urlInput?.addEventListener("input", () => {
    preview.hidden = true;
    clearPrefetched();
  });

  fetchBtn?.addEventListener("click", async () => {
    const url = urlInput.value.trim();
    if (!url) {
      urlInput.reportValidity();
      return;
    }

    fetchBtn.disabled = true;
    fetchBtn.textContent = "Parsing...";
    preview.hidden = false;
    previewThumb.innerHTML = '<span class="thumb-placeholder">&#128247;</span>';
    previewStatus.className = "fetch-preview-status";
    previewStatus.textContent = "";
    previewTitle.textContent = "";
    previewPrice.textContent = "";
    clearPrefetched();

    try {
      const res = await fetch("/products/fetch-details", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({ url }),
      });
      const data = await res.json();

      if (data.ok) {
        const symbol = guessCurrencySymbol(url);
        previewStatus.classList.add("fetch-preview-status-ok");
        previewStatus.textContent = `${(data.site || "").toUpperCase()} ✓ Scraped Successfully`;
        previewTitle.textContent = data.title || url;
        previewPrice.textContent =
          data.price != null
            ? `Live Price: ${symbol}${Number(data.price).toLocaleString()}`
            : "Live price unavailable";
        if (data.image_url) {
          const img = document.createElement("img");
          img.src = data.image_url;
          img.alt = "";
          previewThumb.replaceChildren(img);
        }
        if (titleInput && !titleInput.value.trim() && data.title) {
          titleInput.value = data.title;
        }
        prefetchedUrl.value = url;
        prefetchedPrice.value = data.price ?? "";
        prefetchedOriginalPrice.value = data.original_price ?? "";
        prefetchedImageUrl.value = data.image_url ?? "";
      } else {
        previewStatus.classList.add("fetch-preview-status-error");
        previewStatus.textContent = `⚠ ${data.error || "Could not fetch details"}`;
      }
    } catch {
      previewStatus.classList.add("fetch-preview-status-error");
      previewStatus.textContent = "⚠ Could not reach the server";
    } finally {
      fetchBtn.disabled = false;
      fetchBtn.innerHTML = "&#10024; Fetch Details";
    }
  });
}
