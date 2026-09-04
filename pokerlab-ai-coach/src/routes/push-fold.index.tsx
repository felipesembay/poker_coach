import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Target } from "lucide-react";

import { Money, PageHeader, Panel, StatCard, Hole } from "@/components/lab";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { pushfoldApi } from "@/lib/api";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/push-fold/")({
  head: () => ({
    meta: [
      { title: "Push/Fold — PokerLab" },
      {
        name: "description",
        content:
          "Analise precisão, EV perdido e erros nos spots de push/fold e treine com drills guiados.",
      },
      { property: "og:title", content: "Push/Fold — PokerLab" },
      {
        property: "og:description",
        content: "Relatório de spots de all-in por stack e posição com treinador integrado.",
      },
    ],
  }),
  component: PushFoldPage,
});

const STACK_BUCKETS = [
  { label: "< 8 BB", min: 0, max: 8 },
  { label: "8–12 BB", min: 8, max: 12 },
  { label: "12–15 BB", min: 12, max: 15 },
  { label: "15–18 BB", min: 15, max: 18 },
  { label: "18–22 BB", min: 18, max: 22 },
  { label: "22+ BB", min: 22, max: 999 },
];

// Ordem padrão de posições preflop (BB fica de fora: o motor só cobre
// spots de abertura, onde o herói nunca é a BB) — usada só pra ordenar
// o filtro, não pra validar o que vem da API.
const POSITION_ORDER = ["UTG", "UTG+1", "UTG+2", "MP", "MP+1", "HJ", "CO", "BTN", "SB"];

