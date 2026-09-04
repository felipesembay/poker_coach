import { Hole, PlayingCard } from "@/components/lab";
import { cn } from "@/lib/utils";

export type TableSeat = {
  key: string;
  position?: string | null;
  label: string; // nome do jogador ou só a posição
  stack?: number | null;
  isHero: boolean;
  cards?: string[] | null;
  actionText?: string | null;
  actionTone?: "fold" | "allin" | "normal";
};

/** Distribui N assentos ao redor da mesa, hero embaixo (90°). */
export function seatAngles<T extends { isHero: boolean }>(seats: T[]): number[] {
  const n = seats.length || 1;
  const heroIdx = seats.findIndex((s) => s.isHero);
  return seats.map((_, i) => {
    const delta = i - (heroIdx >= 0 ? heroIdx : 0);
    return (((90 + delta * (360 / n)) % 360) + 360) % 360;
  });
}

/**
 * Mesa de poker visual (oval, feltro, assentos ao redor, board + pot no
 * centro) — componente compartilhado entre Replayer e Treinador de
 * Push/Fold, pra não duplicar a mesma mesa duas vezes.
 */
export function PokerTable({
  seats,
  board = [],
  pot,
  cardSize = "lg",
  seatCardSize = "sm",
}: {
  seats: TableSeat[];
  board?: string[];
  pot?: number;
  cardSize?: "sm" | "md" | "lg" | "xl" | "2xl";
  seatCardSize?: "sm" | "md" | "lg" | "xl" | "2xl";
}) {
  const angles = seatAngles(seats);
  const seatBoxWidth = seatCardSize === "sm" ? 124 : seatCardSize === "md" ? 150 : 220;

  return (
    <div className="grid-lines relative aspect-[16/10] w-full overflow-hidden rounded-lg p-6">
      <div className="absolute inset-6 rounded-[999px] border border-felt-edge bg-felt/70 shadow-[inset_0_0_60px_rgba(0,0,0,0.55)]" />

      <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 text-center">
        <div className="flex justify-center gap-2">
          {board.map((c, i) => (
            <PlayingCard key={`${c}-${i}`} card={c} size={cardSize} />
          ))}
        </div>
        {pot != null && (
          <>
            <p className="num mt-3 text-xs uppercase tracking-[0.16em] text-muted-foreground">
              Pot
            </p>
            <p className="num text-lg font-bold">{pot.toLocaleString("pt-BR")}</p>
          </>
        )}
      </div>

      {seats.map((s, i) => {
        const rad = (angles[i]! * Math.PI) / 180;
        return (
          <div
            key={s.key}
            className={cn(
              "absolute -translate-x-1/2 -translate-y-1/2 rounded-md border p-2 backdrop-blur-sm transition-colors",
              s.isHero
                ? "border-primary/60 bg-primary/12 shadow-[0_0_0_1px_var(--primary)]"
                : "border-border bg-card/85",
            )}
            style={{
              left: `${50 + 39 * Math.cos(rad)}%`,
              top: `${50 + 37 * Math.sin(rad)}%`,
              width: seatBoxWidth,
            }}
          >
            <div className="flex min-w-0 items-center justify-between gap-1">
              <span
                className={cn("truncate text-[11px] font-semibold", s.isHero && "text-primary")}
              >
                {s.label}
              </span>
              {s.position && (
                <span className="num shrink-0 rounded bg-secondary px-1 text-[9px] font-medium">
                  {s.position}
                </span>
              )}
            </div>
            {s.stack != null && (
              <p className="num text-[11px] text-muted-foreground">
                {s.stack.toLocaleString("pt-BR")}
              </p>
            )}
            {s.actionText && (
              <p
                className={cn(
                  "num truncate text-[10px]",
                  s.actionTone === "allin"
                    ? "text-loss"
                    : s.actionTone === "fold"
                      ? "text-muted-foreground/60"
                      : "text-profit",
                )}
              >
                {s.actionText}
              </p>
            )}
            {s.cards && s.cards.length >= 2 ? (
              <div className="mt-1.5">
                <Hole cards={s.cards} size={seatCardSize} />
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
