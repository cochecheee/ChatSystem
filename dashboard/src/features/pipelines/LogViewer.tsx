import { useEffect, useMemo, useState } from 'react';
import { api } from '../../api/client';
import { Icon } from '../../components/Icon';

// GitHub Actions job logs: mỗi dòng có prefix timestamp ISO, chứa mã màu ANSI
// và marker ##[group]/##[endgroup] (fold theo step), ##[error]/##[warning].
// Viewer strip ANSI, tách timestamp thành cột mờ, dựng section fold được.

// ESC dựng qua fromCharCode — literal control char trong source vướng cả
// no-control-regex lẫn các tool xử lý file.
const ANSI_RE = new RegExp(String.fromCharCode(27) + '\\[[0-9;]*[A-Za-z]', 'g');
const TS_RE = /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})[\d.]*Z?\s?/;
const MAX_RENDER_LINES = 5000;

interface LogLine {
  time: string; // HH:MM:SS ("" nếu dòng không có timestamp)
  text: string;
  kind: 'normal' | 'error' | 'warning' | 'command';
}

interface LogSection {
  title: string | null; // null = dòng ngoài mọi ##[group]
  lines: LogLine[];
}

function parseLine(raw: string): { line: LogLine; group: 'open' | 'close' | null } {
  let text = raw.replace(ANSI_RE, '');
  let time = '';
  const ts = TS_RE.exec(text);
  if (ts) {
    time = ts[1].slice(11); // HH:MM:SS
    text = text.slice(ts[0].length);
  }
  if (text.startsWith('##[group]')) {
    return {
      line: { time, text: text.slice('##[group]'.length), kind: 'command' },
      group: 'open',
    };
  }
  if (text.startsWith('##[endgroup]')) {
    return { line: { time, text: '', kind: 'normal' }, group: 'close' };
  }
  let kind: LogLine['kind'] = 'normal';
  if (text.startsWith('##[error]')) {
    kind = 'error';
    text = text.slice('##[error]'.length);
  } else if (text.startsWith('##[warning]')) {
    kind = 'warning';
    text = text.slice('##[warning]'.length);
  } else if (text.startsWith('##[command]')) {
    kind = 'command';
    text = text.slice('##[command]'.length);
  }
  return { line: { time, text, kind }, group: null };
}

function parseLog(raw: string): { sections: LogSection[]; truncated: number } {
  const allLines = raw.split(/\r?\n/);
  const truncated = Math.max(0, allLines.length - MAX_RENDER_LINES);
  const lines = truncated > 0 ? allLines.slice(-MAX_RENDER_LINES) : allLines;

  const sections: LogSection[] = [];
  let current: LogSection = { title: null, lines: [] };
  for (const rawLine of lines) {
    if (rawLine === '') continue;
    const { line, group } = parseLine(rawLine);
    if (group === 'open') {
      if (current.lines.length > 0) sections.push(current);
      current = { title: line.text, lines: [] };
      continue;
    }
    if (group === 'close') {
      sections.push(current);
      current = { title: null, lines: [] };
      continue;
    }
    current.lines.push(line);
  }
  if (current.title !== null || current.lines.length > 0) sections.push(current);
  return { sections, truncated };
}

const KIND_COLOR: Record<LogLine['kind'], string> = {
  normal: 'var(--fg-2, inherit)',
  error: 'var(--sev-crit-fg, #e53935)',
  warning: 'var(--sev-med-fg, #f9a825)',
  command: 'var(--accent)',
};

function LineRow({ line }: { line: LogLine }) {
  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}>
      <span
        className="mono"
        style={{ fontSize: 10, color: 'var(--fg-4)', flexShrink: 0, userSelect: 'none' }}
      >
        {line.time}
      </span>
      <span
        className="mono"
        style={{
          fontSize: 11,
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-all',
          color: KIND_COLOR[line.kind],
          fontWeight: line.kind === 'error' ? 600 : 400,
        }}
      >
        {line.kind === 'error' ? '✖ ' : ''}
        {line.text}
      </span>
    </div>
  );
}

