import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { ArrowUpRight } from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Hole, PageHeader, Panel, StatCard } from "@/components/lab";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
import { leaksApi, type DecisionScope, type LeakCategory } from "@/lib/api";

export const Route = createFileRoute("/leaks")({
  head: () => ({
    meta: [
      { title: "Leak Finder — PokerLab" },
      {
        name: "description",
        content:
          "Categorias de decisão com maior EV perdido frente à referência de Nash — clique para revisar as mãos.",
      },
      { property: "og:title", content: "Leak Finder — PokerLab" },
      {
        property: "og:description",
        content: "Onde suas decisões de push/fold mais destoam do equilíbrio, por posição e stack.",
      },
    ],
  }),
  component: LeaksPage,
});

const axis = {
  stroke: "var(--muted-foreground)",
  fontSize: 11,
  tickLine: false,
  axisLine: false,
};

const tooltipStyle = {
  background: "var(--popover)",
  border: "1px solid var(--border)",
  borderRadius: 8,
  fontSize: 12,
  fontFamily: "var(--font-mono)",
};

const SCOPE_LABEL: Record<DecisionScope, string> = {
  open_shove: "Abertura (push/fold)",
  facing_shove: "Call vs. shove",
};

function categoryLabel(c: LeakCategory): string {
  return `${SCOPE_LABEL[c.decision_scope]} · ${c.position} · ${c.stack_bucket}`;
}

