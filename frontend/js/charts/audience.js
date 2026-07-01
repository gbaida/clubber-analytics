// Renders the Público tab from /api/charts/audience payload.
window.renderAudience = function (p) {
  const C = window.Charts;

  const donut = (id, d) => {
    if (!d) return;
    C.render(id, {
      ...C.base(),
      tooltip: { trigger: "item" },
      legend: { bottom: 0, textStyle: { color: "#9a9ab0" } },
      series: [{
        type: "pie", radius: ["45%", "70%"], center: ["50%", "45%"],
        data: d.labels.map((n, i) => ({ name: n, value: d.values[i] })),
        label: { color: "#c9c9d6", formatter: "{b}\n{d}%" },
        itemStyle: { borderColor: "#0b0d12", borderWidth: 2 },
      }],
    });
  };

  const hbar = (id, d, color) => {
    if (!d) return;
    C.render(id, {
      ...C.base(),
      legend: { show: false },
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      grid: { left: 120, right: 30, top: 34, bottom: 40, containLabel: true },
      xAxis: { type: "value", name: "Participantes", ...C.axisStyle },
      yAxis: { type: "category", data: d.categories, ...C.axisStyle,
               axisLabel: { color: "#9a9ab0", width: 110, overflow: "truncate" } },
      series: [{
        type: "bar", data: d.values, barMaxWidth: 22,
        itemStyle: { color: color || C.PALETTE[0], borderRadius: [0, 3, 3, 0] },
        label: { show: true, position: "right", color: "#9a9ab0" },
      }],
    });
  };

  // 1 — Gênero (donut)
  donut("a-genero", p.genero);

  // 2 — Distribuição de Idade (histograma)
  if (p.idade) {
    C.render("a-idade", {
      ...C.base(),
      legend: { show: false },
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      grid: { left: 48, right: 20, top: 34, bottom: 40, containLabel: true },
      xAxis: { type: "category", data: p.idade.ages, name: "Idade", nameLocation: "middle",
               nameGap: 28, ...C.axisStyle, axisLabel: { color: "#9a9ab0", interval: 4 } },
      yAxis: { type: "value", name: "Participantes", ...C.axisStyle },
      series: [{ type: "bar", data: p.idade.values, barCategoryGap: "8%",
                 itemStyle: { color: "#636EFA" } }],
    });
  }

  // 3 — Top 15 Cidades (horizontal bar)
  hbar("a-cidades", p.cidades, C.PALETTE[0]);

  // 4 — Newsletter (donut)
  donut("a-newsletter", p.newsletter);

  // 5 — Participantes Recorrentes (multi só, vertical bar)
  const recCard = document.getElementById("a-recorrentes-card");
  if (p.recorrentes) {
    if (recCard) recCard.style.display = "";
    const d = p.recorrentes;
    C.render("a-recorrentes", {
      ...C.base(),
      legend: { show: false },
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      grid: { left: 48, right: 20, top: 34, bottom: 50, containLabel: true },
      xAxis: { type: "category", data: d.categories, ...C.axisStyle },
      yAxis: { type: "value", name: "Participantes", ...C.axisStyle },
      series: [{ type: "bar", data: d.values, barMaxWidth: 46,
                 itemStyle: { color: C.PALETTE[2], borderRadius: [4, 4, 0, 0] },
                 label: { show: true, position: "top", color: "#9a9ab0" } }],
    });
  } else if (recCard) {
    recCard.style.display = "none";
  }

  // 6 — Top 10 Mais Fiéis (multi só, horizontal bar)
  const topCard = document.getElementById("a-top-card");
  if (p.top_fieis) {
    if (topCard) topCard.style.display = "";
    hbar("a-top", { ...p.top_fieis }, C.PALETTE[3]);
  } else if (topCard) {
    topCard.style.display = "none";
  }

  // 7 — Distribuição de Idade por Gênero (overlay)
  if (p.idade_genero) {
    const d = p.idade_genero;
    C.render("a-idade-genero", {
      ...C.base(),
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      grid: { left: 48, right: 20, top: 34, bottom: 50, containLabel: true },
      xAxis: { type: "category", data: d.ages, name: "Idade", nameLocation: "middle",
               nameGap: 28, ...C.axisStyle, axisLabel: { color: "#9a9ab0", interval: 4 } },
      yAxis: { type: "value", name: "Participantes", ...C.axisStyle },
      series: d.series.map((s, i) => ({
        name: s.name, type: "bar", stack: "idade", data: s.data,
        itemStyle: { color: C.PALETTE[i % C.PALETTE.length], opacity: 0.8 },
      })),
    });
  }
};
