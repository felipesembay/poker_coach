import { createFileRoute } from "@tanstack/react-router";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  PolarAngleAxis,
  PolarGrid,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { PageHeader, Panel, StatCard } from "@/components/lab";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
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
import { leaks } from "@/lib/mock-data";

export const Route = createFileRoute("/estatisticas")({
  head: () => ({
    meta: [
      { title: "Estatísticas — PokerLab" },
      {
        name: "description",
        content:
          "Estatísticas avançadas por posição, street e stack, com detecção automática de leaks.",
      },
      { property: "og:title", content: "Estatísticas — PokerLab" },
      {
        property: "og:description",
        content: "VPIP, PFR, 3-bet, steal, WTSD e leaks detectados automaticamente.",
      },
    ],
  }),
  component: StatsPage,
});

const byPosition = [
  { pos: "UTG", vpip: 14, pfr: 12 },
  { pos: "HJ", vpip: 18, pfr: 16 },
  { pos: "CO", vpip: 24, pfr: 21 },
  { pos: "BTN", vpip: 36, pfr: 33 },
  { pos: "SB", vpip: 28, pfr: 22 },
  { pos: "BB", vpip: 31, pfr: 11 },
];

const radar = [
  { metric: "Preflop", you: 82, field: 66 },
  { metric: "Push/Fold", you: 91, field: 71 },
  { metric: "ICM", you: 84, field: 68 },
  { metric: "Postflop", you: 74, field: 70 },
  { metric: "Bluffs", you: 68, field: 62 },
  { metric: "Hero Calls", you: 79, field: 64 },
];

const core = [
  { label: "VPIP", value: "22,4%", hint: "Referência: 21–25%" },
  { label: "PFR", value: "18,9%", hint: "Referência: 17–21%" },
  { label: "3-Bet", value: "6,2%", hint: "Baixo para MTT moderno" },
  { label: "Steal BTN", value: "42,0%", hint: "Bem calibrado" },
  { label: "Fold vs Steal", value: "58,1%", hint: "Levemente alto" },
  { label: "WTSD", value: "26,7%", hint: "Referência: 25–28%" },
  { label: "WSD", value: "51,2%", hint: "Sólido" },
  { label: "AF", value: "2,4", hint: "Agressão equilibrada" },
];

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

function StatsPage() {
  return (
    <div className="space-y-5">
      <PageHeader
        title="Estatísticas"
        description="Amostra de 8.923 mãos · comparativo com o campo de micro/low stakes"
        actions={
          <Select defaultValue="all">
            <SelectTrigger className="h-9 w-[170px] text-sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todas as fases</SelectItem>
              <SelectItem value="early">Fase inicial</SelectItem>
              <SelectItem value="mid">Fase média</SelectItem>
              <SelectItem value="bubble">Bolha</SelectItem>
              <SelectItem value="ft">Mesa final</SelectItem>
            </SelectContent>
          </Select>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4 xl:grid-cols-8">
        {core.map((c) => (
          <StatCard key={c.label} label={c.label} value={c.value} hint={c.hint} />
        ))}
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Panel
          title="VPIP e PFR por posição"
          subtitle="Percentual de mãos"
          className="xl:col-span-2"
        >
          <div className="h-72 px-2 py-4">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={byPosition}>
                <CartesianGrid stroke="var(--border)" vertical={false} />
                <XAxis dataKey="pos" {...axis} />
                <YAxis {...axis} width={34} />
                <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "var(--accent)" }} />
                <Bar dataKey="vpip" fill="var(--chart-1)" radius={[3, 3, 0, 0]} />
                <Bar dataKey="pfr" fill="var(--chart-3)" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel title="Perfil técnico" subtitle="Você vs campo">
          <div className="h-72 px-2 py-4">
            <ResponsiveContainer width="100%" height="100%">
              <RadarChart data={radar} outerRadius="72%">
                <PolarGrid stroke="var(--border)" />
                <PolarAngleAxis
                  dataKey="metric"
                  tick={{ fill: "var(--muted-foreground)", fontSize: 10 }}
                />
                <Tooltip contentStyle={tooltipStyle} />
                <Radar
                  dataKey="field"
                  stroke="var(--chart-5)"
                  fill="var(--chart-5)"
                  fillOpacity={0.12}
                />
                <Radar
                  dataKey="you"
                  stroke="var(--chart-1)"
                  fill="var(--chart-1)"
                  fillOpacity={0.25}
                />
              </RadarChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      </div>

      <Panel
        title="Leaks detectados automaticamente"
        subtitle="Ordenados por EV perdido"
        actions={
          <div className="flex items-center gap-2">
            <Input placeholder="Pesquisar leak…" className="h-8 w-40 text-xs" />
            <Button variant="outline" size="sm">
              Criar plano de estudo
            </Button>
          </div>
        }
      >
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Leak</TableHead>
                <TableHead>Severidade</TableHead>
                <TableHead className="text-right">EV perdido</TableHead>
                <TableHead className="text-right">Ocorrências</TableHead>
                <TableHead className="w-40">Correção</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {leaks.map((l) => (
                <TableRow key={l.name}>
                  <TableCell className="text-sm">{l.name}</TableCell>
                  <TableCell>
                    <Badge
                      variant="outline"
                      className={
                        l.severity === "Alto"
                          ? "text-loss"
                          : l.severity === "Médio"
                            ? "text-foreground"
                            : "text-muted-foreground"
                      }
                    >
                      {l.severity}
                    </Badge>
                  </TableCell>
                  <TableCell className="num text-right text-xs text-loss">{l.evLost}</TableCell>
                  <TableCell className="num text-right text-xs">{l.occurrences}</TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <Progress value={Math.max(6, 50 + l.trend * 4)} className="h-1.5" />
                      <span className="num text-[11px] text-muted-foreground">
                        {l.trend > 0 ? "+" : ""}
                        {l.trend}%
                      </span>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </Panel>

      <Panel title="EV por faixa de stack" subtitle="BB/100 ganho ou perdido">
        <div className="h-56 px-2 py-4">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={[
                { range: "< 10 BB", ev: 2.1 },
                { range: "10–15 BB", ev: -3.4 },
                { range: "15–20 BB", ev: -1.8 },
                { range: "20–30 BB", ev: 1.2 },
                { range: "30–50 BB", ev: 2.8 },
                { range: "50+ BB", ev: 0.6 },
              ]}
            >
              <CartesianGrid stroke="var(--border)" vertical={false} />
              <XAxis dataKey="range" {...axis} />
              <YAxis {...axis} width={38} />
              <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "var(--accent)" }} />
              <Bar dataKey="ev" radius={[3, 3, 0, 0]}>
                {[2.1, -3.4, -1.8, 1.2, 2.8, 0.6].map((v, i) => (
                  <Cell key={i} fill={v >= 0 ? "var(--profit)" : "var(--loss)"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Panel>
    </div>
  );
}
