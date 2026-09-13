import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Download, Search } from "lucide-react";
import { useMemo, useState } from "react";

import { Money, PageHeader, Panel, StatCard } from "@/components/lab";
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
import { statsApi } from "@/lib/api";

export const Route = createFileRoute("/sessoes")({
  head: () => ({
    meta: [
      { title: "Sessões — PokerLab" },
      {
        name: "description",
        content: "Histórico de sessões de MTT com lucro, ROI, tempo, volume de mãos e análise.",
      },
      { property: "og:title", content: "Sessões — PokerLab" },
      {
        property: "og:description",
        content: "Filtre e analise cada sessão de torneios em detalhe.",
      },
    ],
  }),
  component: SessionsPage,
});

const RANGE_OPTIONS = [
  { value: "7", label: "Últimos 7 dias" },
  { value: "30", label: "Últimos 30 dias" },
  { value: "90", label: "Últimos 90 dias" },
  { value: "all", label: "Todo o período" },
] as const;

function fmtDateShort(iso: string): string {
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${(y ?? "").slice(2)}`;
}

function fmtDuration(min: number): string {
  const h = Math.floor(min / 60);
  const m = Math.round(min % 60);
  if (h === 0) return `${m}min`;
  return `${h}h ${m}min`;
}

function SessionsPage() {
  const sessionsQ = useQuery({ queryKey: ["stats-sessions"], queryFn: statsApi.sessions });
  const allSessions = sessionsQ.data ?? [];

  const [search, setSearch] = useState("");
  const [siteFilter, setSiteFilter] = useState("all");
  const [range, setRange] = useState<(typeof RANGE_OPTIONS)[number]["value"]>("all");

  const sites = useMemo(
    () => Array.from(new Set(allSessions.map((s) => s.site))).sort(),
    [allSessions],
  );

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    const cutoff =
      range === "all"
        ? null
        : (() => {
            const d = new Date();
            d.setDate(d.getDate() - Number(range));
            return d.toISOString().slice(0, 10);
          })();
    return allSessions.filter((s) => {
      if (q && !s.site.toLowerCase().includes(q) && !s.date.includes(q)) return false;
      if (siteFilter !== "all" && s.site !== siteFilter) return false;
      if (cutoff && s.date < cutoff) return false;
      return true;
    });
  }, [allSessions, search, siteFilter, range]);

  const withResult = filtered.filter((s) => s.profit != null);
  const totalProfit = withResult.reduce((acc, s) => acc + (s.profit ?? 0), 0);
  const positiveCount = withResult.filter((s) => (s.profit ?? 0) >= 0).length;
  const totalMinutes = filtered.reduce((acc, s) => acc + s.duration_min, 0);
  const totalTournaments = filtered.reduce((acc, s) => acc + s.tournaments, 0);
  const totalHands = filtered.reduce((acc, s) => acc + s.hands, 0);
  const bestSession = withResult.length
    ? withResult.reduce((a, b) => ((b.profit ?? 0) > (a.profit ?? 0) ? b : a))
    : null;

  return (
    <div className="space-y-5">
      <PageHeader
        title="Sessões"
        description={
          sessionsQ.isLoading
            ? "Carregando…"
            : `${filtered.length} sessões (dia · sala) · ${totalTournaments} torneios · ${totalHands.toLocaleString("pt-BR")} mãos`
        }
        actions={
          <Button variant="outline" size="sm">
            <Download className="mr-1.5 size-3.5" /> Exportar
          </Button>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard
          label="Lucro do período"
          value={withResult.length ? `$${totalProfit.toFixed(2)}` : "—"}
          delta={
            withResult.length ? `${withResult.length} sessões c/ resultado` : "Sem resultado registrado"
          }
          tone={withResult.length ? (totalProfit >= 0 ? "profit" : "loss") : "neutral"}
        />
        <StatCard
          label="Sessões positivas"
          value={withResult.length ? `${positiveCount} / ${withResult.length}` : "—"}
          delta={
            withResult.length ? `${Math.round((positiveCount / withResult.length) * 100)}%` : undefined
          }
          tone="neutral"
        />
        <StatCard
          label="Tempo total"
          value={fmtDuration(totalMinutes)}
          delta={filtered.length ? `${fmtDuration(Math.round(totalMinutes / filtered.length))} / sessão` : undefined}
          tone="neutral"
        />
        <StatCard
          label="Melhor sessão"
          value={bestSession ? `+$${(bestSession.profit ?? 0).toFixed(2)}` : "—"}
          delta={bestSession ? `${fmtDateShort(bestSession.date)} · ${bestSession.site}` : "Sem resultado registrado"}
          tone={bestSession ? "profit" : "neutral"}
        />
      </div>

      <Panel
        title="Histórico"
        subtitle={`Resultado acumulado: ${withResult.length ? `$${totalProfit.toFixed(2)}` : "—"}`}
      >
        <div className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-3">
          <div className="relative min-w-[200px] flex-1">
            <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Pesquisar sala ou data…"
              className="h-9 pl-8 text-sm"
            />
          </div>
          <Select value={siteFilter} onValueChange={setSiteFilter}>
            <SelectTrigger className="h-9 w-[150px] text-sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todas as salas</SelectItem>
              {sites.map((s) => (
                <SelectItem key={s} value={s}>
                  {s}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={range} onValueChange={(v) => setRange(v as typeof range)}>
            <SelectTrigger className="h-9 w-[160px] text-sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {RANGE_OPTIONS.map((r) => (
                <SelectItem key={r.value} value={r.value}>
                  {r.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Data</TableHead>
                <TableHead>Sala</TableHead>
                <TableHead className="text-right">Torneios</TableHead>
                <TableHead className="text-right">ABI</TableHead>
                <TableHead className="text-right">Lucro</TableHead>
                <TableHead className="text-right">ROI</TableHead>
                <TableHead className="text-right">Tempo</TableHead>
                <TableHead className="text-right">Mãos</TableHead>
                <TableHead className="text-right">Ação</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sessionsQ.isLoading && (
                <TableRow>
                  <TableCell colSpan={9} className="py-10 text-center text-sm text-muted-foreground">
                    Carregando…
                  </TableCell>
                </TableRow>
              )}
              {!sessionsQ.isLoading && filtered.length === 0 && (
                <TableRow>
                  <TableCell colSpan={9} className="py-10 text-center text-sm text-muted-foreground">
                    Nenhuma sessão encontrada com esses filtros.
                  </TableCell>
                </TableRow>
              )}
              {filtered.map((s) => (
                <TableRow key={`${s.date}-${s.site}`}>
                  <TableCell className="num text-xs">{fmtDateShort(s.date)}</TableCell>
                  <TableCell className="text-sm font-medium">
                    <Badge variant="outline" className="font-normal">
                      {s.site}
                    </Badge>
                  </TableCell>
                  <TableCell className="num text-right text-xs">{s.tournaments}</TableCell>
                  <TableCell className="num text-right text-xs">
                    {s.abi != null ? `$${s.abi.toFixed(2)}` : "—"}
                  </TableCell>
                  <TableCell className="text-right text-xs">
                    {s.profit != null ? (
                      <Money value={s.profit} />
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  <TableCell className="text-right text-xs">
                    {s.roi_pct != null ? (
                      <Money value={s.roi_pct} suffix="%" />
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  <TableCell className="num text-right text-xs text-muted-foreground">
                    {fmtDuration(s.duration_min)}
                  </TableCell>
                  <TableCell className="num text-right text-xs text-muted-foreground">
                    {s.hands}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button variant="outline" size="sm" asChild>
                      <Link to="/maos">Analisar</Link>
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </Panel>
    </div>
  );
}
