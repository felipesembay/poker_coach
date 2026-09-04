import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowUpRight, Brain } from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
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
  bankrollCurve,
  dashboardStats,
  handMatrix,
  sessionCalendar,
  sessions,
} from "@/lib/mock-data";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Dashboard — PokerLab" },
      {
        name: "description",
        content:
          "Acompanhe lucro, ROI, ABI, ITM, bankroll e a evolução técnica das suas sessões de MTT.",
      },
      { property: "og:title", content: "Dashboard — PokerLab" },
      {
        property: "og:description",
        content: "Painel de performance MTT com gráficos, heatmap de mãos e resumo por IA.",
      },
    ],
  }),
  component: Dashboard,
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

function Dashboard() {
  return (
    <div className="space-y-5">
      <PageHeader
        title="Dashboard"
        description="Resumo técnico dos últimos 90 dias · 1.842 torneios analisados"
        actions={
          <>
            <Button variant="outline" size="sm">
              Últimos 90 dias
            </Button>
            <Button size="sm" asChild>
              <Link to="/maos">Importar hand history</Link>
            </Button>
          </>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4 xl:grid-cols-8">
        {dashboardStats.map((s) => (
          <StatCard key={s.label} {...s} />
        ))}
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Panel
          title="Bankroll"
          subtitle="Evolução mensal em dólares"
          className="xl:col-span-2"
          actions={
            <Badge variant="outline" className="num text-profit">
              +$860 no mês
            </Badge>
          }
        >
          <div className="h-64 px-2 py-4">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={bankrollCurve}>
                <defs>
                  <linearGradient id="brGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--chart-1)" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="var(--chart-1)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="var(--border)" vertical={false} />
                <XAxis dataKey="d" {...axis} />
                <YAxis {...axis} width={44} />
                <Tooltip contentStyle={tooltipStyle} />
                <Area
                  type="monotone"
                  dataKey="bankroll"
                  stroke="var(--chart-1)"
                  strokeWidth={2}
                  fill="url(#brGrad)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel title="ROI" subtitle="Retorno por mês (%)">
          <div className="h-64 px-2 py-4">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={bankrollCurve}>
                <CartesianGrid stroke="var(--border)" vertical={false} />
                <XAxis dataKey="d" {...axis} />
                <YAxis {...axis} width={36} />
                <Tooltip contentStyle={tooltipStyle} />
                <Line
                  type="monotone"
                  dataKey="roi"
                  stroke="var(--chart-3)"
                  strokeWidth={2}
                  dot={{ r: 2.5, fill: "var(--chart-3)" }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Panel
          title="Lucro mensal"
          subtitle="Verde = lucro · Vermelho = perda"
          className="xl:col-span-2"
        >
          <div className="h-56 px-2 py-4">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={bankrollCurve}>
                <CartesianGrid stroke="var(--border)" vertical={false} />
                <XAxis dataKey="d" {...axis} />
                <YAxis {...axis} width={48} />
                <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "var(--accent)" }} />
                <Bar dataKey="profit" radius={[3, 3, 0, 0]}>
                  {bankrollCurve.map((p) => (
                    <Cell key={p.d} fill={p.profit >= 0 ? "var(--profit)" : "var(--loss)"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel title="Heatmap de mãos" subtitle="Frequência de jogo por combinação">
          <div className="p-4">
            <div className="grid grid-cols-13 gap-[2px]">
              {handMatrix.map((h) => (
                <div
                  key={h.label}
                  title={`${h.label} · ${Math.round(h.value * 100)}%`}
                  className="aspect-square rounded-[2px] transition-transform hover:scale-125"
                  style={{
                    backgroundColor: `color-mix(in oklab, var(--primary) ${Math.round(h.value * 100)}%, var(--elevated))`,
                  }}
                />
              ))}
            </div>
            <div className="num mt-3 flex items-center justify-between text-[10px] text-muted-foreground">
              <span>AA</span>
              <span>Menos jogada → mais jogada</span>
              <span>22</span>
            </div>
          </div>
        </Panel>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Panel title="Calendário de sessões" subtitle="Últimas 5 semanas">
          <div className="p-4">
            <div className="grid grid-cols-7 gap-1.5">
              {sessionCalendar.map((day) => (
                <div
                  key={day.day}
                  title={
                    day.played
                      ? `Dia ${day.day} · ${day.profit} USD`
                      : `Dia ${day.day} · sem sessão`
                  }
                  className={cn(
                    "num grid aspect-square place-items-center rounded-md border border-border text-[10px] transition-colors",
                    !day.played && "bg-elevated/40 text-muted-foreground/50",
                    day.played && day.profit >= 0 && "bg-profit/15 text-profit",
                    day.played && day.profit < 0 && "bg-loss/15 text-loss",
                  )}
                >
                  {day.day}
                </div>
              ))}
            </div>
          </div>
        </Panel>

        <Panel
          title="Últimas sessões"
          subtitle="4 registros recentes"
          className="xl:col-span-2"
          actions={
            <Button variant="ghost" size="sm" asChild>
              <Link to="/sessoes">
                Ver todas <ArrowUpRight className="ml-1 size-3.5" />
              </Link>
            </Button>
          }
        >
          <ul className="divide-y divide-border">
            {sessions.slice(0, 4).map((s) => (
              <li
                key={s.id}
                className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 px-4 py-3 transition-colors hover:bg-accent/40"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">
                    {s.room} · <span className="num">{s.tournaments}</span> torneios
                  </p>
                  <p className="num truncate text-xs text-muted-foreground">
                    {s.date} · {s.duration} · {s.hands} mãos
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-4">
                  <span className="num text-xs text-muted-foreground">ROI {s.roi}%</span>
                  <Money value={s.profit} suffix=" USD" />
                </div>
              </li>
            ))}
          </ul>
        </Panel>
      </div>

      <Panel title="Resumo da IA" subtitle="Gerado a partir das suas 3 últimas sessões">
        <div className="space-y-3 p-4 text-sm leading-relaxed">
          <div className="flex items-center gap-2 text-primary">
            <Brain className="size-4" />
            <span className="text-xs font-semibold uppercase tracking-[0.14em]">Coach IA</span>
          </div>
          <p>
            Sua amostra recente mostra <strong>ROI de 18,4%</strong> — acima da média de 90 dias. O
            volume está consistente e a seleção de mesas melhorou.
          </p>
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="rounded-md border border-border bg-elevated/50 p-3">
              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-loss">
                Principal erro
              </p>
              <p className="mt-1 text-sm">Fold excessivo entre 12 e 18 BB (9 spots)</p>
            </div>
            <div className="rounded-md border border-border bg-elevated/50 p-3">
              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-profit">
                Principal acerto
              </p>
              <p className="mt-1 text-sm">Steals do BTN com frequência de 42%</p>
            </div>
            <div className="rounded-md border border-border bg-elevated/50 p-3">
              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-primary">
                Objetivo de amanhã
              </p>
              <p className="mt-1 text-sm">15 min no treinador de Push/Fold</p>
            </div>
          </div>
          <Button variant="outline" size="sm" asChild>
            <Link to="/coach">Abrir conversa com o Coach IA</Link>
          </Button>
        </div>
      </Panel>
    </div>
  );
}
