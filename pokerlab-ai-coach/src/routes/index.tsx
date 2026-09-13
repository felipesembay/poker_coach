import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { ArrowUpRight, Brain } from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Money, PageHeader, Panel, StatCard } from "@/components/lab";
import { Button } from "@/components/ui/button";
import { statsApi } from "@/lib/api";
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

function fmtMoney(v: number | null | undefined): string {
  if (v == null) return "—";
  return `${v < 0 ? "-" : ""}$${Math.abs(v).toFixed(2)}`;
}

function fmtDuration(min: number): string {
  const h = Math.floor(min / 60);
  const m = Math.round(min % 60);
  if (h === 0) return `${m}min`;
  return `${h}h ${m}min`;
}

function fmtDateShort(iso: string): string {
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${(y ?? "").slice(2)}`;
}

function Dashboard() {
  const overviewQ = useQuery({ queryKey: ["stats-overview"], queryFn: statsApi.overview });
  const netBbByDayQ = useQuery({ queryKey: ["stats-net-bb-day"], queryFn: statsApi.netBbByDay });
  const byBuyinQ = useQuery({ queryKey: ["stats-by-buyin"], queryFn: statsApi.profitByBuyin });
  const byWeekdayQ = useQuery({ queryKey: ["stats-by-weekday"], queryFn: statsApi.netBbByWeekday });
  const byHourQ = useQuery({ queryKey: ["stats-by-hour"], queryFn: statsApi.netBbByHour });
  const sessionsQ = useQuery({ queryKey: ["stats-sessions"], queryFn: statsApi.sessions });
  const positionQ = useQuery({ queryKey: ["stats-position"], queryFn: statsApi.position });
  const stackQ = useQuery({ queryKey: ["stats-stack-buckets"], queryFn: statsApi.stackBuckets });
  const cashTicketQ = useQuery({ queryKey: ["stats-cash-ticket"], queryFn: statsApi.cashVsTicket });

  const ov = overviewQ.data;
  const roi = ov?.roi ?? null;

  const bbCurve = useMemo(() => {
    const rows = netBbByDayQ.data ?? [];
    let acc = 0;
    return rows.map((r) => {
      acc += r.net_bb;
      return { date: r.date, saldo: Math.round(acc * 10) / 10 };
    });
  }, [netBbByDayQ.data]);

  const sessions = sessionsQ.data ?? [];

  // Calendário: últimos 35 dias corridos (a partir de hoje), agregando
  // todas as sessões (pode ter mais de um site no mesmo dia) por data.
  const calendar = useMemo(() => {
    const byDate = new Map<string, { profit: number | null; tournaments: number }>();
    for (const s of sessions) {
      const cur = byDate.get(s.date) ?? { profit: null, tournaments: 0 };
      cur.tournaments += s.tournaments;
      if (s.profit != null) cur.profit = (cur.profit ?? 0) + s.profit;
      byDate.set(s.date, cur);
    }
    const days: { date: string; day: number; played: boolean; profit: number | null }[] = [];
    const today = new Date();
    for (let i = 34; i >= 0; i--) {
      const d = new Date(today);
      d.setDate(d.getDate() - i);
      const iso = d.toISOString().slice(0, 10);
      const entry = byDate.get(iso);
      days.push({ date: iso, day: d.getDate(), played: !!entry, profit: entry?.profit ?? null });
    }
    return days;
  }, [sessions]);

  // Destaques reais (mesmo padrão de insight automático das páginas
  // Streamlit posicao.py/lucro.py/stack.py) — nada de texto gerado, só
  // achar o melhor/pior valor com amostra mínima.
  const highlights = useMemo(() => {
    const out: { tone: "profit" | "loss" | "neutral"; title: string; text: string }[] = [];
    const positions = (positionQ.data ?? []).filter((p) => p.spots >= 20);
    if (positions.length >= 2) {
      const best = positions.reduce((a, b) => (b.net_bb > a.net_bb ? b : a));
      const worst = positions.reduce((a, b) => (b.net_bb < a.net_bb ? b : a));
      if (best.net_bb > 0) {
        out.push({
          tone: "profit",
          title: "Melhor posição",
          text: `${best.position}: ${best.net_bb >= 0 ? "+" : ""}${best.net_bb} BB em ${best.spots} mãos.`,
        });
      }
      if (worst.net_bb < 0) {
        out.push({
          tone: "loss",
          title: "Posição a revisar",
          text: `${worst.position}: ${worst.net_bb} BB em ${worst.spots} mãos.`,
        });
      }
    }
    const hours = (byHourQ.data ?? []).filter((h) => h.hands >= 20);
    if (hours.length >= 2) {
      const best = hours.reduce((a, b) => (b.net_bb > a.net_bb ? b : a));
      if (best.net_bb > 0) {
        out.push({
          tone: "profit",
          title: "Melhor horário",
          text: `${best.hour}h: ${best.net_bb >= 0 ? "+" : ""}${best.net_bb} BB em ${best.hands} mãos.`,
        });
      }
    }
    const stacks = (stackQ.data ?? []).filter((s) => s.spots >= 20);
    const worstStack = stacks.length
      ? stacks.reduce((a, b) => (b.net_bb < a.net_bb ? b : a))
      : null;
    if (worstStack && worstStack.net_bb < 0) {
      out.push({
        tone: "loss",
        title: "Faixa de stack a revisar",
        text: `${worstStack.bucket}: ${worstStack.net_bb} BB em ${worstStack.spots} mãos.`,
      });
    }
    return out.slice(0, 3);
  }, [positionQ.data, byHourQ.data, stackQ.data]);

  const ct = cashTicketQ.data;

  return (
    <div className="space-y-5">
      <PageHeader
        title="Dashboard"
        description={
          ov
            ? `${ov.tournaments} torneios · ${ov.hands.toLocaleString("pt-BR")} mãos importadas`
            : "Carregando…"
        }
        actions={
          <Button size="sm" asChild>
            <Link to="/maos">Importar hand history</Link>
          </Button>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4 xl:grid-cols-8">
        <StatCard
          label="Lucro"
          value={fmtMoney(roi?.profit)}
          tone={roi ? (roi.profit >= 0 ? "profit" : "loss") : "neutral"}
          hint={roi ? `${roi.tournaments} c/ resultado` : "Sem resultado registrado"}
        />
        <StatCard
          label="ROI"
          value={roi ? `${roi.roi_pct}%` : "—"}
          tone={roi ? (roi.roi_pct >= 0 ? "profit" : "loss") : "neutral"}
        />
        <StatCard label="ITM" value={roi ? `${roi.itm_pct}%` : "—"} tone="neutral" />
        <StatCard label="ABI" value={roi ? `$${roi.abi.toFixed(2)}` : "—"} tone="neutral" />
        <StatCard
          label="Saldo (fichas)"
          value={ov ? `${ov.net_bb >= 0 ? "+" : ""}${ov.net_bb} BB` : "—"}
          tone={ov ? (ov.net_bb >= 0 ? "profit" : "loss") : "neutral"}
          hint="Sempre disponível"
        />
        <StatCard label="Horas jogadas" value={ov ? `${ov.hours_played}h` : "—"} tone="neutral" />
        <StatCard label="Torneios" value={ov ? String(ov.tournaments) : "—"} tone="neutral" />
        <StatCard label="Mãos" value={ov ? ov.hands.toLocaleString("pt-BR") : "—"} tone="neutral" />
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Panel
          title="Saldo em BB acumulado"
          subtitle="Sempre disponível — não depende de resultado registrado"
          className="xl:col-span-2"
        >
          <div className="h-64 px-2 py-4">
            {bbCurve.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={bbCurve}>
                  <defs>
                    <linearGradient id="brGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="var(--chart-1)" stopOpacity={0.35} />
                      <stop offset="100%" stopColor="var(--chart-1)" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="date" {...axis} tickFormatter={fmtDateShort} minTickGap={30} />
                  <YAxis {...axis} width={48} />
                  <Tooltip contentStyle={tooltipStyle} labelFormatter={fmtDateShort} />
                  <Area
                    type="monotone"
                    dataKey="saldo"
                    stroke="var(--chart-1)"
                    strokeWidth={2}
                    fill="url(#brGrad)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="grid h-full place-items-center text-sm text-muted-foreground">
                {netBbByDayQ.isLoading ? "Carregando…" : "Sem mãos com horário ainda."}
              </div>
            )}
          </div>
        </Panel>

        <Panel title="ROI por buy-in" subtitle="Precisa de resultado registrado">
          <div className="h-64 px-2 py-4">
            {(byBuyinQ.data ?? []).length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={byBuyinQ.data ?? []}>
                  <CartesianGrid stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="buyin" {...axis} tickFormatter={(v) => `$${v}`} />
                  <YAxis {...axis} width={40} tickFormatter={(v) => `${v}%`} />
                  <Tooltip
                    contentStyle={tooltipStyle}
                    formatter={(v: number) => [`${v}%`, "ROI"]}
                    labelFormatter={(v) => `Buy-in $${v}`}
                  />
                  <Bar dataKey="roi_pct" radius={[3, 3, 0, 0]}>
                    {(byBuyinQ.data ?? []).map((b) => (
                      <Cell
                        key={b.buyin}
                        fill={(b.roi_pct ?? 0) >= 0 ? "var(--profit)" : "var(--loss)"}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="grid h-full place-items-center px-4 text-center text-sm text-muted-foreground">
                {byBuyinQ.isLoading
                  ? "Carregando…"
                  : "Sem torneio com resultado registrado ainda — configure em Torneios."}
              </div>
            )}
          </div>
        </Panel>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title="Saldo em BB por dia da semana" subtitle="Em qual dia você joga melhor">
          <div className="h-56 px-2 py-4">
            {(byWeekdayQ.data ?? []).length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={byWeekdayQ.data ?? []}>
                  <CartesianGrid stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="weekday" {...axis} />
                  <YAxis {...axis} width={44} />
                  <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "var(--accent)" }} />
                  <Bar dataKey="net_bb" radius={[3, 3, 0, 0]}>
                    {(byWeekdayQ.data ?? []).map((w) => (
                      <Cell
                        key={w.weekday}
                        fill={w.net_bb >= 0 ? "var(--profit)" : "var(--loss)"}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="grid h-full place-items-center text-sm text-muted-foreground">
                {byWeekdayQ.isLoading ? "Carregando…" : "Sem dado ainda."}
              </div>
            )}
          </div>
        </Panel>

        <Panel title="Saldo em BB por horário do dia" subtitle="Em que horário você joga melhor">
          <div className="h-56 px-2 py-4">
            {(byHourQ.data ?? []).length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={byHourQ.data ?? []}>
                  <CartesianGrid stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="hour" {...axis} tickFormatter={(v) => `${v}h`} />
                  <YAxis {...axis} width={44} />
                  <Tooltip
                    contentStyle={tooltipStyle}
                    cursor={{ fill: "var(--accent)" }}
                    labelFormatter={(v) => `${v}h`}
                  />
                  <Bar dataKey="net_bb" radius={[3, 3, 0, 0]}>
                    {(byHourQ.data ?? []).map((h) => (
                      <Cell key={h.hour} fill={h.net_bb >= 0 ? "var(--profit)" : "var(--loss)"} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="grid h-full place-items-center text-sm text-muted-foreground">
                {byHourQ.isLoading ? "Carregando…" : "Sem dado ainda."}
              </div>
            )}
          </div>
        </Panel>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Panel title="Calendário de sessões" subtitle="Últimos 35 dias">
          <div className="p-4">
            <div className="grid grid-cols-7 gap-1.5">
              {calendar.map((d) => (
                <div
                  key={d.date}
                  title={
                    d.played
                      ? `${d.date} · ${d.profit != null ? fmtMoney(d.profit) : "sem resultado"}`
                      : `${d.date} · sem sessão`
                  }
                  className={cn(
                    "num grid aspect-square place-items-center rounded-md border border-border text-[10px] transition-colors",
                    !d.played && "bg-elevated/40 text-muted-foreground/50",
                    d.played && d.profit != null && d.profit >= 0 && "bg-profit/15 text-profit",
                    d.played && d.profit != null && d.profit < 0 && "bg-loss/15 text-loss",
                    d.played && d.profit == null && "bg-primary/10 text-primary",
                  )}
                >
                  {d.day}
                </div>
              ))}
            </div>
          </div>
        </Panel>

        <Panel
          title="Últimas sessões"
          subtitle={`${sessions.length} registros`}
          className="xl:col-span-2"
          actions={
            <Button variant="ghost" size="sm" asChild>
              <Link to="/sessoes">
                Ver todas <ArrowUpRight className="ml-1 size-3.5" />
              </Link>
            </Button>
          }
        >
          {sessions.length > 0 ? (
            <ul className="divide-y divide-border">
              {sessions.slice(0, 4).map((s) => (
                <li
                  key={`${s.date}-${s.site}`}
                  className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 px-4 py-3 transition-colors hover:bg-accent/40"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">
                      {s.site} · <span className="num">{s.tournaments}</span> torneios
                    </p>
                    <p className="num truncate text-xs text-muted-foreground">
                      {fmtDateShort(s.date)} · {fmtDuration(s.duration_min)} · {s.hands} mãos
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-4">
                    <span className="num text-xs text-muted-foreground">
                      {s.roi_pct != null ? `ROI ${s.roi_pct}%` : "—"}
                    </span>
                    {s.profit != null ? (
                      <Money value={s.profit} suffix=" USD" />
                    ) : (
                      <span className="num text-xs text-muted-foreground">sem resultado</span>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <div className="p-8 text-center text-sm text-muted-foreground">
              {sessionsQ.isLoading ? "Carregando…" : "Nenhuma sessão ainda."}
            </div>
          )}
        </Panel>
      </div>

      <Panel
        title="Destaques"
        subtitle="Calculado a partir das suas mãos importadas — sem resultado fictício"
      >
        <div className="space-y-3 p-4 fade-up">
          <div className="flex items-center gap-2 text-primary">
            <Brain className="size-4" />
            <span className="text-xs font-semibold uppercase tracking-[0.14em]">Panorama</span>
          </div>
          {highlights.length > 0 ? (
            <div className="grid gap-3 sm:grid-cols-3">
              {highlights.map((h) => (
                <div key={h.title} className="rounded-md border border-border bg-elevated/50 p-3">
                  <p
                    className={cn(
                      "text-xs font-semibold uppercase tracking-[0.12em]",
                      h.tone === "profit" && "text-profit",
                      h.tone === "loss" && "text-loss",
                      h.tone === "neutral" && "text-primary",
                    )}
                  >
                    {h.title}
                  </p>
                  <p className="mt-1 text-sm">{h.text}</p>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              Ainda sem amostra suficiente (mínimo 20 mãos por posição/horário/faixa de stack) pra
              apontar destaques com confiança.
            </p>
          )}
          {ct && (ct.cash.count > 0 || ct.ticket.count > 0) && (
            <p className="text-sm text-muted-foreground">
              💵 Ganho em dinheiro:{" "}
              <span className="num text-foreground">${ct.cash.total.toFixed(2)}</span> (
              {ct.cash.count} torneios) · 🎟️ Ganho em tickets (valor estimado):{" "}
              <span className="num text-foreground">${ct.ticket.total.toFixed(2)}</span> (
              {ct.ticket.count} conversões).
            </p>
          )}
          <Button variant="outline" size="sm" asChild>
            <Link to="/coach">Abrir conversa com o Coach IA</Link>
          </Button>
        </div>
      </Panel>
    </div>
  );
}
