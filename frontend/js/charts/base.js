// Shared ECharts setup: dark palette, instance registry, common option base.
window.Charts = (function () {
  const PALETTE = [
    "#636EFA", "#EF553B", "#00CC96", "#AB63FA", "#FFA15A",
    "#19D3F3", "#FF6692", "#B6E880", "#FF97FF", "#FECB52",
  ];
  const HL = "#FF7F0E";
  const MUTE = "#AAAAAA";

  const registry = {}; // domId -> echarts instance

  function inst(id) {
    const el = document.getElementById(id);
    if (!el) return null;
    if (!registry[id]) registry[id] = echarts.init(el, null, { renderer: "canvas" });
    return registry[id];
  }

  function render(id, option) {
    const chart = inst(id);
    if (!chart) return;
    chart.setOption(option, true);
  }

  function clearAll() {
    Object.values(registry).forEach((c) => c.clear());
  }

  function resizeAll() {
    Object.values(registry).forEach((c) => c.resize());
  }
  window.addEventListener("resize", resizeAll);

  function base() {
    return {
      color: PALETTE,
      textStyle: { color: "#c9c9d6", fontFamily: "Inter, system-ui, sans-serif" },
      grid: { left: 48, right: 20, top: 34, bottom: 60, containLabel: true },
      tooltip: { trigger: "axis", backgroundColor: "#1a1f2b", borderColor: "#2a2a3a",
                 textStyle: { color: "#e8e8f0" } },
      legend: { bottom: 0, textStyle: { color: "#9a9ab0" }, type: "scroll" },
      animationDuration: 600,
      animationEasing: "cubicOut",
    };
  }

  const axisStyle = {
    axisLine: { lineStyle: { color: "#2a2a3a" } },
    axisLabel: { color: "#9a9ab0" },
    splitLine: { lineStyle: { color: "rgba(42,42,58,.5)" } },
  };

  return { PALETTE, HL, MUTE, inst, render, clearAll, resizeAll, base, axisStyle };
})();
