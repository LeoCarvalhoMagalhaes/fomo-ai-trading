import { ColorType, createChart, IChartApi, LineStyle, UTCTimestamp } from "lightweight-charts";
import { useEffect, useRef } from "react";

export interface ChartCandle {
  t: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  ema20: number | null;
  ema50: number | null;
  bb_up: number | null;
  bb_low: number | null;
}

interface Level {
  price: number;
  label: string;
  color: string;
}

function cssColor(name: string): string {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return `rgb(${v.split(" ").join(",")})`;
}

export function PriceChart({ candles, levels = [], height = 380 }: { candles: ChartCandle[]; levels?: Level[]; height?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = createChart(ref.current, {
      height,
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: cssColor("--mute") },
      grid: { vertLines: { color: cssColor("--line") }, horzLines: { color: cssColor("--line") } },
      rightPriceScale: { borderColor: cssColor("--line") },
      timeScale: { borderColor: cssColor("--line"), timeVisible: true },
      localization: { priceFormatter: (p: number) => (p < 1 ? p.toPrecision(4) : p.toFixed(4)) },
      autoSize: true,
    });
    chartRef.current = chart;
    const series = chart.addCandlestickSeries({
      upColor: cssColor("--up"), downColor: cssColor("--down"), borderVisible: false,
      wickUpColor: cssColor("--up"), wickDownColor: cssColor("--down"),
      priceFormat: { type: "price", precision: 10, minMove: 1e-10 },
    });
    series.setData(candles.map((c) => ({ time: c.t as UTCTimestamp, open: c.open, high: c.high, low: c.low, close: c.close })));
    const line = (key: keyof ChartCandle, color: string, style = LineStyle.Solid) => {
      const s = chart.addLineSeries({ color, lineWidth: 1, lineStyle: style, priceLineVisible: false, lastValueVisible: false,
                                      priceFormat: { type: "price", precision: 10, minMove: 1e-10 } });
      s.setData(candles.filter((c) => c[key] !== null).map((c) => ({ time: c.t as UTCTimestamp, value: c[key] as number })));
    };
    line("ema20", cssColor("--info"));
    line("ema50", cssColor("--warn"));
    line("bb_up", cssColor("--mute"), LineStyle.Dotted);
    line("bb_low", cssColor("--mute"), LineStyle.Dotted);
    const vol = chart.addHistogramSeries({ priceScaleId: "vol", priceFormat: { type: "volume" }, color: cssColor("--line") });
    chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    vol.setData(candles.map((c) => ({ time: c.t as UTCTimestamp, value: c.volume })));
    levels.forEach((l) => series.createPriceLine({ price: l.price, color: l.color, lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: l.label }));
    chart.timeScale().fitContent();
    return () => {
      chart.remove();
      chartRef.current = null;
    };
  }, [candles, levels, height]);

  return <div ref={ref} style={{ height }} />;
}
