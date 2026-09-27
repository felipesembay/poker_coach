import { createFileRoute } from "@tanstack/react-router";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { ArrowDown, ArrowUp, ArrowUpDown, Info } from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  LabelList,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip as ChartTooltip,
  XAxis,
  YAxis,
} from "recharts";

import { PageHeader, Panel, StatCard } from "@/components/lab";
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
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import {
  playStyleApi,
  type PlayStyleFilters,
  type PlayStyleFreq,
  type PlayStyleMetricKey,
  type PlayStylePeriod,
  type PlayStyleRow,
  type PlayStyleTournament,
} from "@/lib/api";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/estilo")({
  head: () => ({
    meta: [
      { title: "Estilo de Jogo — PokerLab" },
      {
        name: "description",
        content:
          "VPIP, PFR, 3-Bet, ATS, C-Bet e mais por período, torneio, buy-in, stack e posição — sempre com o tamanho da amostra.",
      },
      { property: "og:title", content: "Estilo de Jogo — PokerLab" },
      {
        property: "og:description",
        content: "Como seu estilo de jogo muda por contexto e ao longo do tempo.",
      },
    ],
  }),
  component: PlayStylePage,
});

// ---------------- constantes ----------------

const axis = {
  stroke: "var(--muted-foreground)",
  fontSize: 11,
  tickLine: false,
  axisLine: false,
};

const tooltipBox =
  "rounded-lg border border-border bg-popover px-3 py-2 font-mono text-xs shadow-md";

// Cor fixa por métrica (segue a métrica em qualquer gráfico/filtro, nunca
// a ordem). Paleta categórica validada p/ fundo escuro (CVD-safe nos pares
// adjacentes); VPIP no mesmo azul do --chart-1 da tela de Estatísticas.
const METRIC_COLOR: Record<PlayStyleMetricKey, string> = {
  vpip: "var(--chart-1)",
  pfr: "#d95926",
  threebet: "#199e70",
  f3b: "#c98500",
  ats: "#d55181",
  fts: "#008300",
  cbet: "#9085e9",
  fcb: "#e66767",
};

const METRIC_LABEL: Record<PlayStyleMetricKey, string> = {
  vpip: "VPIP",
  pfr: "PFR",
  threebet: "3-Bet",
  f3b: "Fold to 3-Bet",
  ats: "ATS",
  fts: "Fold to Steal",
  cbet: "C-Bet",
  fcb: "Fold to C-Bet",
};

const CORE: PlayStyleMetricKey[] = ["vpip", "pfr", "threebet"];
const EVO_METRICS: PlayStyleMetricKey[] = ["vpip", "pfr", "threebet", "f3b", "ats", "cbet"];
const SMALL_SAMPLE = 30;
const ALL = "all";

const PERIODS: { value: PlayStylePeriod; label: string }[] = [
  { value: "all", label: "Todos" },
  { value: "today", label: "Hoje" },
  { value: "7d", label: "Últimos 7 dias" },
  { value: "30d", label: "Últimos 30 dias" },
  { value: "custom", label: "Customizado" },
];

// ---------------- helpers ----------------

const fmtInt = (n: number) => n.toLocaleString("pt-BR");
const fmtPct = (v: number | null | undefined) => (v == null ? "—" : `${v.toFixed(1)}%`);
const fmtMoney = (b: number | null) =>
  b == null ? "?" : b === 0 ? "Freeroll" : `$${b.toFixed(2)}`;
const fmtDate = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleDateString("pt-BR") : "—";
const fmtDateShort = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
const tKey = (t: { site: string; tournament_id: string }) => `${t.site}|${t.tournament_id}`;
const isoDay = (d: Date) => d.toISOString().slice(0, 10);

/** Mesmo recorte de período que a API aplica (poker_coach.player_stats.period_bounds),
 * usado só para restringir a lista de torneios oferecida no filtro. */
