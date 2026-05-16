import { Fragment } from 'react';

/**
 * Tiny markdown renderer — only the subset the AI summary card needs.
 * Supports: **bold**, `inline code`, numbered/bulleted lists, paragraph breaks.
 * Deliberately ~50 lines so we don't ship a 30 KB markdown library just for
 * this card.
 */
export function MiniMarkdown({ text }: { text: string }) {
  if (!text) return null;
  const lines = text.split(/\r?\n/);
  const blocks: React.ReactNode[] = [];
  let listBuffer: { ordered: boolean; items: string[] } | null = null;

  const flushList = (key: number) => {
    if (!listBuffer) return;
    const Tag = listBuffer.ordered ? 'ol' : 'ul';
    blocks.push(
      <Tag key={`list-${key}`} style={{ paddingLeft: 18, margin: '4px 0' }}>
        {listBuffer.items.map((item, i) => (
          <li key={i} style={{ marginBottom: 2 }}>{renderInline(item)}</li>
        ))}
      </Tag>,
    );
    listBuffer = null;
  };

  lines.forEach((raw, i) => {
    const line = raw.trim();
    const ol = line.match(/^(\d+)\.\s+(.*)/);
    const ul = line.match(/^[-•*]\s+(.*)/);
    if (ol) {
      if (!listBuffer || !listBuffer.ordered) {
        flushList(i);
        listBuffer = { ordered: true, items: [] };
      }
      listBuffer.items.push(ol[2]);
      return;
    }
    if (ul) {
      if (!listBuffer || listBuffer.ordered) {
        flushList(i);
        listBuffer = { ordered: false, items: [] };
      }
      listBuffer.items.push(ul[1]);
      return;
    }
    flushList(i);
    if (line === '') {
      blocks.push(<div key={i} style={{ height: 6 }} />);
    } else {
      blocks.push(
        <p key={i} style={{ margin: '2px 0', lineHeight: 1.5 }}>
          {renderInline(line)}
        </p>,
      );
    }
  });
  flushList(lines.length);

  return <>{blocks}</>;
}

/** Inline tokens: **bold** and `code`. Greedy left-to-right, no nesting. */
function renderInline(s: string): React.ReactNode {
  // Split on **bold** and `code` while keeping delimiters.
  const parts = s.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  return parts.map((p, i) => {
    if (p.startsWith('**') && p.endsWith('**')) {
      return <strong key={i}>{p.slice(2, -2)}</strong>;
    }
    if (p.startsWith('`') && p.endsWith('`')) {
      return (
        <code key={i} className="mono" style={{
          padding: '0 4px', background: 'var(--surface-2)', borderRadius: 3,
          fontSize: '0.92em',
        }}>
          {p.slice(1, -1)}
        </code>
      );
    }
    return <Fragment key={i}>{p}</Fragment>;
  });
}
