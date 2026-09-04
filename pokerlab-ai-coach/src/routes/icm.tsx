import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Coins } from "lucide-react";

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
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { icmApi } from "@/lib/api";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/icm")({
  head: () => ({
    meta: [
      { title: "ICM — PokerLab" },
      {
        name: "description",
        content:
          "Estude pressão de ICM em bolha, mesa final e satélites, com precisão por categoria e drills.",
      },
      { property: "og:title", content: "ICM — PokerLab" },
      {
        property: "og:description",
        content: "Spots de ICM revisados com $EV, risco e treinador dedicado.",
      },
    ],
  }),
  component: IcmPage,
});

const categories = ["Todos", "Mesa Final", "Bolha", "Satélite"];

function riskLabel(pct: number): string {
  if (pct >= 30) return "Crítico";
  if (pct >= 15) return "Alto";
  if (pct >= 5) return "Médio";
  return "Baixo";
}

function IcmPage() {
  const [selectedKey, setSelectedKey] = useState<string>("");
  const [filterCategory, setFilterCategory] = useState("Todos");

  const tournamentsQ = useQuery({
    queryKey: ["icm-tournaments"],
    queryFn: icmApi.tournaments,
  });

  const tournaments = tournamentsQ.data ?? [];
  const selectedT = tournaments.find((t) => `${t.site}::${t.tournament_id}` === selectedKey);

  const spotsQ = useQuery({
    queryKey: ["icm-spots", selectedKey],
    queryFn: () =>
      icmApi.spots({
        site: selectedT!.site,
        tournament_id: selectedT!.tournament_id,
        confirmed: true,
      }),
    enabled: !!selectedT?.has_payouts,
  });

  const summary = spotsQ.data;
  const allSpots = summary?.rows ?? [];

  const filtered = useMemo(
    () =>
      filterCategory === "Todos" ? allSpots : allSpots.filter((s) => s.category === filterCategory),
    [allSpots, filterCategory],
  );

  const totalSpots = summary?.spots ?? 0;
  const leakSpots = summary?.leak_spots ?? 0;
  const accuracy = totalSpots ? Math.round(((totalSpots - leakSpots) / totalSpots) * 100) : 0;
  const totalEvLost = summary?.total_ev_lost ?? 0;

  const categoryStats = useMemo(() => {
    if (!allSpots.length) return [];
    return (["Mesa Final", "Bolha", "Satélite"] as const).map((cat) => {
      const catSpots = allSpots.filter((s) => s.category === cat);
      const correct = catSpots.filter((s) => s.hero_decision === s.icm_decision).length;
      return {
        label: cat,
        acc: catSpots.length ? Math.round((correct / catSpots.length) * 100) : null,
        n: catSpots.length,
      };
    });
  }, [allSpots]);

  return (
    <div className="space-y-5">
      <PageHeader
        title="ICM"
        description={
          totalSpots
            ? `${totalSpots} spots analisados · precisão ${accuracy}%`
            : "Selecione um torneio com premiação configurada"
        }
        actions={
          <Button size="sm">
            <Coins className="mr-1.5 size-3.5" /> Treinar
          </Button>
        }
      />

      {/* Tournament selector */}
      <Panel title="Torneio">
        <div className="flex flex-wrap items-center gap-3 p-4">
          <Select value={selectedKey} onValueChange={setSelectedKey}>
            <SelectTrigger className="h-9 w-[320px] text-sm">
              <SelectValue placeholder="Selecione um torneio…" />
            </SelectTrigger>
            <SelectContent>
              {tournamentsQ.isLoading && (
                <SelectItem value="__loading" disabled>
                  Carregando…
                </SelectItem>
              )}
              {tournaments.map((t) => (
                <SelectItem
                  key={`${t.site}::${t.tournament_id}`}
                  value={`${t.site}::${t.tournament_id}`}
                >
                  {t.name ?? `${t.site} #${t.tournament_id}`}
                  {!t.has_payouts && " — sem premiação"}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {selectedT && !selectedT.has_payouts && (
            <p className="text-xs text-loss">
              Este torneio não tem premiação salva. Configure os prêmios para calcular o ICM.
            </p>
          )}
          {spotsQ.isLoading && <p className="text-xs text-muted-foreground">Calculando spots…</p>}
        </div>
      </Panel>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard
          label="Precisão ICM"
          value={totalSpots ? `${accuracy}%` : "—"}
          tone={accuracy >= 85 ? "profit" : accuracy >= 70 ? "neutral" : "loss"}
          hint={totalSpots ? `${totalSpots} spots` : "Selecione um torneio"}
        />
        <StatCard
          label="$EV perdido"
          value={totalSpots ? `$${Math.abs(totalEvLost).toFixed(2)}` : "—"}
          tone="loss"
        />
        <StatCard
          label="Spots com erro"
          value={totalSpots ? String(leakSpots) : "—"}
          tone={leakSpots > 0 ? "loss" : "profit"}
        />
        <StatCard
          label="Spots corretos"
          value={totalSpots ? String(totalSpots - leakSpots) : "—"}
          tone="profit"
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Panel title="Precisão por fase" subtitle="Onde o ICM mais custa" className="xl:col-span-2">
          <ul className="divide-y divide-border">
            {(categoryStats.length
              ? categoryStats
              : [
                  { label: "Mesa Final", acc: null, n: 0 },
                  { label: "Bolha", acc: null, n: 0 },
                  { label: "Satélite", acc: null, n: 0 },
                ]
            ).map((r) => (
              <li
                key={r.label}
                className="grid grid-cols-[110px_minmax(0,1fr)_52px] items-center gap-3 px-4 py-3"
              >
                <span className="truncate text-xs text-muted-foreground">{r.label}</span>
                <div className="h-2 overflow-hidden rounded-full bg-elevated">
                  {r.acc != null && (
                    <div
                      className={cn(
                        "h-full rounded-full",
                        r.acc >= 85 ? "bg-profit" : r.acc >= 72 ? "bg-primary" : "bg-loss",
                      )}
                      style={{ width: `${r.acc}%` }}
                    />
                  )}
                </div>
                <span className="num text-right text-xs font-semibold">
                  {r.acc != null ? `${r.acc}%` : "—"}
                </span>
              </li>
            ))}
          </ul>
        </Panel>

        <Panel title="Conceitos-chave" subtitle="Recomendado para o seu perfil">
          <ul className="divide-y divide-border">
            {[
              "Bubble factor: por que calls apertam perto da bolha",
              "Risk premium em satélites com 2 vagas",
              "Chip leader vs short stacks na FT",
              "Quando ignorar o ICM e maximizar chips",
            ].map((t) => (
              <li key={t} className="px-4 py-3 text-sm transition-colors hover:bg-accent/40">
                {t}
              </li>
            ))}
          </ul>
        </Panel>
      </div>

      <Panel
        title="Spots de ICM"
        subtitle="Cenários revisados automaticamente das suas sessões"
        actions={
          <div className="flex items-center gap-2">
            <Input placeholder="Pesquisar cenário…" className="h-8 w-40 text-xs" />
          </div>
        }
      >
        <div className="border-b border-border px-4 py-3">
          <Tabs value={filterCategory} onValueChange={setFilterCategory}>
            <TabsList className="h-8">
              {categories.map((c) => (
                <TabsTrigger key={c} value={c} className="text-xs">
                  {c}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        </div>

        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Cenário</TableHead>
                <TableHead>Categoria</TableHead>
                <TableHead className="text-right">Stack</TableHead>
                <TableHead>Risco</TableHead>
                <TableHead>Hero</TableHead>
                <TableHead>ICM</TableHead>
                <TableHead className="text-right">$EV perdido</TableHead>
                <TableHead className="text-right">Ação</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {spotsQ.isLoading && (
                <TableRow>
                  <TableCell
                    colSpan={8}
                    className="py-10 text-center text-sm text-muted-foreground"
                  >
                    Calculando…
                  </TableCell>
                </TableRow>
              )}
              {!spotsQ.isLoading && !selectedKey && (
                <TableRow>
                  <TableCell
                    colSpan={8}
                    className="py-10 text-center text-sm text-muted-foreground"
                  >
                    Selecione um torneio para ver os spots.
                  </TableCell>
                </TableRow>
              )}
              {filtered.map((s) => {
                const correct = s.hero_decision === s.icm_decision;
                const risk = riskLabel(s.risk_premium_pct);
                return (
                  <TableRow key={`${s.site}-${s.hand_id}`}>
                    <TableCell className="text-sm">{s.scenario}</TableCell>
                    <TableCell>
                      <Badge variant="secondary" className="text-[10px] font-normal">
                        {s.category}
                      </Badge>
                    </TableCell>
                    <TableCell className="num text-right text-xs">{s.stack}</TableCell>
                    <TableCell>
                      <Badge
                        variant="outline"
                        className={cn(
                          "text-[10px] font-normal",
                          (risk === "Crítico" || risk === "Alto") && "text-loss",
                        )}
                      >
                        {risk} ({s.risk_premium_pct.toFixed(0)}%)
                      </Badge>
                    </TableCell>
                    <TableCell
                      className={cn(
                        "num text-xs font-semibold",
                        correct ? "text-profit" : "text-loss",
                      )}
                    >
                      {s.hero_decision}
                    </TableCell>
                    <TableCell className="num text-xs text-muted-foreground">
                      {s.icm_decision}
                    </TableCell>
                    <TableCell className="text-right text-xs">
                      {correct ? (
                        <span className="text-muted-foreground">—</span>
                      ) : (
                        <Money value={-Math.abs(s.icm_ev_lost)} suffix=" BI" />
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button variant="outline" size="sm">
                        Revisar
                      </Button>
                    </TableCell>
                  </TableRow>
                );
              })}
              {!spotsQ.isLoading &&
                selectedKey &&
                selectedT?.has_payouts &&
                filtered.length === 0 && (
                  <TableRow>
                    <TableCell
                      colSpan={8}
                      className="py-10 text-center text-sm text-muted-foreground"
                    >
                      Nenhum spot encontrado para este filtro.
                    </TableCell>
                  </TableRow>
                )}
            </TableBody>
          </Table>
        </div>
      </Panel>
    </div>
  );
}
