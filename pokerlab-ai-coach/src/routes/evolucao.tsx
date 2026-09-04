import { createFileRoute } from "@tanstack/react-router";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { PageHeader, Panel, StatCard } from "@/components/lab";
import { Progress } from "@/components/ui/progress";
import { bankrollCurve, evolutionCurve, goals } from "@/lib/mock-data";

export const Route = createFileRoute("/evolucao")({
  head: () => ({
    meta: [
      { title: "Evolução — PokerLab" },
      {
        name: "description",
        content: "Acompanhe precisão de push/fold e ICM, ROI, lucro, leaks corrigidos e metas.",
      },
      { property: "og:title", content: "Evolução — PokerLab" },
      { property: "og:description", content: "Curvas de progresso técnico do seu jogo de MTT." },
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

function EvolutionPage() {
  return (
    <div className="space-y-5">
      <PageHeader
        title="Evolução"
        description="Progresso técnico dos últimos 6 meses · 14 leaks corrigidos"
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="Precisão Push/Fold" value="91%" delta="+20 pp em 6 meses" tone="profit" />
        <StatCard label="Precisão ICM" value="84%" delta="+22 pp em 6 meses" tone="profit" />
        <StatCard label="ROI" value="18,4%" delta="+12 pp" tone="profit" />
        <StatCard label="Leaks corrigidos" value="14" delta="+12" tone="profit" />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title="Precisão técnica" subtitle="Push/Fold e ICM (%)">
          <div className="h-64 px-2 py-4">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={evolutionCurve}>
                <CartesianGrid stroke="var(--border)" vertical={false} />
                <XAxis dataKey="d" {...axis} />
                <YAxis {...axis} width={34} domain={[50, 100]} />
                <Tooltip contentStyle={tooltipStyle} />
                <Line
                  type="monotone"
                  dataKey="pushfold"
                  stroke="var(--chart-1)"
                  strokeWidth={2}
                  dot={false}
                />
                <Line
                  type="monotone"
                  dataKey="icm"
                  stroke="var(--chart-3)"
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel title="Lucro e ROI" subtitle="Resultado financeiro acumulado">
          <div className="h-64 px-2 py-4">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={bankrollCurve}>
                <CartesianGrid stroke="var(--border)" vertical={false} />
                <XAxis dataKey="d" {...axis} />
                <YAxis {...axis} width={44} />
                <Tooltip contentStyle={tooltipStyle} />
                <Line
                  type="monotone"
                  dataKey="profit"
                  stroke="var(--profit)"
                  strokeWidth={2}
                  dot={false}
                />
                <Line
                  type="monotone"
                  dataKey="roi"
                  stroke="var(--chart-1)"
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title="Leaks corrigidos" subtitle="Acumulado por mês">
          <div className="h-56 px-2 py-4">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={evolutionCurve}>
                <CartesianGrid stroke="var(--border)" vertical={false} />
                <XAxis dataKey="d" {...axis} />
                <YAxis {...axis} width={30} />
                <Tooltip contentStyle={tooltipStyle} />
                <Line
                  type="monotone"
                  dataKey="leaks"
                  stroke="var(--chart-2)"
                  strokeWidth={2}
                  dot={{ r: 2.5 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel title="Metas" subtitle="Trimestre atual">
          <ul className="divide-y divide-border">
            {goals.map((g) => (
              <li key={g.name} className="px-4 py-3">
                <div className="flex items-center justify-between gap-3">
                  <span className="truncate text-sm">{g.name}</span>
                  <span className="num shrink-0 text-xs text-muted-foreground">
                    {g.current} / {g.target}
                  </span>
                </div>
                <Progress value={(g.current / g.target) * 100} className="mt-2 h-1.5" />
              </li>
            ))}
          </ul>
        </Panel>
      </div>
    </div>
  );
}
