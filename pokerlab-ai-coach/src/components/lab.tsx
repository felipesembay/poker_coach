import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description: string;
  actions?: ReactNode;
}) {
  return (
    <header className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-4 sm:flex sm:items-center sm:justify-between">
      <div className="min-w-0">
        <h1 className="truncate text-xl font-extrabold tracking-tight sm:text-2xl">{title}</h1>
        <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">{description}</p>
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </header>
  );
}

export function StatCard({
  label,
  value,
  delta,
  hint,
  tone = "neutral",
}: {
  label: string;
  value: string;
  delta?: string;
  hint?: string;
  tone?: "profit" | "loss" | "neutral";
}) {
  return (
    <div className="panel fade-up p-4 transition-colors hover:border-primary/30">
      <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
        {label}
      </p>
      <p className="num mt-2 text-2xl font-bold">{value}</p>
      <div className="mt-1.5 flex items-center gap-2">
        {delta ? (
          <span
            className={cn(
              "num text-xs font-semibold",
              tone === "profit" && "text-profit",
              tone === "loss" && "text-loss",
              tone === "neutral" && "text-muted-foreground",
            )}
          >
            {delta}
          </span>
        ) : null}
        {hint ? <span className="truncate text-xs text-muted-foreground">{hint}</span> : null}
      </div>
    </div>
  );
}

export function Panel({
  title,
  subtitle,
  actions,
  children,
  className,
}: {
  title?: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("panel fade-up overflow-hidden", className)}>
      {title ? (
        <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 border-b border-border px-4 py-3 sm:flex sm:justify-between">
          <div className="min-w-0">
            <h2 className="truncate text-sm font-semibold">{title}</h2>
            {subtitle ? <p className="truncate text-xs text-muted-foreground">{subtitle}</p> : null}
          </div>
          {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
        </div>
      ) : null}
      {children}
    </section>
  );
}

export function Money({ value, suffix = "" }: { value: number; suffix?: string }) {
  const positive = value > 0;
  const zero = value === 0;
  return (
    <span
      className={cn(
        "num font-semibold",
        zero ? "text-muted-foreground" : positive ? "text-profit" : "text-loss",
      )}
    >
      {positive ? "+" : ""}
      {value.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}
      {suffix}
    </span>
  );
}

type Suit = { color: string; glyph: string };

const SPADE: Suit = { color: "text-foreground", glyph: "♠" };

const SUITS: Record<string, Suit> = {
  s: SPADE,
  h: { color: "text-loss", glyph: "♥" },
  d: { color: "text-primary", glyph: "♦" },
  c: { color: "text-profit", glyph: "♣" },
};

export function PlayingCard({
  card,
  size = "md",
}: {
  card: string;
  size?: "sm" | "md" | "lg" | "xl" | "2xl";
}) {
  const rank = card.slice(0, -1);
  const suit: Suit = SUITS[card.slice(-1).toLowerCase()] ?? SPADE;

  return (
    <span
      className={cn(
        "num inline-flex flex-col items-center justify-center rounded-[4px] border border-border bg-elevated font-bold leading-none",
        size === "sm" && "h-7 w-5 text-[11px]",
        size === "md" && "h-10 w-7 text-sm",
        size === "lg" && "h-16 w-11 gap-0.5 text-lg",
        size === "xl" && "h-24 w-16 gap-1 rounded-md text-2xl",
        size === "2xl" && "h-48 w-32 gap-1.5 rounded-lg text-5xl",
        suit.color,
      )}
    >
      <span>{rank}</span>
      <span
        className={
          size === "sm"
            ? "text-[9px]"
            : size === "xl" || size === "2xl"
              ? "text-[0.6em]"
              : "text-xs"
        }
      >
        {suit.glyph}
      </span>
    </span>
  );
}

export function Hole({
  cards,
  size = "md",
}: {
  cards: string[];
  size?: "sm" | "md" | "lg" | "xl" | "2xl";
}) {
  return (
    <span className="inline-flex items-center gap-1">
      {cards.map((c, i) => (
        <PlayingCard key={`${c}-${i}`} card={c} size={size} />
      ))}
    </span>
  );
}
