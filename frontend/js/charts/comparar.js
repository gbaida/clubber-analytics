// Renders the Comparar tab from /api/charts/comparar payload.
window.renderComparar = function (p) {
  const C = window.Charts;
  const HL = p.colors ? p.colors.hl : C.HL;
  const MUTE = p.colors ? p.colors.mute : C.MUTE;
  const money0 = (v) => "R$" + Number(v).toLocaleString("pt-BR", { maximumFractionDigits: 0 });

  // KPI cards (ref vs média)
  const k = p.kpis;
  const setKpi = (id, val, delta, suffix) => {
    const el = document.getElementById(id);
    if (!el) return;
    const d = delta > 0 ? `+${delta}` : `${delta}`;
    el.querySelector(".value").textContent = val;
    el.querySelector(".delta").textContent = `${d}${suffix} vs média`;
    el.querySelector(".delta").style.color = delta >= 0 ? "#00CC96" : "#EF553B";
  };
  setKpi("ck-ing", k.ingressos.ref.toLocaleString("pt-BR"), k.ingressos.delta, "");
  setKpi("ck-rec", money0(k.receita.ref), Math.round(k.receita.delta), "");
  setKpi("ck-pag", k.pagos.ref + "%", k.pagos.delta, "pp");
  setKpi("ck-cmp", k.comparecimento.ref + "%", k.comparecimento.delta, "pp");

  // helper: bar with ref highlighted
  const hlBar = (id, title, events, values, ref, yname, fmt) =>
    C.render(id, {
      ...C.base(),
      legend: { show: false },
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" },
                 valueFormatter: fmt },
      xAxis: { type: "category", data: events, axisLabel: { color: "#9a9ab0", rotate: 20, interval: 0 },
               axisLine: { lineStyle: { color: "#2a2a3a" } } },
      yAxis: { type: "value", name: yname, ...C.axisStyle },
      series: [{ type: "bar", data: values.map((v, i) => ({
        value: v, itemStyle: { color: events[i] === ref ? HL : MUTE, borderRadius: [4, 4, 0, 0] } })),
        barMaxWidth: 42 }],
    });

  if (p.receita_evento)
    hlBar("c-receita", "Receita por Evento", p.receita_evento.events, p.receita_evento.values,
          p.receita_evento.ref, "Receita (BRL)", (v) => money0(v));
  if (p.ingressos_evento)
    hlBar("c-ingressos", "Ingressos Vendidos por Evento", p.ingressos_evento.events,
          p.ingressos_evento.values, p.ingressos_evento.ref, "Ingressos", (v) => v);

  // Stacked: Primeira Vez vs Recorrente (ref bordered)
  const stacked = (id, title, rows, order, ref, keys, names, colors, yname) => {
    const markRef = order.indexOf(ref);
    C.render(id, {
      ...C.base(),
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      xAxis: { type: "category", data: order, axisLabel: { color: "#9a9ab0", rotate: 20, interval: 0 },
               axisLine: { lineStyle: { color: "#2a2a3a" } } },
      yAxis: { type: "value", name: yname, ...C.axisStyle },
      series: keys.map((key, ki) => ({
        name: names[ki], type: "bar", stack: "s", data: rows.map((r) => r[key]),
        itemStyle: { color: colors[ki] },
        markArea: ki === 0 && markRef >= 0 ? {
          silent: true,
          itemStyle: { color: "transparent", borderColor: HL, borderWidth: 2 },
          data: [[{ xAxis: markRef, yAxis: 0 }, { xAxis: markRef }]],
        } : undefined,
      })),
    });
  };

  if (p.fidelidade)
    stacked("c-fidelidade", "Primeira Vez vs Recorrente por Evento", p.fidelidade.rows,
            p.fidelidade.order, p.fidelidade.ref, ["primeira_vez", "recorrente"],
            ["Primeira Vez", "Recorrente"], [C.PALETTE[4], C.PALETTE[5]], "Participantes");
  if (p.pago_gratuito)
    stacked("c-pagogratuito", "Ingressos: Pago vs Gratuito", p.pago_gratuito.rows,
            p.pago_gratuito.order, p.pago_gratuito.ref, ["pago", "gratuito"],
            ["Pago", "Gratuito"], [C.PALETTE[0], C.PALETTE[2]], "Ingressos");

  // 4 evolution charts — ref (HL) vs others (mute) vs avg (dashed)
  if (p.evolucao) {
    const e = p.evolucao;
    const evoChart = (id, title, block, yname) =>
      C.render(id, {
        ...C.base(),
        legend: { show: true, bottom: 0, data: [block.ref.name, "Média dos outros"],
                  textStyle: { color: "#9a9ab0" } },
        tooltip: { trigger: "axis" },
        xAxis: { type: "value", name: e.x_label, nameLocation: "middle", nameGap: 30,
                 inverse: !!e.reversed, ...C.axisStyle },
        yAxis: { type: "value", name: yname, ...C.axisStyle },
        series: [
          ...block.others.map((o) => ({
            name: o.name, type: "line", data: o.data, showSymbol: false, smooth: true,
            lineStyle: { color: MUTE, width: 1, opacity: 0.4 }, silent: true,
            tooltip: { show: false }, legendHoverLink: false,
          })),
          { name: "Média dos outros", type: "line", data: block.avg, showSymbol: false, smooth: true,
            lineStyle: { color: MUTE, width: 2, type: "dashed" } },
          { name: block.ref.name, type: "line", data: block.ref.data, smooth: true,
            symbol: "circle", symbolSize: 5, lineStyle: { color: HL, width: 3 },
            itemStyle: { color: HL } },
        ],
      });

    evoChart("c-vendas-diaria", "Vendas Diárias: Selecionado vs Outros", e.vendas_diaria, "Ingressos");
    evoChart("c-vendas-acum", "Vendas Acumuladas: Selecionado vs Outros", e.vendas_acum, "Acumulado");
    evoChart("c-receita-diaria", "Receita Diária: Selecionado vs Outros", e.receita_diaria, "Receita (BRL)");
    evoChart("c-receita-acum", "Receita Acumulada: Selecionado vs Outros", e.receita_acum, "Receita (BRL)");
  }
};
