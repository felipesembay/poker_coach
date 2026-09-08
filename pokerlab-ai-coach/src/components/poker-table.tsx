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
  bb,
}: {
  seats: TableSeat[];
  board?: string[];
  pot?: number;
  cardSize?: "sm" | "md" | "lg" | "xl" | "2xl";
  seatCardSize?: "sm" | "md" | "lg" | "xl" | "2xl";
  /** Tamanho do big blind (chips) — quando informado, o stack de cada
   * assento é exibido em BB (ex. "19.9 BB") em vez de fichas cruas, que é
   * como se pensa jogando torneio. O pot no centro continua em fichas
   * (junto do contexto de blind/ante que só faz sentido em valor absoluto). */
  bb?: number;
}) {
  const angles = seatAngles(seats);
  // Só o texto (nome/posição/stack/ação) mora nessa largura agora — as
  // cartas saíram do quadro e flutuam fora dele (ver abaixo), então não
  // precisa mais ser larga o bastante pra caber as 2 cartas lado a lado.
  const seatBoxWidth = seatCardSize === "sm" ? 100 : seatCardSize === "md" ? 118 : 158;

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
        // Cartas ficam FORA do quadro de info, do lado de fora da mesa
        // (longe do centro) — pra não empilhar em cima do nome/stack nem
        // encostar no board. Assentos na metade de cima da oval (sin<0)
        // têm as cartas acima do quadro; embaixo (incl. Hero, sempre
        // embaixo), as cartas ficam abaixo.
        const cardsAboveBox = Math.sin(rad) < 0;
        return (
          <div
            key={s.key}
            className={cn(
              "absolute -translate-x-1/2 -translate-y-1/2 flex flex-col items-center gap-1.5",
              cardsAboveBox && "flex-col-reverse",
            )}
            style={{
              left: `${50 + 39 * Math.cos(rad)}%`,
              top: `${50 + 37 * Math.sin(rad)}%`,
              width: seatBoxWidth,
            }}
          >
            <div
              className={cn(
                "w-full rounded-md border p-2 backdrop-blur-sm transition-colors",
                s.isHero
                  ? "border-primary/60 bg-primary/12 shadow-[0_0_0_1px_var(--primary)]"
                  : "border-border bg-card/85",
              )}
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
                  {bb ? `${(s.stack / bb).toFixed(1)} BB` : s.stack.toLocaleString("pt-BR")}
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
            </div>
            {s.cards && s.cards.length >= 2 ? <Hole cards={s.cards} size={seatCardSize} /> : null}
          </div>
        );
      })}
    </div>
  );
}
