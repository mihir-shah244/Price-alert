document.addEventListener("DOMContentLoaded", () => {
  const canvas = document.getElementById("priceChart");
  if (!canvas) return;

  const productId = canvas.dataset.productId;
  const targetPrice = parseFloat(canvas.dataset.targetPrice);

  fetch(`/products/${productId}/history`)
    .then((res) => res.json())
    .then((points) => {
      const labels = points.map((p) => new Date(p.checked_at).toLocaleString());
      const prices = points.map((p) => p.price);

      new Chart(canvas, {
        type: "line",
        data: {
          labels,
          datasets: [
            {
              label: "Price",
              data: prices,
              borderColor: "#3b82f6",
              tension: 0.2,
            },
            {
              label: "Target price",
              data: prices.map(() => targetPrice),
              borderColor: "#ef4444",
              borderDash: [6, 4],
              pointRadius: 0,
            },
          ],
        },
        options: {
          responsive: true,
          scales: { y: { beginAtZero: false } },
        },
      });
    });
});
