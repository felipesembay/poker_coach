import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
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

import { PageHeader, Panel, StatCard } from "@/components/lab";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { pushfoldApi, statsApi } from "@/lib/api";

export const Route = createFileRoute("/estatisticas")({
  head: () => ({
    meta: [
      { title: "Estatísticas — PokerLab" },
      {
        name: "description",
        content:
          "Estatísticas reais por posição e stack, com leaks de push/fold detectados pelo motor de Nash.",
      },
      { property: "og:title", content: "Estatísticas — PokerLab" },
      {
        property: "og:description",
        content: "VPIP, PFR e EV perdido por posição — tudo derivado das suas mãos importadas.",
      },
    ],
  }),
  component: StatsPage,
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

// Bucket arbitrário sobre EV perdido (BB) — mesmo espírito do `risk`
// bucket de ICM (poker_coach.icm): não é escala padrão da indústria,
// só pra colorir a tabela por gravidade relativa.
function severity(evLost: number): "Alto" | "Médio" | "Baixo" {
  if (evLost >= 30) return "Alto";
  if (evLost >= 8) return "Médio";
  return "Baixo";
}

function StatsPage() {
  const overviewQ = useQuery({ queryKey: ["stats-overview"], queryFn: statsApi.overview });
  const positionQ = useQuery({ queryKey: ["stats-position"], queryFn: statsApi.position });
  const stackQ = useQuery({ queryKey: ["stats-stack-buckets"], queryFn: statsApi.stackBuckets });
  const pfSummaryQ = useQuery({
    queryKey: ["pushfold-summary-default"],
    queryFn: () => pushfoldApi.summary(),
  });

  const [search, setSearch] = useState("");

  const ov = overviewQ.data;
  const positions = positionQ.data ?? [];
  const stacks = (stackQ.data ?? []).filter((s) => s.spots > 0);

  const btn = positions.find((p) => p.position === "BTN");

  const leakRows = useMemo(() => {
    const byPos = pfSummaryQ.data?.by_position ?? {};
    const rows = Object.entries(byPos).map(([position, d]) => ({
      position,
      spots: d.spots,
      leaks: d.leaks,
      evLost: d.ev_lost_bb,
      leakPct: d.spots ? Math.round((d.leaks / d.spots) * 100) : 0,
    }));
    rows.sort((a, b) => b.evLost - a.evLost);
    const q = search.trim().toLowerCase();
    return q ? rows.filter((r) => r.position.toLowerCase().includes(q)) : rows;
  }, [pfSummaryQ.data, search]);

  return (
    <div className="space-y-5">
      <PageHeader
        title="Estatísticas"
        description={
          ov
            ? `Amostra de ${ov.hands.toLocaleString("pt-BR")} mãos · leaks de push/fold em stack 5–25 BB`
            : "Carregando…"
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="VPIP" value={ov ? `${ov.vpip_pct}%` : "—"} />
        <StatCard label="PFR" value={ov ? `${ov.pfr_pct}%` : "—"} />
        <StatCard
          label="VPIP no BTN"
          value={btn ? `${btn.vpip_pct}%` : "—"}
          hint={btn ? `${btn.spots} mãos` : "Sem dado"}
        />
        <StatCard
          label="Spots push/fold analisados"
          value={pfSummaryQ.data ? String(pfSummaryQ.data.spots) : "—"}
          hint="Stack 5–25 BB"
        />
        <StatCard
          label="Leaks (decisão ≠ Nash)"
          value={pfSummaryQ.data ? String(pfSummaryQ.data.leak_spots) : "—"}
          tone="loss"
          hint={
            pfSummaryQ.data
              ? `${Math.round((pfSummaryQ.data.leak_spots / pfSummaryQ.data.spots) * 100)}% dos spots`
              : "Sem dado"
          }
        />
        <StatCard
          label="EV perdido (push/fold)"
          value={pfSummaryQ.data ? `-${pfSummaryQ.data.total_ev_lost_bb.toFixed(1)} BB` : "—"}
          tone="loss"
        />
        <StatCard label="ITM" value={ov?.roi ? `${ov.roi.itm_pct}%` : "—"} />
        <StatCard label="Torneios" value={ov ? String(ov.tournaments) : "—"} />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title="VPIP e PFR por posição" subtitle="Percentual de mãos">
          <div className="h-72 px-2 py-4">
            {positions.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={positions}>
                  <CartesianGrid stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="position" {...axis} />
                  <YAxis {...axis} width={34} tickFormatter={(v) => `${v}%`} />
                  <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "var(--accent)" }} />
                  <Bar dataKey="vpip_pct" name="VPIP" fill="var(--chart-1)" radius={[3, 3, 0, 0]} />
                  <Bar dataKey="pfr_pct" name="PFR" fill="var(--chart-3)" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="grid h-full place-items-center text-sm text-muted-foreground">
                {positionQ.isLoading ? "Carregando…" : "Sem mãos com posição identificada ainda."}
              </div>
            )}
          </div>
        </Panel>

        <Panel
          title="EV perdido por posição (push/fold)"
          subtitle="Nash real — quanto sua decisão custou vs. a ótima"
        >
          <div className="h-72 px-2 py-4">
            {leakRows.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={leakRows}>
                  <CartesianGrid stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="position" {...axis} />
                  <YAxis {...axis} width={40} />
                  <Tooltip
                    contentStyle={tooltipStyle}
                    cursor={{ fill: "var(--accent)" }}
                    formatter={(v: number) => [`-${v} BB`, "EV perdido"]}
                  />
                  <Bar dataKey="evLost" radius={[3, 3, 0, 0]} fill="var(--loss)" />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="grid h-full place-items-center text-sm text-muted-foreground">
                {pfSummaryQ.isLoading ? "Carregando…" : "Sem spots de push/fold no range 5–25 BB."}
              </div>
            )}
          </div>
        </Panel>
      </div>

      <Panel
        title="Leaks de push/fold por posição"
        subtitle="Ordenado por EV perdido · motor de Nash (poker_coach.pushfold), não é heurística"
        actions={
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Pesquisar posição…"
            className="h-8 w-40 text-xs"
          />
        }
      >
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Posição</TableHead>
                <TableHead>Severidade</TableHead>
                <TableHead className="text-right">EV perdido</TableHead>
                <TableHead className="text-right">Decisões erradas</TableHead>
                <TableHead className="text-right">Spots</TableHead>
                <TableHead className="text-right">Taxa de leak</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {pfSummaryQ.isLoading && (
                <TableRow>
                  <TableCell
                    colSpan={6}
                    className="py-10 text-center text-sm text-muted-foreground"
                  >
                    Carregando…
                  </TableCell>
                </TableRow>
              )}
              {!pfSummaryQ.isLoading && leakRows.length === 0 && (
                <TableRow>
                  <TableCell
                    colSpan={6}
                    className="py-10 text-center text-sm text-muted-foreground"
                  >
                    Nenhum leak encontrado.
                  </TableCell>
                </TableRow>
              )}
              {leakRows.map((r) => {
                const sev = severity(r.evLost);
                return (
                  <TableRow key={r.position}>
                    <TableCell className="text-sm font-medium">{r.position}</TableCell>
                    <TableCell>
                      <Badge
                        variant="outline"
                        className={
                          sev === "Alto"
                            ? "text-loss"
                            : sev === "Médio"
                              ? "text-foreground"
                              : "text-muted-foreground"
                        }
                      >
                        {sev}
                      </Badge>
                    </TableCell>
                    <TableCell className="num text-right text-xs text-loss">
                      -{r.evLost.toFixed(1)} BB
                    </TableCell>
                    <TableCell className="num text-right text-xs">{r.leaks}</TableCell>
                    <TableCell className="num text-right text-xs text-muted-foreground">
                      {r.spots}
                    </TableCell>
                    <TableCell className="num text-right text-xs text-muted-foreground">
                      {r.leakPct}%
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      </Panel>

      <Panel
        title="Saldo em BB por faixa de stack"
        subtitle="Fold/push/call preflop e resultado por faixa de stack efetivo"
      >
        <div className="h-56 px-2 py-4">
          {stacks.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={stacks}>
                <CartesianGrid stroke="var(--border)" vertical={false} />
                <XAxis dataKey="bucket" {...axis} />
                <YAxis {...axis} width={44} />
                <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "var(--accent)" }} />
                <Bar dataKey="net_bb" radius={[3, 3, 0, 0]}>
                  {stacks.map((s) => (
                    <Cell key={s.bucket} fill={s.net_bb >= 0 ? "var(--profit)" : "var(--loss)"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="grid h-full place-items-center text-sm text-muted-foreground">
              {stackQ.isLoading ? "Carregando…" : "Sem dado ainda."}
            </div>
          )}
        </div>
      </Panel>
    </div>
  );
}