function LeaksPage() {
  const [scope, setScope] = useState<"all" | DecisionScope>("all");
  const [selected, setSelected] = useState<LeakCategory | null>(null);

  const categoriesQ = useQuery({
    queryKey: ["leak-categories"],
    queryFn: () => leaksApi.categories({ bb_min: 1, bb_max: 25 }),
  });

  const categories = useMemo(() => {
    const rows = categoriesQ.data ?? [];
    return scope === "all" ? rows : rows.filter((r) => r.decision_scope === scope);
  }, [categoriesQ.data, scope]);

  const chartData = categories.slice(0, 12).map((c) => ({ ...c, label: categoryLabel(c) }));

  const handsQ = useQuery({
    queryKey: ["leak-hands", selected?.category_key],
    queryFn: () =>
      leaksApi.hands({
        decision_scope: selected!.decision_scope,
        position: selected!.position,
        stack_bucket: selected!.stack_bucket,
        bb_min: 1,
        bb_max: 25,
      }),
    enabled: !!selected,
  });

  const totalEvLost = (categoriesQ.data ?? []).reduce((s, c) => s + c.ev_lost_total_bb, 0);
  const totalOpportunities = (categoriesQ.data ?? []).reduce((s, c) => s + c.opportunities, 0);
  const totalIncorrect = (categoriesQ.data ?? []).reduce((s, c) => s + c.incorrect, 0);

  return (
    <div className="space-y-5">
      <PageHeader
        title="Leak Finder"
        description="Categorias de decisão (posição × faixa de stack) ordenadas pelo EV perdido frente à referência de Nash — não é análise de resultado, é análise de decisão."
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard
          label="EV perdido total"
          value={categoriesQ.data ? `-${totalEvLost.toFixed(1)} BB` : "—"}
          tone="loss"
        />
        <StatCard
          label="Oportunidades avaliadas"
          value={categoriesQ.data ? String(totalOpportunities) : "—"}
        />
        <StatCard
          label="Decisões incorretas"
          value={categoriesQ.data ? String(totalIncorrect) : "—"}
          tone="loss"
        />
        <StatCard
          label="Categorias com leak"
          value={categoriesQ.data ? String(categories.filter((c) => c.incorrect > 0).length) : "—"}
        />
      </div>

      <Panel
        title="EV perdido por categoria"
        subtitle="Escopo: abertura preflop (push/fold) e call vs. all-in — mesmo motor de Nash do módulo Push/Fold"
        actions={
          <Select value={scope} onValueChange={(v) => setScope(v as "all" | DecisionScope)}>
            <SelectTrigger className="h-8 w-44 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todos os escopos</SelectItem>
              <SelectItem value="open_shove">Abertura (push/fold)</SelectItem>
              <SelectItem value="facing_shove">Call vs. shove</SelectItem>
            </SelectContent>
          </Select>
        }
      >
        <div className="h-80 px-2 py-4">
          {chartData.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} layout="vertical" margin={{ left: 24 }}>
                <CartesianGrid stroke="var(--border)" horizontal={false} />
                <XAxis type="number" {...axis} />
                <YAxis type="category" dataKey="label" {...axis} width={200} />
                <Tooltip
                  contentStyle={tooltipStyle}
                  cursor={{ fill: "var(--accent)" }}
                  formatter={(v: number, _n, p) => [
                    `-${v} BB (${p.payload.opportunities} oportunidades, ${p.payload.error_rate_pct}% erro)`,
                    "EV perdido",
                  ]}
                />
                <Bar
                  dataKey="ev_lost_total_bb"
                  radius={[0, 3, 3, 0]}
                  fill="var(--loss)"
                  cursor="pointer"
                  onClick={(d) => setSelected(d as unknown as LeakCategory)}
                >
                  {chartData.map((c) => (
                    <Cell key={c.category_key} fillOpacity={selected?.category_key === c.category_key ? 1 : 0.75} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="grid h-full place-items-center text-sm text-muted-foreground">
              {categoriesQ.isLoading
                ? "Carregando…"
                : "Sem spots de push/fold suficientes ainda (stack 1–25 BB)."}
            </div>
          )}
        </div>
      </Panel>

      <Panel
        title="Categorias"
        subtitle="Clique numa linha para revisar as mãos"
      >
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Categoria</TableHead>
                <TableHead className="text-right">Oportunidades</TableHead>
                <TableHead className="text-right">Incorretas</TableHead>
                <TableHead className="text-right">Taxa de erro</TableHead>
                <TableHead className="text-right">EV perdido</TableHead>
                <TableHead className="text-right">EV perdido médio</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {!categoriesQ.isLoading && categories.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6} className="py-10 text-center text-sm text-muted-foreground">
                    Nenhuma categoria encontrada.
                  </TableCell>
                </TableRow>
              )}
              {categories.map((c) => (
                <TableRow
                  key={c.category_key}
                  onClick={() => setSelected(c)}
                  className={
                    selected?.category_key === c.category_key
                      ? "cursor-pointer bg-accent/50"
                      : "cursor-pointer hover:bg-accent/30"
                  }
                >
                  <TableCell className="text-sm font-medium">{categoryLabel(c)}</TableCell>
                  <TableCell className="num text-right text-xs text-muted-foreground">
                    {c.opportunities}
                  </TableCell>
                  <TableCell className="num text-right text-xs">{c.incorrect}</TableCell>
                  <TableCell className="num text-right text-xs">
                    {c.error_rate_pct != null ? `${c.error_rate_pct}%` : "—"}
                  </TableCell>
                  <TableCell className="num text-right text-xs text-loss">
                    -{c.ev_lost_total_bb.toFixed(1)} BB
                  </TableCell>
                  <TableCell className="num text-right text-xs text-muted-foreground">
                    {c.ev_lost_avg_bb != null ? `-${c.ev_lost_avg_bb.toFixed(2)} BB` : "—"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </Panel>

      {selected && (
        <Panel
          title={`Mãos — ${categoryLabel(selected)}`}
          subtitle={`${handsQ.data?.length ?? 0} mãos nessa categoria`}
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
                {!handsQ.isLoading && (handsQ.data ?? []).length === 0 && (
                  <TableRow>
                    <TableCell colSpan={6} className="py-8 text-center text-sm text-muted-foreground">
                      Nenhuma mão encontrada.
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
