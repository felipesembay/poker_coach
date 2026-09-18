import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { X } from "lucide-react";
import { useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Money, PageHeader, Panel, StatCard } from "@/components/lab";
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
import { trainerApi } from "@/lib/api";

export const Route = createFileRoute("/evolucao")({
  head: () => ({
    meta: [
      { title: "Evolução Push/Fold — PokerLab" },
      {
        name: "description",
        content:
          "Acompanhe sua evolução no treino de Push/Fold dia a dia — acertos, volume e EV perdido.",
      },
      { property: "og:title", content: "Evolução Push/Fold — PokerLab" },
      {
        property: "og:description",
        content: "Histórico e gráficos do Modo Estudo, com cruzamento com os torneios do dia.",
      },
    ],
  }),
  component: EvolutionPage,
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

function fmtDateShort(iso: string): string {
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${(y ?? "").slice(2)}`;
}

function fmtDuration(min: number): string {
  if (min <= 0) return "—";
  const h = Math.floor(min / 60);
  const m = Math.round(min % 60);
  if (h === 0) return `${m}min`;
  return `${h}h ${m}min`;
}

function EvolutionPage() {
  const byDayQ = useQuery({ queryKey: ["pushfold-training-by-day"], queryFn: trainerApi.byDay });
  const days = byDayQ.data ?? []; // já vem ordenado desc (dia mais recente primeiro)

  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const detailQ = useQuery({
    queryKey: ["pushfold-training-day", selectedDate],
    queryFn: () => trainerApi.byDayDetail(selectedDate!),
    enabled: !!selectedDate,
  });

  // Gráficos precisam de ordem cronológica crescente (dias já vêm desc).
  const chartData = useMemo(() => {
    const asc = [...days].reverse();
    return asc.map((d, i) => {
      const windowStart = Math.max(0, i - 6);
      const window = asc.slice(windowStart, i + 1).filter((w) => w.accuracy_pct != null);
      const movingAvg = window.length
        ? window.reduce((acc, w) => acc + (w.accuracy_pct ?? 0), 0) / window.length
        : null;
      return { ...d, moving_avg_7: movingAvg };
    });
  }, [days]);

  const totalHands = days.reduce((acc, d) => acc + d.hands, 0);
  const totalCorrect = days.reduce((acc, d) => acc + d.correct, 0);
  const overallAccuracy = totalHands ? (totalCorrect / totalHands) * 100 : null;
  const bestDay = days.length
    ? days.reduce((a, b) => ((b.accuracy_pct ?? -1) > (a.accuracy_pct ?? -1) ? b : a))
    : null;

  return (
    <div className="space-y-5">
      <PageHeader
        title="Evolução Push/Fold"
        description={
          days.length
            ? `${days.length} dia${days.length === 1 ? "" : "s"} de treino · ${totalHands} mãos no total`
            : "Sem treino registrado ainda — jogue algumas mãos no Modo Estudo."
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard
          label="Dias de treino"
          value={String(days.length)}
          delta={days.length ? `${totalHands} mãos` : "—"}
          tone="neutral"
        />
        <StatCard
          label="Accuracy geral"
          value={overallAccuracy != null ? `${overallAccuracy.toFixed(1)}%` : "—"}
          delta={`${totalCorrect}/${totalHands} corretas`}
          tone={overallAccuracy != null && overallAccuracy >= 70 ? "profit" : "neutral"}
        />
        <StatCard
          label="Melhor dia"
          value={bestDay?.accuracy_pct != null ? `${bestDay.accuracy_pct.toFixed(1)}%` : "—"}
          delta={bestDay ? fmtDateShort(bestDay.date) : "Sem dado"}
          tone={bestDay ? "profit" : "neutral"}
        />
        <StatCard
          label="Tempo de treino"
          value={fmtDuration(days.reduce((acc, d) => acc + d.duration_min, 0))}
          delta="Aproximado — 1ª à última resposta do dia"
          tone="neutral"
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title="Accuracy diária" subtitle="% de acerto por dia · média móvel de 7 dias">
          <div className="h-64 px-2 py-4">
            {chartData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData}>
                  <CartesianGrid stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="date" {...axis} tickFormatter={fmtDateShort} minTickGap={30} />
                  <YAxis {...axis} width={34} domain={[0, 100]} />
                  <Tooltip
                    contentStyle={tooltipStyle}
                    labelFormatter={fmtDateShort}
                    formatter={(v: number, name: string) => [
                      `${v.toFixed(1)}%`,
                      name === "moving_avg_7" ? "Média móvel (7d)" : "Accuracy",
                    ]}
                  />
                  <Line
                    type="monotone"
                    dataKey="accuracy_pct"
                    stroke="var(--chart-1)"
                    strokeWidth={2}
                    dot={{ r: 2.5 }}
                  />
                  <Line
                    type="monotone"
                    dataKey="moving_avg_7"
                    stroke="var(--chart-3)"
                    strokeWidth={2}
                    strokeDasharray="4 3"
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="grid h-full place-items-center text-sm text-muted-foreground">
                {byDayQ.isLoading ? "Carregando…" : "Sem treino registrado ainda."}
              </div>
            )}
          </div>
        </Panel>

        <Panel title="Volume de treino" subtitle="Mãos treinadas por dia">
          <div className="h-64 px-2 py-4">
            {chartData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData}>
                  <CartesianGrid stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="date" {...axis} tickFormatter={fmtDateShort} minTickGap={30} />
                  <YAxis {...axis} width={34} />
                  <Tooltip
                    contentStyle={tooltipStyle}
                    cursor={{ fill: "var(--accent)" }}
                    labelFormatter={fmtDateShort}
                    formatter={(v: number) => [v, "Mãos"]}
                  />
                  <Bar dataKey="hands" radius={[3, 3, 0, 0]} fill="var(--chart-1)" />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="grid h-full place-items-center text-sm text-muted-foreground">
                {byDayQ.isLoading ? "Carregando…" : "Sem treino registrado ainda."}
              </div>
            )}
          </div>
        </Panel>
      </div>

      <Panel title="Histórico por dia" subtitle="Clique num dia pra ver o detalhe e as mãos treinadas">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Data</TableHead>
                <TableHead className="text-right">Mãos</TableHead>
                <TableHead className="text-right">Acertos</TableHead>
                <TableHead className="text-right">Accuracy</TableHead>
                <TableHead className="text-right">EV perdido (média)</TableHead>
                <TableHead className="text-right">Duração</TableHead>
                <TableHead className="text-right">Ação</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {byDayQ.isLoading && (
                <TableRow>
                  <TableCell colSpan={7} className="py-10 text-center text-sm text-muted-foreground">
                    Carregando…
                  </TableCell>
                </TableRow>
              )}
              {!byDayQ.isLoading && days.length === 0 && (
                <TableRow>
                  <TableCell colSpan={7} className="py-10 text-center text-sm text-muted-foreground">
                    Nenhum dia de treino ainda.
                  </TableCell>
                </TableRow>
              )}
              {days.map((d) => (
                <TableRow
                  key={d.date}
                  className={cnRow(selectedDate === d.date)}
                  onClick={() => setSelectedDate(d.date === selectedDate ? null : d.date)}
                >
                  <TableCell className="num text-xs">{fmtDateShort(d.date)}</TableCell>
                  <TableCell className="num text-right text-xs">{d.hands}</TableCell>
                  <TableCell className="num text-right text-xs">{d.correct}</TableCell>
                  <TableCell className="text-right text-xs">
                    {d.accuracy_pct != null ? (
                      <Badge
                        variant="outline"
                        className={d.accuracy_pct >= 70 ? "text-profit" : "text-loss"}
                      >
                        {d.accuracy_pct.toFixed(1)}%
                      </Badge>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  <TableCell className="text-right text-xs">
                    {d.avg_ev_lost_bb != null ? (
                      <Money value={-d.avg_ev_lost_bb} suffix=" BB" />
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  <TableCell className="num text-right text-xs text-muted-foreground">
                    {fmtDuration(d.duration_min)}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedDate(d.date === selectedDate ? null : d.date);
                      }}
                    >
                      {selectedDate === d.date ? "Fechar" : "Ver dia"}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </Panel>

      {selectedDate && (
        <Panel
          title={`Detalhe — ${fmtDateShort(selectedDate)}`}
          subtitle="Mãos treinadas, stacks trabalhados e torneios jogados no mesmo dia"
          actions={
            <Button variant="ghost" size="icon" className="size-7" onClick={() => setSelectedDate(null)}>
              <X className="size-4" />
            </Button>
          }
        >
          {detailQ.isLoading ? (
            <p className="p-4 text-sm text-muted-foreground">Carregando…</p>
          ) : detailQ.data ? (
            <div className="space-y-4 p-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="rounded-md border border-border bg-elevated/50 p-3 text-sm">
                  <p className="text-xs uppercase tracking-[0.1em] text-muted-foreground">
                    Stacks trabalhados
                  </p>
                  {detailQ.data.stack_buckets.length > 0 ? (
                    <ul className="mt-1 space-y-1">
                      {detailQ.data.stack_buckets.map((b) => (
                        <li key={b.bucket} className="flex items-center justify-between">
                          <span className="num text-xs">{b.bucket}</span>
                          <span className="num text-xs text-muted-foreground">{b.hands} mãos</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="mt-1 text-xs text-muted-foreground">Sem stack identificado.</p>
                  )}
                </div>

                <div className="rounded-md border border-border bg-elevated/50 p-3 text-sm">
                  <p className="text-xs uppercase tracking-[0.1em] text-muted-foreground">
                    Torneios jogados nesse dia
                  </p>
                  {detailQ.data.sessions.length > 0 ? (
                    <ul className="mt-1 space-y-1">
                      {detailQ.data.sessions.map((s) => (
                        <li key={s.site} className="flex items-center justify-between">
                          <span className="text-xs">
                            {s.site} · {s.tournaments} torneio{s.tournaments === 1 ? "" : "s"}
                          </span>
                          {s.profit != null ? (
                            <Money value={s.profit} />
                          ) : (
                            <span className="text-xs text-muted-foreground">sem resultado</span>
                          )}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="mt-1 text-xs text-muted-foreground">
                      Nenhum torneio jogado nesse dia (só treino).
                    </p>
                  )}
                </div>
              </div>

              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow className="hover:bg-transparent">
                      <TableHead>Hora</TableHead>
                      <TableHead>Posição</TableHead>
                      <TableHead className="text-right">Stack</TableHead>
                      <TableHead>Sua decisão</TableHead>
                      <TableHead>Nash</TableHead>
                      <TableHead className="text-right">EV perdido</TableHead>
                      <TableHead className="text-right">Mão</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {detailQ.data.answers.map((a, i) => (
                      <TableRow key={`${a.site}-${a.hand_id}-${i}`}>
                        <TableCell className="num text-xs text-muted-foreground">
                          {a.ts.slice(11, 16)}
                        </TableCell>
                        <TableCell className="text-xs">{a.hero_position ?? "—"}</TableCell>
                        <TableCell className="num text-right text-xs">
                          {a.hero_stack_bb != null ? `${a.hero_stack_bb.toFixed(1)} BB` : "—"}
                        </TableCell>
                        <TableCell className="text-xs capitalize">{a.user_decision}</TableCell>
                        <TableCell className="text-xs capitalize text-muted-foreground">
                          {a.nash_decision}
                        </TableCell>
                        <TableCell className="text-right text-xs">
                          {a.correct ? (
                            <Badge variant="outline" className="text-profit">
                              correto
                            </Badge>
                          ) : (
                            <Badge variant="outline" className="text-loss">
                              −{(a.ev_lost_bb ?? 0).toFixed(2)} BB
                            </Badge>
                          )}
                        </TableCell>
                        <TableCell className="text-right">
                          <Button variant="outline" size="sm" asChild>
                            <Link
                              to="/replayer"
                              search={{ site: a.site, handId: a.hand_id }}
                            >
                              Abrir
                            </Link>
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </div>
          ) : (
            <p className="p-4 text-sm text-muted-foreground">Sem dados pra esse dia.</p>
          )}
        </Panel>
      )}
    </div>
  );
}

function cnRow(active: boolean): string {
  return active
    ? "cursor-pointer bg-accent/60"
    : "cursor-pointer hover:bg-accent/30";
}