function periodRange(period: PlayStylePeriod, from: string, to: string): [string, string] | null {
  const today = new Date();
  const back = (days: number) => isoDay(new Date(today.getTime() - days * 86_400_000));
  if (period === "today") return [isoDay(today), isoDay(today)];
  if (period === "7d") return [back(6), isoDay(today)];
  if (period === "30d") return [back(29), isoDay(today)];
  if (period === "custom" && from && to) return [from, to];
  return null;
}

function tournamentLabel(t: PlayStyleTournament) {
  return `${t.name ?? t.tournament_id} · ${fmtMoney(t.buyin)} · ${fmtDate(t.first_ts)} · ${t.hands} mãos`;
}

/** Valor do gráfico: null (ponto some) quando a amostra da métrica é menor que o mínimo. */
function gated(row: PlayStyleRow, key: PlayStyleMetricKey, minN: number): number | null {
  return row[`${key}_n`] >= minN ? row[key] : null;
}

// ---------------- componentes ----------------

function InfoTip({ text }: { text: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          className="text-muted-foreground transition-colors hover:text-foreground"
          aria-label="Como é calculado"
        >
          <Info className="size-3.5" />
        </button>
      </TooltipTrigger>
      <TooltipContent className="max-w-72 bg-popover text-popover-foreground border border-border">
        {text}
      </TooltipContent>
    </Tooltip>
  );
}

function MetricCard({
  metric,
  pct,
  made,
  opps,
  description,
}: {
  metric: PlayStyleMetricKey;
  pct: number | null;
  made: number;
  opps: number;
  description: string;
}) {
  const unit = metric === "vpip" || metric === "pfr" ? "mãos" : "oportunidades";
  return (
    <div className="panel fade-up p-4 transition-colors hover:border-primary/30">
      <div className="flex items-center gap-1.5">
        <span
          className="size-2 shrink-0 rounded-full"
          style={{ background: METRIC_COLOR[metric] }}
          aria-hidden
        />
        <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
          {METRIC_LABEL[metric]}
        </p>
        <InfoTip text={description} />
      </div>
      <p className="num mt-2 text-2xl font-bold">{fmtPct(pct)}</p>
      <div className="mt-1.5 flex flex-wrap items-center gap-2">
        <span className="num text-xs text-muted-foreground">
          {fmtInt(made)} / {fmtInt(opps)} {unit}
        </span>
        {opps < SMALL_SAMPLE ? (
          <Badge
            variant="outline"
            className="h-5 px-1.5 text-[10px] font-normal text-muted-foreground"
          >
            Amostra pequena
          </Badge>
        ) : null}
      </div>
    </div>
  );
}

type TipEntry = {
  dataKey?: string | number;
  value?: number | null;
  payload?: Record<string, unknown>;
};

function MetricTooltip({
  active,
  payload,
  label,
  labelFormatter,
}: {
  active?: boolean;
  payload?: TipEntry[];
  label?: string | number;
  labelFormatter?: (l: string) => string;
}) {
  if (!active || !payload?.length) return null;
  const row = payload[0]?.payload ?? {};
  const shown = payload.filter(
    (p): p is TipEntry & { dataKey: PlayStyleMetricKey } =>
      typeof p.dataKey === "string" && p.dataKey in METRIC_LABEL && p.value != null,
  );
  return (
    <div className={tooltipBox}>
      <p className="mb-1 font-semibold">{labelFormatter ? labelFormatter(String(label)) : label}</p>
      {shown.map((p) => (
        <p key={p.dataKey} className="flex items-center gap-2">
          <span className="size-2 rounded-full" style={{ background: METRIC_COLOR[p.dataKey] }} />
          <span className="text-muted-foreground">{METRIC_LABEL[p.dataKey]}</span>
          <span className="ml-auto pl-3">{fmtPct(p.value)}</span>
          <span className="text-muted-foreground">
            n={fmtInt(Number(row[`${p.dataKey}_n`] ?? 0))}
          </span>
        </p>
      ))}
    </div>
  );
}

