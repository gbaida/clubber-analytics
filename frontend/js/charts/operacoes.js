// Renders the Operações tab from /api/charts/operacoes payload.
window.renderOperacoes = function (p) {
  const C = window.Charts;

  // 1 — Comparecimento por Evento (stacked: Pago/Gratuito × Presente/Ausente)
  if (p.comparecimento) {
    const d = p.comparecimento;
    C.render("o-comparecimento", {
      ...C.base(),
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      legend: { bottom: 0, textStyle: { color: "#9a9ab0" }, type: "scroll" },
      grid: { left: 48, right: 20, top: 34, bottom: 90, containLabel: true },
      xAxis: { type: "category", data: d.categories, ...C.axisStyle,
               axisLabel: { color: "#9a9ab0", interval: 0, rotate: 25, width: 90, overflow: "truncate" } },
      yAxis: { type: "value", name: "Ingressos", ...C.axisStyle },
      series: d.series.map((s) => ({
        name: s.name, type: "bar", stack: s.stack, data: s.data, barMaxWidth: 46,
        itemStyle: { color: s.color },
      })),
    });
  }

  // 2 — Taxa de Cancelamento por Evento (bar)
  if (p.cancelamento) {
    const d = p.cancelamento;
    C.render("o-cancelamento", {
      ...C.base(),
      legend: { show: false },
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" },
                 valueFormatter: (v) => v + "%" },
      grid: { left: 48, right: 20, top: 34, bottom: 90, containLabel: true },
      xAxis: { type: "category", data: d.categories, ...C.axisStyle,
               axisLabel: { color: "#9a9ab0", interval: 0, rotate: 25, width: 90, overflow: "truncate" } },
      yAxis: { type: "value", name: "Cancelamento (%)", ...C.axisStyle },
      series: [{ type: "bar", data: d.values, barMaxWidth: 46,
                 itemStyle: { color: C.PALETTE[1], borderRadius: [4, 4, 0, 0] },
                 label: { show: true, position: "top", color: "#9a9ab0", formatter: "{c}%" } }],
    });
  }

  // 3 — Distribuição por Status de Ingresso (bar)
  if (p.status) {
    const d = p.status;
    C.render("o-status", {
      ...C.base(),
      legend: { show: false },
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      grid: { left: 48, right: 20, top: 34, bottom: 40, containLabel: true },
      xAxis: { type: "category", data: d.categories, ...C.axisStyle },
      yAxis: { type: "value", name: "Ingressos", ...C.axisStyle },
      series: [{ type: "bar", data: d.values, barMaxWidth: 60,
                 itemStyle: { color: (pt) => C.PALETTE[pt.dataIndex % C.PALETTE.length],
                              borderRadius: [4, 4, 0, 0] },
                 label: { show: true, position: "top", color: "#9a9ab0" } }],
    });
  }

  // 4 — Mix de Categorias por Evento (stacked)
  if (p.mix_categoria) {
    const d = p.mix_categoria;
    C.render("o-mix", {
      ...C.base(),
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      grid: { left: 48, right: 20, top: 34, bottom: 90, containLabel: true },
      xAxis: { type: "category", data: d.categories, ...C.axisStyle,
               axisLabel: { color: "#9a9ab0", interval: 0, rotate: 25, width: 90, overflow: "truncate" } },
      yAxis: { type: "value", name: "Ingressos", ...C.axisStyle },
      series: d.series.map((s) => ({ name: s.name, type: "bar", stack: "mix",
                                     data: s.data, barMaxWidth: 46 })),
    });
  }
};
