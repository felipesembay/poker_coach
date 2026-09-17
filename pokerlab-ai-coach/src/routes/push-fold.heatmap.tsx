import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { ArrowUpRight } from "lucide-react";

import { Hole, PageHeader, Panel } from "@/components/lab";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { leaksApi, type LeakCategory } from "@/lib/api";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/push-fold/heatmap")({
  head: () => ({
    meta: [
      { title: "Heatmap Push/Fold — PokerLab" },
      {
        name: "description",
        content: "Frequência de erro e EV perdido por posição e stack efetivo, com referência de Nash.",
      },
    ],
  }),
  component: HeatmapPage,
});

// Mesma ordem de posições usada no Replayer/treinador. Nem todo torneio
// tem todas — colunas sem nenhum spot ficam vazias, não escondidas (é
// informação: "sem amostra", não "sem posição").
const POSITIONS = ["UTG", "HJ", "CO", "BTN", "SB", "BB"];
// Ordem das faixas: raso (topo) -> fundo (base) — mesmas faixas de
// poker_coach.pushfold.analyze.LEAK_STACK_BUCKETS.
const BUCKETS = ["3-5BB", "6-10BB", "11-15BB", "16-20BB"];

// Amostra mínima pra célula ser mostrada com confiança plena — abaixo
// disso, a célula é marcada como baixa amostra (não é a mesma coisa que
// "sem erro"). Ajustável; não é um padrão da indústria.
const MIN_SAMPLE = 10;

function cellTone(c: LeakCategory | undefined): string {
  if (!c || c.opportunities === 0) return "bg-elevated/30 text-muted-foreground/40";
  if (c.incorrect === 0) return "bg-profit/10 text-profit";
  const rate = c.error_rate_pct ?? 0;
  if (rate >= 40) return "bg-loss/30 text-loss";
  if (rate >= 20) return "bg-loss/15 text-loss";
  return "bg-loss/5 text-foreground";
}

function HeatmapPage() {
  const [selected, setSelected] = useState<LeakCategory | null>(null);

  const categoriesQ = useQuery({
    queryKey: ["leak-categories"],
    queryFn: () => leaksApi.categories({ bb_min: 1, bb_max: 25 }),
  });

  const openCategories = useMemo(
    () => (categoriesQ.data ?? []).filter((c) => c.decision_scope === "open_shove"),
    [categoriesQ.data],
  );

  const grid = useMemo(() => {
    const byKey = new Map(openCategories.map((c) => [`${c.position}|${c.stack_bucket}`, c]));
    return BUCKETS.map((bucket) => ({
      bucket,
      cells: POSITIONS.map((pos) => byKey.get(`${pos}|${bucket}`)),
    }));
  }, [openCategories]);

  const handsQ = useQuery({
    queryKey: ["leak-hands", selected?.category_key],
    queryFn: () =>
      leaksApi.hands({
        decision_scope: "open_shove",
        position: selected!.position,
        stack_bucket: selected!.stack_bucket,
        bb_min: 1,
        bb_max: 25,
      }),
    enabled: !!selected,
  });

  return (
    <div className="space-y-5">
      <PageHeader
        title="Heatmap Push/Fold"
        description="Frequência de erro e EV perdido por posição × stack efetivo, nos spots de abertura (você é o primeiro a agir) — referência de Nash, vilão modelado como BB."
      />

      <Panel
        title="Posição × stack efetivo"
        subtitle={`Cor = intensidade do erro (0 / <20% / 20–40% / ≥40%) · células com menos de ${MIN_SAMPLE} oportunidades vêm marcadas como baixa amostra`}
      >
        <div className="overflow-x-auto p-4">
          <table className="w-full border-separate border-spacing-1">
            <thead>
              <tr>
                <th className="w-20 text-left text-xs text-muted-foreground">Stack</th>
                {POSITIONS.map((p) => (
                  <th key={p} className="num text-xs font-semibold text-muted-foreground">
                    {p}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {grid.map((row) => (
                <tr key={row.bucket}>
                  <td className="num text-xs text-muted-foreground">{row.bucket}</td>
                  {row.cells.map((c, i) => (
                    <td key={POSITIONS[i]}>
                      <button
                        type="button"
                        disabled={!c || c.opportunities === 0}
                        onClick={() => c && setSelected(c)}
                        className={cn(
                          "num flex h-16 w-full flex-col items-center justify-center gap-0.5 rounded-md border text-xs transition-colors",
                          c && c.opportunities > 0
                            ? "border-border hover:border-primary/50"
                            : "border-dashed border-border/50",
                          cellTone(c),
                          c && c.opportunities < MIN_SAMPLE && c.opportunities > 0 && "opacity-60",
                          selected?.category_key === c?.category_key && "ring-1 ring-primary",
                        )}
                        title={
                          c && c.opportunities > 0
                            ? `${c.opportunities} oportunidades · ${c.error_rate_pct}% erro · -${c.ev_lost_total_bb} BB`
                            : "Sem amostra"
                        }
                      >
                        {c && c.opportunities > 0 ? (
                          <>
                            <span className="font-bold">{c.error_rate_pct}%</span>
                            <span className="text-[10px] opacity-80">{c.opportunities} spots</span>
                          </>
                        ) : (
                          <span>—</span>
                        )}
                      </button>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      {selected && (
        <Panel
          title={`Mãos — ${selected.position} · ${selected.stack_bucket}`}
          subtitle={`${selected.opportunities} oportunidades · ${selected.incorrect} decisões incorretas · EV perdido total -${selected.ev_lost_total_bb.toFixed(1)} BB`}
        >
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead>Cartas</TableHead>
                  <TableHead>Stack ef.</TableHead>
                  <TableHead>Ação tomada</TableHead>
                  <TableHead>Referência (Nash)</TableHead>
                  <TableHead className="text-right">EV perdido</TableHead>
                  <TableHead className="text-right">Replayer</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {handsQ.isLoading && (
                  <TableRow>
                    <TableCell colSpan={6} className="py-8 text-center text-sm text-muted-foreground">
                      Carregando…
                    </TableCell>
                  </TableRow>
                )}
                {(handsQ.data ?? []).map((h) => (
                  <TableRow key={`${h.site}-${h.hand_id}`}>
                    <TableCell>
                      <Hole cards={h.hero_cards.split(" ")} size="sm" />
                    </TableCell>
                    <TableCell className="num text-xs">{h.effective_bb} BB</TableCell>
                    <TableCell>
                      <Badge
                        variant="outline"
                        className={h.action_taken !== h.action_reference ? "text-loss" : ""}
                      >
                        {h.action_taken}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">{h.action_reference}</Badge>
                    </TableCell>
                    <TableCell className="num text-right text-xs text-loss">
                      {h.ev_lost_bb > 0 ? `-${h.ev_lost_bb.toFixed(2)} BB` : "0.00 BB"}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button variant="ghost" size="sm" asChild>
                        <Link to="/replayer" search={{ site: h.site, handId: h.hand_id }}>
                          Abrir <ArrowUpRight className="ml-1 size-3.5" />
                        </Link>
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </Panel>
      )}
    </div>
  );
}
