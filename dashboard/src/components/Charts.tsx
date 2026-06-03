interface AreaTrendProps {
  values: number[];
  values2?: number[];
  height?: number;
}

export function AreaTrend({ values, values2, height = 200 }: AreaTrendProps) {
  const w = 720,
    h = height,
    padX = 8,
    padT = 12,
    padB = 28;
  const max = Math.max(...values, ...(values2 ?? [0]));
  const stepX = (w - padX * 2) / (values.length - 1);
  const yFor = (v: number) => padT + (1 - v / max) * (h - padT - padB);
  const toPath = (arr: number[]) =>
    arr.map((v, i) => `${i === 0 ? 'M' : 'L'} ${padX + i * stepX} ${yFor(v)}`).join(' ');
  const toArea = (arr: number[]) =>
    `${toPath(arr)} L ${padX + (arr.length - 1) * stepX} ${h - padB} L ${padX} ${h - padB} Z`;
  const ticks = 4;
  const gridY = Array.from(
    { length: ticks },
    (_, i) => padT + (i / (ticks - 1)) * (h - padT - padB)
  );
  const xLabels = ['28d ago', '21d', '14d', '7d', 'today'];
  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      width="100%"
      height={h}
      preserveAspectRatio="none"
      style={{ display: 'block' }}
    >
      <defs>
        <linearGradient id="g-found" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.18" />
          <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
        </linearGradient>
      </defs>
      {gridY.map((y, i) => (
        <line
          key={i}
          x1={padX}
          x2={w - padX}
          y1={y}
          y2={y}
          stroke="var(--line)"
          strokeDasharray="2 4"
        />
      ))}
      {values2 && (
        <path
          d={toPath(values2)}
          stroke="var(--fg-4)"
          strokeWidth="1.5"
          fill="none"
          strokeDasharray="3 3"
        />
      )}
      <path d={toArea(values)} fill="url(#g-found)" />
      <path d={toPath(values)} stroke="var(--accent)" strokeWidth="2" fill="none" />
      {xLabels.map((lbl, i) => {
        const x = padX + (i / (xLabels.length - 1)) * (w - padX * 2);
        return (
          <text
            key={i}
            x={x}
            y={h - 8}
            fontSize="10"
            fill="var(--fg-4)"
            textAnchor="middle"
            fontFamily="var(--font-mono)"
          >
            {lbl}
          </text>
        );
      })}
    </svg>
  );
}

export function Sparkline({
  values,
  width = 80,
  height = 24,
}: {
  values: number[];
  width?: number;
  height?: number;
}) {
  const max = Math.max(...values),
    min = Math.min(...values);
  const stepX = width / (values.length - 1);
  const yFor = (v: number) => (1 - (v - min) / (max - min || 1)) * (height - 4) + 2;
  const d = values.map((v, i) => `${i === 0 ? 'M' : 'L'} ${i * stepX} ${yFor(v)}`).join(' ');
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
      <path
        d={d}
        stroke="var(--accent)"
        strokeWidth="1.5"
        fill="none"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function SeverityBar({
  counts,
  height = 6,
}: {
  counts: Record<string, number>;
  height?: number;
}) {
  const total =
    (counts.critical || 0) + (counts.high || 0) + (counts.medium || 0) + (counts.low || 0);
  if (!total)
    return (
      <div className="sev-bar" style={{ height }}>
        <div style={{ background: 'var(--line-strong)', width: '100%' }} />
      </div>
    );
  const seg = (k: string) => `${((counts[k] || 0) / total) * 100}%`;
  return (
    <div className="sev-bar" style={{ height }}>
      <div style={{ width: seg('critical'), background: 'var(--sev-crit-fg)' }} />
      <div style={{ width: seg('high'), background: 'var(--sev-high-fg)' }} />
      <div style={{ width: seg('medium'), background: 'var(--sev-med-fg)' }} />
      <div style={{ width: seg('low'), background: 'var(--sev-low-fg)' }} />
    </div>
  );
}

export function Donut({ counts, size = 120 }: { counts: Record<string, number>; size?: number }) {
  const data = [
    { k: 'critical', v: counts.critical || 0, c: 'var(--sev-crit-fg)' },
    { k: 'high', v: counts.high || 0, c: 'var(--sev-high-fg)' },
    { k: 'medium', v: counts.medium || 0, c: 'var(--sev-med-fg)' },
    { k: 'low', v: counts.low || 0, c: 'var(--sev-low-fg)' },
  ];
  const total = data.reduce((s, d) => s + d.v, 0);
  const denom = total || 1; // avoid div-by-zero khi vẽ arcs
  const r = size / 2 - 10,
    cx = size / 2,
    cy = size / 2,
    C = 2 * Math.PI * r;
  let acc = 0;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="var(--bg-muted)" strokeWidth="14" />
      {total > 0 &&
        data.map((d, i) => {
          const len = (d.v / denom) * C;
          const dash = `${len} ${C - len}`;
          const offset = -acc;
          acc += len;
          return (
            <circle
              key={i}
              cx={cx}
              cy={cy}
              r={r}
              fill="none"
              stroke={d.c}
              strokeWidth="14"
              strokeDasharray={dash}
              strokeDashoffset={offset}
              transform={`rotate(-90 ${cx} ${cy})`}
            />
          );
        })}
      <text
        x={cx}
        y={cy}
        textAnchor="middle"
        dominantBaseline="middle"
        fontSize="22"
        fontWeight="600"
        fill="var(--fg)"
        fontFamily="var(--font-sans)"
      >
        {total}
      </text>
      <text
        x={cx}
        y={cy + 16}
        textAnchor="middle"
        fontSize="10"
        fill="var(--fg-3)"
        fontFamily="var(--font-sans)"
      >
        issues
      </text>
    </svg>
  );
}

export function Heatmap({ rows = 4, cols = 24 }: { rows?: number; cols?: number }) {
  const cells = Array.from({ length: rows * cols }, (_, i) =>
    Math.abs((Math.sin(i * 12.9898) * 43758.5453) % 1)
  );
  const cellW = 16,
    cellH = 16,
    gap = 3;
  const w = cols * (cellW + gap),
    h = rows * (cellH + gap);
  return (
    <svg width="100%" viewBox={`0 0 ${w} ${h + 18}`} preserveAspectRatio="none">
      {Array.from({ length: rows }).map((_, r) =>
        Array.from({ length: cols }).map((_, c) => {
          const v = cells[r * cols + c];
          return (
            <rect
              key={`${r}-${c}`}
              x={c * (cellW + gap)}
              y={r * (cellH + gap)}
              width={cellW}
              height={cellH}
              rx="2"
              fill="var(--accent)"
              opacity={0.08 + v * 0.85}
            />
          );
        })
      )}
      <text x="0" y={h + 14} fontSize="9.5" fill="var(--fg-4)" fontFamily="var(--font-mono)">
        00:00
      </text>
      <text
        x={w / 2 - 12}
        y={h + 14}
        fontSize="9.5"
        fill="var(--fg-4)"
        fontFamily="var(--font-mono)"
      >
        12:00
      </text>
      <text x={w - 30} y={h + 14} fontSize="9.5" fill="var(--fg-4)" fontFamily="var(--font-mono)">
        23:00
      </text>
    </svg>
  );
}
