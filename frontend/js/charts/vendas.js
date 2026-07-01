// Renders the 6 Vendas visuals from /api/charts/vendas payload.
window.renderVendas = function (p) {
  const C = window.Charts;
  const money = (v) => "R$" + Number(v).toLocaleString("pt-BR", { minimumFractionDigits: 2 });

  // 1 — Vendas diárias por evento (bar)
  if (p.diarias) {
    const d = p.diarias;
    C.render("v-diarias", {
      ...C.base(),
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      xAxis: { type: d.multi ? "value" : "category", name: d.x_label, nameLocation: "middle",
               nameGap: 32, inverse: !!d.reversed, ...C.axisStyle },
      yAxis: { type: "value", name: "Ingressos", ...C.axisStyle },
      series: d.series.map((s) => ({
        name: s.name, type: "bar", stack: d.multi ? undefined : "x",
        data: s.data, barMaxWidth: 28, itemStyle: { borderRadius: [3, 3, 0, 0] },
      })),
    });
  }

  // 2 — Vendas acumuladas (line)
  if (p.acumulado) {
    const d = p.acumulado;
    C.render("v-acumulado", {
      ...C.base(),
      xAxis: { type: d.multi ? "value" : "category", name: d.x_label, nameLocation: "middle",
               nameGap: 32, inverse: !!d.reversed, ...C.axisStyle },
      yAxis: { type: "value", name: "Acumulado", ...C.axisStyle },
      series: d.series.map((s) => ({
        name: s.name, type: "line", smooth: true, showSymbol: false,
        data: s.data, lineStyle: { width: 2 },
      })),
    });
  }

  // 3 — Vendas por dia da semana (bar)
  if (p.dia_semana) {
    C.render("v-dow", {
      ...C.base(),
      legend: { show: false },
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      xAxis: { type: "category", data: p.dia_semana.categories, ...C.axisStyle },
      yAxis: { type: "value", name: "Ingressos", ...C.axisStyle },
      series: [{ type: "bar", data: p.dia_semana.data, barMaxWidth: 40,
                 itemStyle: { color: C.PALETTE[0], borderRadius: [4, 4, 0, 0] } }],
    });
  }

  // 4 — Quando compraram (bar, x reversed → event day 0 on the right)
  if (p.quando_compraram) {
    const q = p.quando_compraram;
    C.render("v-quando", {
      ...C.base(),
      legend: { show: false },
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      xAxis: { type: "value", name: q.x_label, nameLocation: "middle", nameGap: 32,
               inverse: !!q.reversed, ...C.axisStyle },
      yAxis: { type: "value", name: "Ingressos", ...C.axisStyle },
      series: [{ type: "bar", data: q.data, barMaxWidth: 22,
                 itemStyle: { color: C.PALETTE[2] } }],
    });
  }

  // 5 — Heatmap dia × hora
  if (p.heatmap) {
    const h = p.heatmap;
    const maxV = h.data.reduce((m, d) => Math.max(m, d[2]), 0) || 1;
    C.render("v-heat", {
      ...C.base(),
      legend: { show: false },
      grid: { left: 50, right: 20, top: 20, bottom: 60, containLabel: true },
      tooltip: { position: "top" },
      xAxis: { type: "category", data: h.hours.map(String), name: "Hora", ...C.axisStyle, splitArea: { show: false } },
      yAxis: { type: "category", data: h.dows, ...C.axisStyle, splitArea: { show: false } },
      visualMap: { min: 0, max: maxV, calculable: true, orient: "horizontal",
                   left: "center", bottom: 4, inRange: { color: ["#0e1117", "#1f3a5f", "#3b7dd8", "#7fb8ff"] },
                   textStyle: { color: "#9a9ab0" } },
      series: [{ type: "heatmap", data: h.data,
                 label: { show: true, color: "#cdd6e6", fontSize: 9 },
                 emphasis: { itemStyle: { shadowBlur: 8, shadowColor: "rgba(0,0,0,.5)" } } }],
    });
  }

  // 6 — Resumo por evento (table)
  const tbody = document.getElementById("v-resumo-body");
  if (tbody) {
    tbody.innerHTML = "";
    (p.resumo || []).forEach((r) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${r["Evento"]}</td>
        <td>${r["Total"].toLocaleString("pt-BR")}</td>
        <td>${r["Válidos"].toLocaleString("pt-BR")}</td>
        <td>${r["Cancelados"].toLocaleString("pt-BR")}</td>
        <td>${r["Comparecimento"].toLocaleString("pt-BR")}</td>
        <td>${money(r["Receita"])}</td>
        <td>${r["Dias de Venda"] ?? "—"}</td>
        <td>${r["Taxa de Comparecimento"]}%</td>
        <td>${r["Taxa de Cancelamento"]}%</td>`;
      tbody.appendChild(tr);
    });
  }
};
