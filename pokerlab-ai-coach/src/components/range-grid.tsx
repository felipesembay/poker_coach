import { useQuery } from "@tanstack/react-query";

import { Panel } from "@/components/lab";
import { pushfoldApi } from "@/lib/api";
import { cn } from "@/lib/utils";

// Mesma ordem/convenção do motor Python (poker_coach/ui/range_grid.py e
// pushfold/nash.ev_grid) — espelhado aqui pra não duplicar o cálculo do
// grid em si (isso vem da API), só a montagem visual das 169 classes.
const RANKS_DESC = "AKQJT98765432";

function classAt(row: number, col: number): string {
  const a = RANKS_DESC[row]!;
  const b = RANKS_DESC[col]!;
  if (row === col) return a + a;
  if (row < col) return a + b + "s";
  return b + a + "o";
}

/** "As" + "Kh" -> "AKo" (maior rank primeiro, "s"/"o" por naipe igual/diferente). */
export function handClassOf(cards: string[] | null | undefined): string | null {
  if (!cards || cards.length !== 2) return null;
  const [c1, c2] = cards;
  const r1 = c1!.slice(0, -1).toUpperCase();
  const r2 = c2!.slice(0, -1).toUpperCase();
  if (r1 === r2) return r1 + r2;
  const i1 = RANKS_DESC.indexOf(r1);
  const i2 = RANKS_DESC.indexOf(r2);
  if (i1 === -1 || i2 === -1) return null;
  const suited = c1!.slice(-1).toLowerCase() === c2!.slice(-1).toLowerCase();
  const [hi, lo] = i1 < i2 ? [r1, r2] : [r2, r1];
  return hi + lo + (suited ? "s" : "o");
}

/** Verde escala com EV positivo, vermelho com negativo — mesma escala de
 * poker_coach/ui/range_grid.py::_color, só que devolvendo CSS em vez de HTML. */
function cellBg(ev: number, vmax: number): string {
  const vm = vmax <= 0 ? 1 : vmax;
  const t = Math.min(Math.abs(ev) / vm, 1);
  let r: number, g: number, b: number;
  if (ev >= 0) {
    r = Math.round(214 - t * 190);
    g = Math.round(238 - t * 88);
    b = Math.round(214 - t * 190);
  } else {
    r = Math.round(238 - t * 8);
    g = Math.round(214 - t * 150);
    b = Math.round(214 - t * 150);
  }
  return `rgb(${r},${g},${b})`;
}

/**
 * Grid 13x13 de range (estilo ICMizer/HRC) — EV do push de CADA classe de
 * mão contra a range de call de equilíbrio, pro mesmo stack/pot do spot
 * atual. Reusa /api/pushfold/range-grid (mesmo motor do relatório e do
 * treinador), só monta a visualização.
 */
export function RangeGrid({
  effectiveBb,
  potBb,
  heroCards,
  cellPx = 26,
  kind = "push",
}: {
  effectiveBb: number;
  potBb: number;
  heroCards?: string[] | null;
  cellPx?: number;
  /** "push": herói decide empurrar (abertura) — EV de cada classe empurrando.
   * "call": herói decide pagar um all-in que já estava na mesa — EV de
   * cada classe pagando a range de shove de equilíbrio do vilão. */
  kind?: "push" | "call";
}) {
  const gridQ = useQuery({
    queryKey: ["range-grid", kind, effectiveBb, potBb],
    queryFn: () =>
      kind === "call"
        ? pushfoldApi.callGrid({ effective_bb: effectiveBb, pot_bb: potBb })
        : pushfoldApi.rangeGrid({ effective_bb: effectiveBb, pot_bb: potBb }),
  });

  if (gridQ.isLoading) {
    return <p className="p-4 text-center text-sm text-muted-foreground">Calculando grid…</p>;
  }
  if (gridQ.isError || !gridQ.data) {
    return <p className="p-4 text-center text-sm text-loss">Erro ao calcular o grid.</p>;
  }

  const { grid, shove_pct, call_pct } = gridQ.data;
  const values = Object.values(grid);
  const vmax = Math.max(...values.map((v) => Math.abs(v)), 1);
  const heroClass = handClassOf(heroCards);

  return (
    <div className="p-3">
      <p className="mb-2 text-center text-[11px] text-muted-foreground">
        {kind === "call" ? (
          <>
            Range de shove do vilão:{" "}
            <strong className="text-foreground">{shove_pct.toFixed(1)}%</strong> das mãos
          </>
        ) : (
          <>
            Push: <strong className="text-foreground">{shove_pct.toFixed(1)}%</strong> das mãos ·
            Call da BB: <strong className="text-foreground">{call_pct.toFixed(1)}%</strong>
          </>
        )}{" "}
        · {effectiveBb.toFixed(1)} BB efetivos
      </p>
      <div
        className="mx-auto inline-grid overflow-hidden rounded-md border border-border"
        style={{ gridTemplateColumns: `repeat(13, ${cellPx}px)` }}
      >
        {Array.from({ length: 13 }).flatMap((_, row) =>
          Array.from({ length: 13 }).map((_, col) => {
            const cls = classAt(row, col);
            const ev = grid[cls] ?? 0;
            const isHero = heroClass === cls;
            return (
              <div
                key={cls}
                title={`${cls}: ${ev >= 0 ? "+" : ""}${ev.toFixed(2)} BB`}
                className={cn(
                  "flex flex-col items-center justify-center border border-black/10 font-bold leading-none text-white [text-shadow:0_1px_2px_rgba(0,0,0,0.85)]",
                  isHero && "relative z-10 ring-2 ring-inset ring-primary",
                )}
                style={{
                  width: cellPx,
                  height: cellPx,
                  background: cellBg(ev, vmax),
                  fontSize: cellPx * 0.32,
                }}
              >
                <span>{cls}</span>
              </div>
            );
          }),
        )}
      </div>
      {heroClass && (
        <p className="mt-2 text-center text-[11px] text-muted-foreground">
          Sua mão: <strong className="text-primary">{heroClass}</strong> (destacada acima)
        </p>
      )}
    </div>
  );
}

/** Wrapper com Panel — evita repetir título/subtítulo nos dois lugares
 * que usam o grid (Replayer e Treinador). */
export function RangeGridPanel({
  kind = "push",
  ...props
}: {
  effectiveBb: number;
  potBb: number;
  heroCards?: string[] | null;
  cellPx?: number;
  kind?: "push" | "call";
}) {
  return (
    <Panel
      title="Mapa de mãos"
      subtitle={
        kind === "call"
          ? "EV de pagar o all-in por classe · mesmo stack/pot do spot"
          : "EV do push por classe · mesmo stack/pot do spot"
      }
    >
      <RangeGrid kind={kind} {...props} />
    </Panel>
  );
}
