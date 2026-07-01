// Renders the Receita tab from /api/charts/receita payload.
window.renderReceita = function (p) {
  const C = window.Charts;
  const money = (v) => "R$" + Number(v).toLocaleString("pt-BR", { maximumFractionDigits: 0 });

  // Vertical bar coloured per-category (mirrors the Plotly discrete palette).
  const catBar = (id, d, opts = {}) => {
    if (!d) { C.render(id, { series: [] }); return; }
    C.render(id, {
      ...C.base(),
      legend: { show: false },
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" },
                 valueFormatter: opts.money ? money : undefined },
      grid: { left: 48, right: 20, top: 34, bottom: 90, containLabel: true },
      xAxis: { type: "category", data: d.categories, ...C.axisStyle,
               axisLabel: { color: "#9a9ab0", interval: 0, rotate: 25, width: 90, overflow: "truncate" } },
      yAxis: { type: "value", name: opts.yname || "", ...C.axisStyle },
      series: [{
        type: "bar", data: d.values, barMaxWidth: 46,
        itemStyle: { color: (pt) => C.PALETTE[pt.dataIndex % C.PALETTE.length], borderRadius: [4, 4, 0, 0] },
      }],
    });
  };

  catBar("r-evento", p.receita_evento, { yname: "Receita (BRL)", money: true });
  catBar("r-categoria", p.receita_categoria, { yname: "Receita (BRL)", money: true });
  catBar("r-gratuito", p.ingressos_gratuitos, { yname: "Ingressos" });
  catBar("r-pagamento", p.receita_pagamento, { yname: "Receita (BRL)", money: true });

  // Donut — Gratuitos vs Pagos
  if (p.gratuito_pago) {
    const g = p.gratuito_pago;
    C.render("r-tipo", {
      ...C.base(),
      tooltip: { trigger: "item" },
      legend: { bottom: 0, textStyle: { color: "#9a9ab0" } },
      series: [{
        type: "pie", radius: ["45%", "70%"], center: ["50%", "45%"],
        data: g.labels.map((n, i) => ({ name: n, value: g.values[i] })),
        label: { color: "#c9c9d6", formatter: "{b}\n{d}%" },
        itemStyle: { borderColor: "#0b0d12", borderWidth: 2 },
      }],
    });
  }

  // Area — Receita diária (single-event só)
  const el = document.getElementById("r-diaria-card");
  if (p.receita_diaria) {
    if (el) el.style.display = "";
    const d = p.receita_diaria;
    C.render("r-diaria", {
      ...C.base(),
      tooltip: { trigger: "axis", valueFormatter: money },
      xAxis: { type: "category", data: d.dates, boundaryGap: false, ...C.axisStyle },
      yAxis: { type: "value", name: "Receita (BRL)", ...C.axisStyle },
      series: [{
        type: "line", data: d.values, smooth: true, showSymbol: false,
        areaStyle: { opacity: 0.25 }, lineStyle: { width: 2, color: C.PALETTE[0] },
        itemStyle: { color: C.PALETTE[0] },
      }],
    });
  } else if (el) {
    el.style.display = "none";
  }
};