function Empty({ children }: { children: string }) {
  return (
    <div className="grid h-full place-items-center px-6 text-center text-sm text-muted-foreground">
      {children}
    </div>
  );
}

function GroupedBars({
  rows,
  dim,
  minN,
}: {
  rows: PlayStyleRow[];
  dim: "stack_range" | "position";
  minN: number;
}) {
  const data = rows
    .map((r) => ({
      label: r[dim] ?? "?",
      ...Object.fromEntries(CORE.map((m) => [m, gated(r, m, minN)])),
      ...Object.fromEntries(CORE.map((m) => [`${m}_n`, r[`${m}_n`]])),
    }))
    .filter((d) => CORE.some((m) => (d as Record<string, unknown>)[m] != null));
  if (!data.length) return <Empty>Sem amostra suficiente com os filtros atuais.</Empty>;
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} barGap={2}>
        <CartesianGrid stroke="var(--border)" vertical={false} />
        <XAxis dataKey="label" {...axis} />
        <YAxis {...axis} width={38} tickFormatter={(v) => `${v}%`} />
        <ChartTooltip content={<MetricTooltip />} cursor={{ fill: "var(--accent)" }} />
        <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12 }} />
        {CORE.map((m) => (
          <Bar
            key={m}
            dataKey={m}
            name={METRIC_LABEL[m]}
            fill={METRIC_COLOR[m]}
            radius={[3, 3, 0, 0]}
            maxBarSize={22}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

// ---------------- tabela ----------------

type ColKind = "text" | "int" | "pct" | "gap";
type Col = { key: keyof PlayStyleRow; label: string; kind: ColKind; metric?: PlayStyleMetricKey };

const TABLE_COLS: Col[] = [
  { key: "position", label: "Posição", kind: "text" },
  { key: "stack_range", label: "Stack", kind: "text" },
  { key: "hands", label: "Mãos", kind: "int" },
  { key: "vpip", label: "VPIP", kind: "pct", metric: "vpip" },
  { key: "pfr", label: "PFR", kind: "pct", metric: "pfr" },
  { key: "gap", label: "Gap (p.p.)", kind: "gap" },
  { key: "threebet", label: "3-Bet", kind: "pct", metric: "threebet" },
  { key: "f3b", label: "Fold to 3-Bet", kind: "pct", metric: "f3b" },
  { key: "ats", label: "ATS", kind: "pct", metric: "ats" },
  { key: "fts", label: "Fold to Steal", kind: "pct", metric: "fts" },
  { key: "cbet", label: "C-Bet", kind: "pct", metric: "cbet" },
  { key: "fcb", label: "Fold to C-Bet", kind: "pct", metric: "fcb" },
];

function DetailTable({
  rows,
  descriptions,
}: {
  rows: PlayStyleRow[];
  descriptions: Partial<Record<PlayStyleMetricKey, string>>;
}) {
  // null = ordem natural da API (posição da mesa × faixa de stack)
  const [sort, setSort] = useState<{ key: keyof PlayStyleRow; dir: 1 | -1 } | null>(null);

  const sorted = useMemo(() => {
    if (!sort) return rows;
    return [...rows].sort((a, b) => {
      const va = a[sort.key];
      const vb = b[sort.key];
      if (va == null && vb == null) return 0;
      if (va == null) return 1; // sem amostra sempre no fim
      if (vb == null) return -1;
      if (typeof va === "number" && typeof vb === "number") return (va - vb) * sort.dir;
      return String(va).localeCompare(String(vb)) * sort.dir;
    });
  }, [rows, sort]);

  const toggle = (key: keyof PlayStyleRow) =>
    setSort((s) => (s?.key !== key ? { key, dir: -1 } : s.dir === -1 ? { key, dir: 1 } : null));

  return (
    <div className="[&>div]:max-h-[560px]">
      <Table>
        <TableHeader className="sticky top-0 z-10 bg-card">
          <TableRow className="hover:bg-transparent">
            {TABLE_COLS.map((c) => {
              const Icon =
                sort?.key !== c.key ? ArrowUpDown : sort.dir === -1 ? ArrowDown : ArrowUp;
              const tip = c.metric
                ? descriptions[c.metric]
                : c.kind === "gap"
                  ? "VPIP − PFR"
                  : undefined;
              return (
                <TableHead
                  key={c.key}
                  className={cn("whitespace-nowrap", c.kind !== "text" && "text-right")}
                  title={tip}
                >
                  <button
                    type="button"
                    onClick={() => toggle(c.key)}
                    className={cn(
                      "inline-flex items-center gap-1 hover:text-foreground",
                      sort?.key === c.key && "text-foreground",
                    )}
                  >
                    {c.label}
                    <Icon className="size-3 opacity-60" />
                  </button>
                </TableHead>
              );
            })}
          </TableRow>
        </TableHeader>
        <TableBody>
          {sorted.map((r) => (
            <TableRow key={`${r.position}|${r.stack_range}`}>
              {TABLE_COLS.map((c) => {
                if (c.kind === "text")
                  return (
                    <TableCell key={c.key} className="whitespace-nowrap text-sm font-medium">
                      {r[c.key] as string}
                    </TableCell>
                  );
                if (c.kind === "int")
                  return (
                    <TableCell key={c.key} className="num text-right text-xs">
                      {fmtInt(r.hands)}
                    </TableCell>
                  );
                if (c.kind === "gap")
                  return (
                    <TableCell key={c.key} className="num text-right text-xs">
                      {r.gap == null ? "—" : r.gap.toFixed(1)}
                    </TableCell>
                  );
                const m = c.metric!;
                const n = r[`${m}_n`];
                return (
                  <TableCell key={c.key} className="num whitespace-nowrap text-right text-xs">
                    <span className={cn(r[m] == null && "text-muted-foreground")}>
                      {fmtPct(r[m])}
                    </span>
                    <span
                      className={cn(
                        "ml-1.5 text-[10px]",
                        n < SMALL_SAMPLE ? "text-muted-foreground/60" : "text-muted-foreground",
                      )}
                    >
                      n={fmtInt(n)}
                    </span>
                  </TableCell>
                );
              })}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

// ---------------- página ----------------

function PlayStylePage() {
  const optionsQ = useQuery({ queryKey: ["play-style-options"], queryFn: playStyleApi.options });
  const opts = optionsQ.data;

  const [period, setPeriod] = useState<PlayStylePeriod>("all");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [buyin, setBuyin] = useState(ALL);
  const [tournament, setTournament] = useState(ALL);
  const [stack, setStack] = useState(ALL);
  const [position, setPosition] = useState(ALL);
  const [freq, setFreq] = useState<PlayStyleFreq>("W");
  const [minN, setMinN] = useState(20);
  const [evoMetrics, setEvoMetrics] = useState<PlayStyleMetricKey[]>(CORE);
  const [vpMode, setVpMode] = useState<"stack" | "position">("position");

  // Torneios oferecidos já restritos por buy-in + período, pra não oferecer
  // combinação que sempre daria vazio.
  const tournaments = useMemo(() => {
    const range = periodRange(period, dateFrom, dateTo);
    return (opts?.tournaments ?? []).filter((t) => {
      if (buyin !== ALL && t.buyin !== Number(buyin)) return false;
      if (range && t.first_ts) {
        const d = t.first_ts.slice(0, 10);
        if (d < range[0] || d > range[1]) return false;
      }
      return true;
    });
  }, [opts, buyin, period, dateFrom, dateTo]);

  useEffect(() => {
    if (tournament !== ALL && !tournaments.some((t) => tKey(t) === tournament)) setTournament(ALL);
  }, [tournaments, tournament]);

  const onPeriod = (p: PlayStylePeriod) => {
    setPeriod(p);
    if (p === "custom" && opts && !dateFrom) {
      setDateFrom(opts.date_min ?? "");
      setDateTo(opts.date_max ?? "");
    }
  };

  const [tSite, tId] = tournament === ALL ? [undefined, undefined] : tournament.split("|");
  const filters: PlayStyleFilters = {
    period,
    date_from: period === "custom" ? dateFrom : undefined,
    date_to: period === "custom" ? dateTo : undefined,
    site: tSite,
    tournament_id: tId,
    buyin: buyin === ALL ? undefined : Number(buyin),
    stack: stack === ALL ? undefined : stack,
    position: position === ALL ? undefined : position,
    freq,
  };
  const customIncomplete = period === "custom" && (!dateFrom || !dateTo);

  const reportQ = useQuery({
    queryKey: ["play-style-report", filters],
    queryFn: () => playStyleApi.report(filters),
    enabled: !customIncomplete,
    placeholderData: keepPreviousData,
  });
  const rep = reportQ.data;
  const s = rep?.summary;

  const descriptions = useMemo(
    () =>
      Object.fromEntries((opts?.metrics ?? []).map((m) => [m.key, m.description])) as Partial<
        Record<PlayStyleMetricKey, string>
      >,
    [opts],
  );

  const clearFilters = () => {
    setPeriod("all");
    setDateFrom("");
    setDateTo("");
    setBuyin(ALL);
    setTournament(ALL);
    setStack(ALL);
    setPosition(ALL);
  };

  const evoData = (rep?.evolution ?? []).map((r) => ({
    period: r.period ?? "",
    ...Object.fromEntries(evoMetrics.map((m) => [m, gated(r, m, minN)])),
    ...Object.fromEntries(evoMetrics.map((m) => [`${m}_n`, r[`${m}_n`]])),
  }));
  const evoHasData = evoData.some((d) =>
    evoMetrics.some((m) => (d as Record<string, unknown>)[m] != null),
  );

  const vpData = ((vpMode === "stack" ? rep?.by_stack : rep?.by_position) ?? [])
    .filter((r) => r.vpip_n >= minN && r.vpip != null && r.pfr != null)
    .map((r) => ({
      label: (vpMode === "stack" ? r.stack_range : r.position) ?? "?",
      vpip: r.vpip,
      pfr: r.pfr,
      vpip_n: r.vpip_n,
      pfr_n: r.pfr_n,
      range: [r.pfr, r.vpip],
      gap: r.gap,
    }));

  const loadingText =
    optionsQ.isError || reportQ.isError ? "Erro ao carregar da API." : "Carregando…";
  const noHands = s?.hands === 0;

  return (
    <div className="space-y-5">
      <PageHeader
        title="Estilo de Jogo"
        description={
          s
            ? `${fmtInt(s.hands)} mãos · ${fmtInt(s.tournaments)} torneios · ${fmtDate(s.date_min)} → ${fmtDate(s.date_max)}`
            : loadingText
        }
      />

      {/* ---------- filtros ---------- */}
      <Panel>
        <div className="flex flex-wrap items-end gap-3 p-4">
          <FilterField label="Período">
            <Select value={period} onValueChange={(v) => onPeriod(v as PlayStylePeriod)}>
              <SelectTrigger className="h-8 w-40 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PERIODS.map((p) => (
                  <SelectItem key={p.value} value={p.value}>
                    {p.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </FilterField>
          {period === "custom" ? (
            <>
              <FilterField label="De">
                <Input
                  type="date"
                  value={dateFrom}
                  onChange={(e) => setDateFrom(e.target.value)}
                  className="num h-8 text-xs"
                />
              </FilterField>
              <FilterField label="Até">
                <Input
                  type="date"
                  value={dateTo}
                  onChange={(e) => setDateTo(e.target.value)}
                  className="num h-8 text-xs"
                />
              </FilterField>
            </>
          ) : null}
          <FilterField label="Buy-in">
            <Select value={buyin} onValueChange={setBuyin}>
              <SelectTrigger className="h-8 w-32 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>Todos</SelectItem>
                {(opts?.buyins ?? []).map((b) => (
                  <SelectItem key={b} value={String(b)}>
                    {fmtMoney(b)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </FilterField>
          <FilterField label={`Torneio (${tournaments.length})`}>
            <Select value={tournament} onValueChange={setTournament}>
              <SelectTrigger className="h-8 w-72 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="max-h-80">
                <SelectItem value={ALL}>Todos</SelectItem>
                {tournaments.map((t) => (
                  <SelectItem key={tKey(t)} value={tKey(t)} className="text-xs">
                    {tournamentLabel(t)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </FilterField>
          <FilterField label="Stack">
            <Select value={stack} onValueChange={setStack}>
              <SelectTrigger className="h-8 w-32 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>Todos</SelectItem>
                {(opts?.stack_ranges ?? []).map((r) => (
                  <SelectItem key={r} value={r}>
                    {r}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </FilterField>
          <FilterField
            label="Posição"
            tip="Relativa ao botão, contando só os jogadores da mão: 4-handed = CO/BTN/SB/BB, heads-up = BTN/SB (o botão é o small blind) e BB — BTN e SB contam só mesas com 3+ jogadores. Mesas com 7+ jogadores também têm UTG+1/MP."
          >
            <Select value={position} onValueChange={setPosition}>
              <SelectTrigger className="h-8 w-28 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>Todas</SelectItem>
                {(opts?.positions ?? []).map((p) => (
                  <SelectItem key={p} value={p}>
                    {p}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </FilterField>
          <Button variant="outline" size="sm" className="h-8 text-xs" onClick={clearFilters}>
            Limpar filtros
          </Button>
          {reportQ.isFetching ? (
            <span className="pb-2 text-xs text-muted-foreground">Atualizando…</span>
          ) : null}
        </div>
      </Panel>

      {customIncomplete ? (
        <Panel>
          <p className="p-6 text-center text-sm text-muted-foreground">
            Escolha as duas datas do período customizado.
          </p>
        </Panel>
      ) : noHands ? (
        <Panel>
          <p className="p-6 text-center text-sm text-muted-foreground">
            Nenhuma mão com essa combinação de filtros.
          </p>
        </Panel>
      ) : (
        <>
          {/* ---------- KPIs ---------- */}
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {(["vpip", "pfr", "threebet", "f3b", "ats", "fts", "cbet", "fcb"] as const).map((m) => (
              <MetricCard
                key={m}
                metric={m}
                pct={s?.[m].pct ?? null}
                made={s?.[m].made ?? 0}
                opps={s?.[m].opps ?? 0}
                description={descriptions[m] ?? ""}
              />
            ))}
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <StatCard
              label="VPIP/PFR Gap"
              value={s?.gap != null ? `${s.gap.toFixed(1)} p.p.` : "—"}
              hint={
                s?.vpip.pct != null && s.pfr.pct != null
                  ? `VPIP ${fmtPct(s.vpip.pct)} − PFR ${fmtPct(s.pfr.pct)} · ${fmtInt(s.vpip.opps)} mãos`
                  : "Sem dado"
              }
            />
            <StatCard
              label="Mãos no filtro"
              value={s ? fmtInt(s.hands) : "—"}
              hint={s ? `${fmtInt(s.hands - s.vpip.opps)} walks / sem decisão preflop` : ""}
            />
            <StatCard
              label="Torneios"
              value={s ? fmtInt(s.tournaments) : "—"}
              hint={s ? `${fmtDate(s.date_min)} → ${fmtDate(s.date_max)}` : ""}
            />
          </div>

          {/* ---------- gráficos ---------- */}
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <label htmlFor="min-n">Amostra mínima por ponto nos gráficos</label>
            <Input
              id="min-n"
              type="number"
              min={1}
              max={500}
              value={minN}
              onChange={(e) => setMinN(Math.max(1, Number(e.target.value) || 1))}
              className="num h-7 w-20 text-xs"
            />
            <InfoTip text="Categorias e períodos com menos oportunidades que isso (na métrica em questão) não aparecem nos gráficos. A tabela no fim mostra tudo, com o n de cada métrica." />
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <Panel
              title="VPIP / PFR / 3-Bet por stack"
              subtitle="Stack do herói no início da mão, em BB"
            >
              <div className="h-72 px-2 py-4">
                {rep ? (
                  <GroupedBars rows={rep.by_stack} dim="stack_range" minN={minN} />
                ) : (
                  <Empty>{loadingText}</Empty>
                )}
              </div>
            </Panel>
            <Panel
              title="VPIP / PFR / 3-Bet por posição"
              subtitle="Só posições que existem em cada mão"
            >
              <div className="h-72 px-2 py-4">
                {rep ? (
                  <GroupedBars rows={rep.by_position} dim="position" minN={minN} />
                ) : (
                  <Empty>{loadingText}</Empty>
                )}
              </div>
            </Panel>
          </div>

          <Panel
            title="Evolução ao longo do tempo"
            subtitle={`Pontos com menos de ${minN} oportunidades na métrica ficam de fora · dia ≈ sessão`}
            actions={
              <ToggleGroup
                type="single"
                size="sm"
                value={freq}
                onValueChange={(v) => v && setFreq(v as PlayStyleFreq)}
              >
                <ToggleGroupItem value="D" className="h-7 px-2 text-xs">
                  Dia
                </ToggleGroupItem>
                <ToggleGroupItem value="W" className="h-7 px-2 text-xs">
                  Semana
                </ToggleGroupItem>
                <ToggleGroupItem value="M" className="h-7 px-2 text-xs">
                  Mês
                </ToggleGroupItem>
              </ToggleGroup>
            }
          >
            <div className="border-b border-border px-4 py-2.5">
              <ToggleGroup
                type="multiple"
                size="sm"
                value={evoMetrics}
                onValueChange={(v) => setEvoMetrics(v as PlayStyleMetricKey[])}
                className="flex-wrap justify-start"
              >
                {EVO_METRICS.map((m) => (
                  <ToggleGroupItem key={m} value={m} className="h-7 gap-1.5 px-2 text-xs">
                    <span className="size-2 rounded-full" style={{ background: METRIC_COLOR[m] }} />
                    {METRIC_LABEL[m]}
                  </ToggleGroupItem>
                ))}
              </ToggleGroup>
            </div>
            <div className="h-80 px-2 py-4">
              {!rep ? (
                <Empty>{loadingText}</Empty>
              ) : !evoMetrics.length ? (
                <Empty>Selecione ao menos uma métrica.</Empty>
              ) : !evoHasData ? (
                <Empty>
                  Sem períodos com amostra suficiente — ajuste a amostra mínima, o agrupamento ou os
                  filtros.
                </Empty>
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={evoData}>
                    <CartesianGrid stroke="var(--border)" vertical={false} />
                    <XAxis
                      dataKey="period"
                      {...axis}
                      tickFormatter={fmtDateShort}
                      minTickGap={30}
                    />
                    <YAxis {...axis} width={38} tickFormatter={(v) => `${v}%`} />
                    <ChartTooltip
                      content={
                        <MetricTooltip labelFormatter={(l) => `Início: ${fmtDateShort(l)}`} />
                      }
                    />
                    {evoMetrics.map((m) => (
                      <Line
                        key={m}
                        type="monotone"
                        dataKey={m}
                        name={METRIC_LABEL[m]}
                        stroke={METRIC_COLOR[m]}
                        strokeWidth={2}
                        dot={{ r: 3, fill: METRIC_COLOR[m], strokeWidth: 0 }}
                        activeDot={{ r: 5 }}
                        isAnimationActive={false}
                      />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              )}
            </div>
          </Panel>

          <Panel
            title="VPIP x PFR"
            subtitle="Barra = distância entre VPIP e PFR · número = gap em pontos percentuais"
            actions={
              <ToggleGroup
                type="single"
                size="sm"
                value={vpMode}
                onValueChange={(v) => v && setVpMode(v as "stack" | "position")}
              >
                <ToggleGroupItem value="stack" className="h-7 px-2 text-xs">
                  Por Stack
                </ToggleGroupItem>
                <ToggleGroupItem value="position" className="h-7 px-2 text-xs">
                  Por Posição
                </ToggleGroupItem>
              </ToggleGroup>
            }
          >
            <div className="h-80 px-2 py-4">
              {!rep ? (
                <Empty>{loadingText}</Empty>
              ) : !vpData.length ? (
                <Empty>Sem amostra suficiente com os filtros atuais.</Empty>
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={vpData} margin={{ top: 18 }}>
                    <CartesianGrid stroke="var(--border)" vertical={false} />
                    <XAxis dataKey="label" {...axis} />
                    <YAxis {...axis} width={38} tickFormatter={(v) => `${v}%`} />
                    <ChartTooltip content={<MetricTooltip />} cursor={{ fill: "var(--accent)" }} />
                    <Legend
                      iconSize={8}
                      wrapperStyle={{ fontSize: 12 }}
                      payload={(["vpip", "pfr"] as const).map((m) => ({
                        value: METRIC_LABEL[m],
                        type: "circle" as const,
                        color: METRIC_COLOR[m],
                      }))}
                    />
                    <Bar
                      dataKey="range"
                      barSize={6}
                      fill="var(--muted-foreground)"
                      fillOpacity={0.35}
                      radius={3}
                      legendType="none"
                      isAnimationActive={false}
                    />
                    {(["vpip", "pfr"] as const).map((m) => (
                      <Line
                        key={m}
                        dataKey={m}
                        name={METRIC_LABEL[m]}
                        stroke="none"
                        legendType="circle"
                        dot={{ r: 6, fill: METRIC_COLOR[m], stroke: "var(--card)", strokeWidth: 2 }}
                        activeDot={{ r: 7, fill: METRIC_COLOR[m] }}
                        isAnimationActive={false}
                      >
                        {m === "vpip" ? (
                          <LabelList
                            dataKey="gap"
                            position="top"
                            offset={12}
                            fill="var(--muted-foreground)"
                            fontSize={11}
                            formatter={(v: number) => `+${v.toFixed(1)}`}
                          />
                        ) : null}
                      </Line>
                    ))}
                  </ComposedChart>
                </ResponsiveContainer>
              )}
            </div>
          </Panel>

          {/* ---------- tabela ---------- */}
          <Panel
            title="Detalhamento por posição e stack"
            subtitle="Clique no cabeçalho para ordenar · n = oportunidades (denominador) da métrica"
          >
            {rep ? (
              <DetailTable rows={rep.table} descriptions={descriptions} />
            ) : (
              <p className="p-6 text-center text-sm text-muted-foreground">{loadingText}</p>
            )}
          </Panel>

          <Panel title="Como as métricas são calculadas">
            <ul className="space-y-1.5 p-4 text-xs text-muted-foreground">
              {(opts?.metrics ?? []).map((m) => (
                <li key={m.key}>
                  <span className="font-semibold text-foreground">{m.label}</span> — {m.description}
                </li>
              ))}
              <li>
                <span className="font-semibold text-foreground">Posição</span> — recalculada a
                partir dos assentos ocupados e do botão de cada mão (não usa o número do assento).
              </li>
              <li>
                <span className="font-semibold text-foreground">Stack</span> — stack do herói no
                início da mão, em BB.
              </li>
            </ul>
          </Panel>
        </>
      )}
    </div>
  );
}

function FilterField({
  label,
  tip,
  children,
}: {
  label: string;
  tip?: string;
  children: ReactNode;
}) {
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-1 text-xs text-muted-foreground">
        <span>{label}</span>
        {tip ? <InfoTip text={tip} /> : null}
      </div>
      {children}
    </div>
  );
}