function PushFoldPage() {
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<"all" | "errors" | "hits">("all");
  const [position, setPosition] = useState("Todas");

  const summaryQ = useQuery({
    queryKey: ["pushfold-summary"],
    queryFn: () => pushfoldApi.summary({ bb_min: 5, bb_max: 25 }),
  });
  const spotsQ = useQuery({
    queryKey: ["pushfold-spots"],
    queryFn: () => pushfoldApi.spots({ bb_min: 5, bb_max: 25, limit: 300 }),
  });

  const spots = spotsQ.data ?? [];
  const summary = summaryQ.data;
  const hits = summary ? summary.spots - summary.leak_spots : 0;

  const positions = useMemo(() => {
    const present = Array.from(new Set(spots.map((s) => s.position)));
    return present.sort((a, b) => {
      const ia = POSITION_ORDER.indexOf(a);
      const ib = POSITION_ORDER.indexOf(b);
      return (ia === -1 ? 999 : ia) - (ib === -1 ? 999 : ib);
    });
  }, [spots]);

  const stackAccuracy = useMemo(() => {
    return STACK_BUCKETS.map((b) => {
      const inBucket = spots.filter((s) => {
        const bb = parseFloat(s.stack);
        return bb >= b.min && bb < b.max;
      });
      const ok = inBucket.filter((s) => s.taken === s.correct).length;
      return {
        range: b.label,
        acc: inBucket.length ? Math.round((ok / inBucket.length) * 100) : null,
        n: inBucket.length,
      };
    });
  }, [spots]);

  const errorBreakdown = useMemo(() => {
    const wrong = spots.filter((s) => s.taken !== s.correct);
    const foldInsteadOfShove = wrong.filter((s) => s.taken === "Fold").length;
    const shoveInsteadOfFold = wrong.filter((s) => s.taken === "All-in").length;
    const total = wrong.length || 1;
    return [
      {
        label: "Fold em vez de all-in",
        pct: Math.round((foldInsteadOfShove / total) * 100),
        tone: "loss",
      },
      {
        label: "All-in em vez de fold",
        pct: Math.round((shoveInsteadOfFold / total) * 100),
        tone: "primary",
      },
    ];
  }, [spots]);

  const filteredSpots = useMemo(() => {
    return spots.filter((s) => {
      if (filter === "errors" && s.taken === s.correct) return false;
      if (filter === "hits" && s.taken !== s.correct) return false;
      if (position !== "Todas" && s.position !== position) return false;
      if (
        search &&
        !`${s.spot} ${s.position} ${s.hero_cards}`.toLowerCase().includes(search.toLowerCase())
      )
        return false;
      return true;
    });
  }, [spots, filter, position, search]);

  return (
    <div className="space-y-5">
      <PageHeader
        title="Push/Fold"
        description={
          summary
            ? `${summary.spots} spots analisados (abertura preflop, vilão = BB) · ${summary.leak_spots} decisões erradas`
            : "Carregando…"
        }
        actions={
          <Button size="sm" asChild>
            <Link to="/push-fold/treinar">
              <Target className="mr-1.5 size-3.5" /> Treinar
            </Link>
          </Button>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard
          label="Precisão"
          value={summary ? `${((hits / summary.spots) * 100 || 0).toFixed(1)}%` : "—"}
          tone="profit"
          hint={summary ? `${summary.spots} spots` : ""}
        />
        <StatCard
          label="EV perdido"
          value={summary ? `-${summary.total_ev_lost_bb.toFixed(1)} BB` : "—"}
          tone="loss"
          hint="Vs. Nash chip EV"
        />
        <StatCard label="Acertos" value={summary ? String(hits) : "—"} tone="profit" />
        <StatCard label="Erros" value={summary ? String(summary.leak_spots) : "—"} tone="loss" />
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Panel
          title="Precisão por stack efetivo"
          subtitle="Onde você perde EV"
          className="xl:col-span-2"
        >
          <ul className="divide-y divide-border">
            {stackAccuracy.map((s) => (
              <li
                key={s.range}
                className="grid grid-cols-[96px_minmax(0,1fr)_56px] items-center gap-3 px-4 py-3"
              >
                <span className="num text-xs text-muted-foreground">{s.range}</span>
                <div className="h-2 overflow-hidden rounded-full bg-elevated">
                  {s.acc !== null ? (
                    <div
                      className={cn(
                        "h-full rounded-full transition-all",
                        s.acc >= 88 ? "bg-profit" : s.acc >= 80 ? "bg-primary" : "bg-loss",
                      )}
                      style={{ width: `${s.acc}%` }}
                    />
                  ) : null}
                </div>
                <span className="num text-right text-xs font-semibold">
                  {s.acc !== null ? `${s.acc}%` : "—"}
                </span>
              </li>
            ))}
          </ul>
        </Panel>

        <Panel title="Distribuição de erros" subtitle="Fold-vs-All-in — só 2 tipos (motor binário)">
          <div className="space-y-3 p-4">
            {errorBreakdown.map((e) => (
              <div key={e.label}>
                <div className="flex items-center justify-between gap-2 text-xs">
                  <span className="truncate text-muted-foreground">{e.label}</span>
                  <span className="num font-semibold">{e.pct}%</span>
                </div>
                <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-elevated">
                  <div
                    className={cn("h-full", e.tone === "loss" ? "bg-loss" : "bg-primary")}
                    style={{ width: `${e.pct}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </Panel>
      </div>

      <Panel
        title="Spots revisados"
        subtitle="Comparação entre ação tomada e ação correta (Nash, chip EV)"
        actions={
          <div className="flex items-center gap-2">
            <Input
              placeholder="Pesquisar spot…"
              className="h-8 w-40 text-xs"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <Select value={position} onValueChange={setPosition}>
              <SelectTrigger className="h-8 w-[110px] text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="Todas">Todas posições</SelectItem>
                {positions.map((p) => (
                  <SelectItem key={p} value={p}>
                    {p}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={filter} onValueChange={(v) => setFilter(v as typeof filter)}>
              <SelectTrigger className="h-8 w-[130px] text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos</SelectItem>
                <SelectItem value="errors">Só erros</SelectItem>
                <SelectItem value="hits">Só acertos</SelectItem>
              </SelectContent>
            </Select>
          </div>
        }
      >
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Spot</TableHead>
                <TableHead className="text-right">Stack</TableHead>
                <TableHead>Posição</TableHead>
                <TableHead>Mão</TableHead>
                <TableHead>Ação tomada</TableHead>
                <TableHead>Ação correta</TableHead>
                <TableHead className="text-right">EV</TableHead>
                <TableHead className="text-right">Ação</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {spotsQ.isLoading ? (
                <TableRow>
                  <TableCell colSpan={8} className="py-8 text-center text-sm text-muted-foreground">
                    Carregando (roda o solver de Nash sobre todas as mãos)…
                  </TableCell>
                </TableRow>
              ) : filteredSpots.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={8} className="py-8 text-center text-sm text-muted-foreground">
                    Nenhum spot encontrado.
                  </TableCell>
                </TableRow>
              ) : (
                filteredSpots.slice(0, 100).map((s) => (
                  <TableRow key={s.hand_id}>
                    <TableCell className="text-sm">{s.spot}</TableCell>
                    <TableCell className="num text-right text-xs">{s.stack}</TableCell>
                    <TableCell>
                      <Badge variant="secondary" className="num text-[10px]">
                        {s.position}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      {s.hero_cards ? (
                        <Hole cards={s.hero_cards.split(" ")} size="sm" />
                      ) : (
                        <span className="text-xs text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell
                      className={cn(
                        "num text-xs",
                        s.taken === s.correct ? "text-profit" : "text-loss",
                      )}
                    >
                      {s.taken}
                    </TableCell>
                    <TableCell className="num text-xs">{s.correct}</TableCell>
                    <TableCell className="text-right text-xs">
                      <Money value={s.ev} suffix=" BB" />
                    </TableCell>
                    <TableCell className="text-right">
                      <Button variant="outline" size="sm" asChild>
                        <Link to="/replayer" search={{ site: s.site, handId: s.hand_id }}>
                          Ver mão
                        </Link>
                      </Button>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      </Panel>
    </div>
  );
}
