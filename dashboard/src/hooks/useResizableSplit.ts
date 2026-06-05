import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react';

const MIN = 240;
const MAX = 720;

/**
 * Drag-to-resize the left column of a 2-pane `.vuln-split` grid.
 *
 * Returns a ref to put on the grid container, the `gridTemplateColumns` value
 * (left px + 6px handle + flexible right), and a pointer-down handler for the
 * resizer bar. The chosen width is clamped to [MIN, MAX] and persisted to
 * localStorage under `storageKey` so it survives reloads.
 *
 * Usage:
 *   const { containerRef, gridColumns, onResizerPointerDown } =
 *     useResizableSplit('vulns.listWidth');
 *   <div ref={containerRef} className="vuln-split" style={{ gridTemplateColumns: gridColumns }}>
 *     {leftPane}
 *     <div className="col-resizer" onPointerDown={onResizerPointerDown} />
 *     {rightPane}
 *   </div>
 */
export function useResizableSplit(storageKey: string, defaultWidth = 320) {
  const [width, setWidth] = useState<number>(() => {
    const raw = Number(localStorage.getItem(storageKey));
    return Number.isFinite(raw) && raw >= MIN && raw <= MAX ? raw : defaultWidth;
  });
  const containerRef = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);
  // Mirror the latest width so the pointerup handler persists the final value
  // without a stale closure. Updated only inside event handlers (never render).
  const widthRef = useRef(width);

  useEffect(() => {
    const onMove = (e: PointerEvent) => {
      if (!dragging.current || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const next = Math.min(MAX, Math.max(MIN, e.clientX - rect.left));
      widthRef.current = next;
      setWidth(next);
    };
    const onUp = () => {
      if (!dragging.current) return;
      dragging.current = false;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      try {
        localStorage.setItem(storageKey, String(Math.round(widthRef.current)));
      } catch {
        // ignore quota / private-mode errors — width just won't persist
      }
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
    return () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
  }, [storageKey]);

  const onResizerPointerDown = (e: ReactPointerEvent) => {
    e.preventDefault();
    dragging.current = true;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  };

  return {
    width,
    containerRef,
    onResizerPointerDown,
    gridColumns: `${width}px 6px minmax(0, 1fr)`,
  };
}
