// Renders the Marketing tab from /api/charts/marketing payload.
window.renderMarketing = function (p) {
  const C = window.Charts;

  // 1 — Ingressos por Canal de Aquisição (horizontal bar)
  if (p.canal_aquisicao) {
    const d = p.canal_aquisicao;
    C.render("m-canal", {
      ...C.base(),
      legend: { show: false },
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      grid: { left: 90, right: 30, top: 34, bottom: 40, containLabel: true },
      xAxis: { type: "value", name: "Ingressos", ...C.axisStyle },
      yAxis: { type: "category", data: d.categories, ...C.axisStyle },
      series: [{
        type: "bar", data: d.values, barMaxWidth: 24,
        itemStyle: { color: (pt) => C.PALETTE[pt.dataIndex % C.PALETTE.length], borderRadius: [0, 3, 3, 0] },
        label: { show: true, position: "right", color: "#9a9ab0" },
      }],
    });
  }

  // 2 — Canal × Meio (stacked)
  if (p.canal_meio) {
    const d = p.canal_meio;
    C.render("m-canal-meio", {
      ...C.base(),
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      grid: { left: 48, right: 20, top: 34, bottom: 70, containLabel: true },
      xAxis: { type: "category", data: d.categories, ...C.axisStyle,
               axisLabel: { color: "#9a9ab0", interval: 0, rotate: 20 } },
      yAxis: { type: "value", name: "Ingressos", ...C.axisStyle },
      series: d.series.map((s) => ({
        name: s.name, type: "bar", stack: "meio", data: s.data, barMaxWidth: 46,
      })),
    });
  }

  // 3 — Performance por Canal e Evento (grouped, multi só)
  const el = document.getElementById("m-canal-evento-card");
  if (p.canal_evento) {
    if (el) el.style.display = "";
    const d = p.canal_evento;
    C.render("m-canal-evento", {
      ...C.base(),
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      grid: { left: 48, right: 20, top: 34, bottom: 90, containLabel: true },
      xAxis: { type: "category", data: d.categories, ...C.axisStyle,
               axisLabel: { color: "#9a9ab0", interval: 0, rotate: 25, width: 90, overflow: "truncate" } },
      yAxis: { type: "value", name: "Ingressos", ...C.axisStyle },
      series: d.series.map((s) => ({ name: s.name, type: "bar", data: s.data, barMaxWidth: 26 })),
    });
  } else if (el) {
    el.style.display = "none";
  }
};
