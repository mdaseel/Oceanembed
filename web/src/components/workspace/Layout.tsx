import { useEffect, useRef, useState, type ReactNode } from "react";

/**
 * Shared workspace primitives: one inspector made of collapsible sections, and
 * one analysis tray. Closed sections keep their content in the document, so a
 * value never disappears - it is only folded away.
 */

export function Inspector({
  eyebrow,
  title,
  children,
  testid = "inspector",
}: {
  eyebrow: string;
  title: string;
  children: ReactNode;
  testid?: string;
}) {
  return (
    <aside className="panel ws-inspector" data-testid={testid} aria-label="Inspector">
      <div className="ws-inspector-head">
        <span className="eyebrow">{eyebrow}</span>
        <h2>{title}</h2>
      </div>
      {children}
    </aside>
  );
}

export function Section({
  title,
  badge,
  defaultOpen = false,
  testid,
  children,
}: {
  title: string;
  badge?: string;
  defaultOpen?: boolean;
  testid?: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  // A section whose default becomes open (for example coastal context when a
  // monitoring area is selected) unfolds; the user can still fold it again.
  useEffect(() => {
    if (defaultOpen) setOpen(true);
  }, [defaultOpen]);
  return (
    <details
      className="ws-section"
      open={open}
      data-testid={testid}
      onToggle={(e) => setOpen((e.currentTarget as HTMLDetailsElement).open)}
    >
      <summary>
        {title}
        {badge && <span className="ws-section-badge">{badge}</span>}
      </summary>
      <div className="ws-section-body">{children}</div>
    </details>
  );
}

export interface TrayTab {
  id: string;
  label: string;
  badge?: string;
  /** Keep the tab mounted while hidden (cheap views whose state must persist). */
  keepMounted?: boolean;
  render: () => ReactNode;
}

export function Tray({
  tabs,
  active,
  onActive,
  testid = "analysis-tray",
  revealKey = 0,
}: {
  tabs: TrayTab[];
  active: string;
  onActive: (id: string) => void;
  testid?: string;
  revealKey?: number;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const root = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!revealKey) return;
    setCollapsed(false);
    root.current?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth", block: "start" });
  }, [revealKey]);
  const current = tabs.find((t) => t.id === active) ?? tabs[0];
  return (
    <section
      className="panel ws-tray"
      ref={root}
      data-testid={testid}
      data-active={current?.id}
      data-collapsed={collapsed ? "true" : "false"}
    >
      <div className="ws-tray-bar" role="tablist" aria-label="Analysis tray">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={t.id === current?.id}
            className={t.id === current?.id ? "active" : ""}
            data-testid={`tray-tab-${t.id}`}
            onClick={() => {
              onActive(t.id);
              setCollapsed(false);
            }}
          >
            {t.label}
            {t.badge && <span className="ws-section-badge">{t.badge}</span>}
          </button>
        ))}
        <button
          type="button"
          className="ws-tray-toggle"
          aria-expanded={!collapsed}
          onClick={() => setCollapsed(!collapsed)}
        >
          {collapsed ? "Show" : "Hide"}
        </button>
      </div>
      <div className="ws-tray-body">
        {tabs.map((t) =>
          t.id === current?.id ? (
            <div key={t.id} role="tabpanel">
              {t.render()}
            </div>
          ) : t.keepMounted ? (
            <div key={t.id} hidden>
              {t.render()}
            </div>
          ) : null,
        )}
      </div>
    </section>
  );
}

export function SubTabs<T extends string>({
  tabs,
  active,
  onActive,
  label,
}: {
  tabs: { id: T; label: string }[];
  active: T;
  onActive: (id: T) => void;
  label: string;
}) {
  return (
    <div className="ws-subtabs" role="tablist" aria-label={label}>
      {tabs.map((t) => (
        <button
          key={t.id}
          type="button"
          role="tab"
          aria-selected={t.id === active}
          className={t.id === active ? "active" : ""}
          data-testid={`tab-${t.id}`}
          onClick={() => onActive(t.id)}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function regionLabel(key: string): string {
  if (key === "nio") return "North Indian Ocean domain";
  return key
    .split("_")
    .map((w, i) => (i > 0 && w === "of" ? w : w.charAt(0).toUpperCase() + w.slice(1)))
    .join(" ");
}

export const pct = (v: number | null | undefined, digits = 1) =>
  v == null || !Number.isFinite(v) ? "—" : `${(v * 100).toFixed(digits)} %`;

export const num = (v: number | null | undefined, digits = 2, unit = "") =>
  v == null || !Number.isFinite(v) ? "—" : `${v.toFixed(digits)}${unit ? ` ${unit}` : ""}`;