function Section({
  section,
  forceOpen,
  filter,
}: {
  section: LogSection;
  forceOpen: boolean;
  filter: string;
}) {
  // Section chứa error mở sẵn — đó là thứ người dùng tìm khi CI đỏ.
  const hasError = section.lines.some((l) => l.kind === 'error');
  const [open, setOpen] = useState(hasError);

  const visible = filter
    ? section.lines.filter((l) => l.text.toLowerCase().includes(filter.toLowerCase()))
    : section.lines;
  if (filter && visible.length === 0) return null;

  if (section.title === null) {
    return (
      <div style={{ padding: '2px 0' }}>
        {visible.map((l, i) => (
          <LineRow key={i} line={l} />
        ))}
      </div>
    );
  }

  const isOpen = open || forceOpen || Boolean(filter);
  return (
    <div>
      <div
        onClick={() => setOpen(!open)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 5,
          cursor: 'pointer',
          padding: '3px 0',
          color: hasError ? 'var(--sev-crit-fg, #e53935)' : 'var(--fg-2)',
          fontWeight: 600,
          fontSize: 11,
        }}
      >
        <Icon name={isOpen ? 'chevron_down' : 'chevron_right'} size={10} />
        <span className="mono">{section.title}</span>
        <span className="muted" style={{ fontSize: 10, fontWeight: 400 }}>
          {section.lines.length} lines
        </span>
      </div>
      {isOpen && (
        <div style={{ paddingLeft: 15, borderLeft: '1px solid var(--line)', marginLeft: 4 }}>
          {visible.map((l, i) => (
            <LineRow key={i} line={l} />
          ))}
        </div>
      )}
    </div>
  );
}

export function LogViewer({
  runId,
  jobId,
  projectId,
}: {
  runId: number;
  jobId: number;
  projectId?: number;
}) {
  const [raw, setRaw] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState('');
  const [expandAll, setExpandAll] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setRaw(null);
    setError(null);
    api.github
      .jobLogs(runId, jobId, projectId)
      .then((text) => {
        if (!cancelled) setRaw(text);
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [runId, jobId, projectId]);

  const parsed = useMemo(() => (raw !== null ? parseLog(raw) : null), [raw]);

  if (error) {
    return (
      <div className="muted" style={{ fontSize: 11, padding: '8px 12px' }}>
        {error}
      </div>
    );
  }
  if (parsed === null) {
    return (
      <div className="muted" style={{ fontSize: 11, padding: '8px 12px' }}>
        Loading log…
      </div>
    );
  }

  return (
    <div
      style={{
        background: 'var(--surface-2)',
        border: '1px solid var(--line)',
        borderRadius: 6,
        marginTop: 8,
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '6px 10px',
          borderBottom: '1px solid var(--line)',
        }}
      >
        <Icon name="search" size={11} style={{ color: 'var(--fg-3)', flexShrink: 0 }} />
        <input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter log lines…"
          style={{
            flex: 1,
            background: 'transparent',
            border: 'none',
            outline: 'none',
            color: 'var(--fg-1)',
            fontSize: 11,
          }}
        />
        <button className="btn ghost sm" onClick={() => setExpandAll(!expandAll)}>
          {expandAll ? 'Collapse all' : 'Expand all'}
        </button>
      </div>
      <div style={{ maxHeight: 420, overflowY: 'auto', padding: '6px 10px' }}>
        {parsed.truncated > 0 && (
          <div className="muted" style={{ fontSize: 10, marginBottom: 4 }}>
            … {parsed.truncated} earlier lines hidden (showing last {MAX_RENDER_LINES})
          </div>
        )}
        {parsed.sections.map((s, i) => (
          <Section key={i} section={s} forceOpen={expandAll} filter={filter} />
        ))}
      </div>
    </div>
  );
}
