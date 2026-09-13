import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Coins, Plus, Trash2 } from "lucide-react";

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
import { Textarea } from "@/components/ui/textarea";
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

// ---- Import em lote de premiação — cola manualmente o que você copiou
// da tela de resultados do PartyPoker/PokerStars/SharkScope. Sem
// automação contra o site de terceiro: é você quem copia e cola. ----
type BulkPayoutGroup = {
  site: string;
  tournament_id: string;
  name: string | null;
  prizes: number[];
};

function parseBulkPayouts(text: string): { groups: BulkPayoutGroup[]; errors: string[] } {
  const errors: string[] = [];
  const rows: {
    site: string;
    tournament_id: string;
    name: string;
    place: number;
    prize: number;
  }[] = [];

  text.split("\n").forEach((raw, idx) => {
    const line = raw.trim();
    if (!line || line.startsWith("#")) return;
    const parts = line
      .split(/[,;\t]+/)
      .map((p) => p.trim())
      .filter(Boolean);
    // site,tournament_id,[nome opcional — pode ter vírgulas, o que sobra
    // no meio depois de tirar site/tournament_id/colocação/prêmio é o
    // nome],colocação,prêmio. Sem nome = formato antigo, 4 campos.
    if (parts.length < 4) {
      errors.push(`Linha ${idx + 1}: esperado "site,tournament_id,[nome,]colocação,prêmio".`);
      return;
    }
    const [site, tournament_id, ...rest] = parts;
    const placeStr = rest[rest.length - 2]!;
    const prizeStr = rest[rest.length - 1]!;
    const name = rest.slice(0, rest.length - 2).join(", ");
    const place = Number(placeStr);
    const prize = Number(prizeStr.replace(/[^0-9.,-]/g, "").replace(",", "."));
    if (
      !site ||
      !tournament_id ||
      !Number.isFinite(place) ||
      place < 1 ||
      !Number.isFinite(prize)
    ) {
      errors.push(`Linha ${idx + 1}: valores inválidos ("${line}").`);
      return;
    }
    rows.push({ site, tournament_id, name, place, prize });
  });

  const byKey = new Map<string, typeof rows>();
  for (const r of rows) {
    const key = `${r.site}::${r.tournament_id}`;
    const list = byKey.get(key) ?? [];
    list.push(r);
    byKey.set(key, list);
  }

  const groups: BulkPayoutGroup[] = [];
  for (const [key, groupRows] of byKey) {
    const [site, tournament_id] = key.split("::");
    const maxPlace = Math.max(...groupRows.map((r) => r.place));
    const prizes = Array.from({ length: maxPlace }, () => 0);
    for (const r of groupRows) prizes[r.place - 1] = r.prize;
    const name = groupRows.find((r) => r.name)?.name ?? null;
    groups.push({ site: site!, tournament_id: tournament_id!, name, prizes });
  }
  return { groups, errors };
}

function IcmPage() {
  const queryClient = useQueryClient();
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

  // ---- Premiação: formulário manual do torneio selecionado ----
  const payoutsQ = useQuery({
    queryKey: ["icm-payouts", selectedKey],
    queryFn: () => icmApi.getPayouts(selectedT!.site, selectedT!.tournament_id),
    enabled: !!selectedT,
  });

  const [prizeInputs, setPrizeInputs] = useState<string[]>(["", ""]);
  // Nome do torneio — a hand history nunca trás isso (só o ID), então é
  // sempre preenchido à mão olhando a lista de torneios do site.
  const [nameInput, setNameInput] = useState("");

  // Recarrega o formulário sempre que troca de torneio ou os prêmios
  // salvos chegam — não roda a cada keystroke porque só depende de
  // selectedKey/payoutsQ.data.
  useEffect(() => {
    if (!selectedT) return;
    const saved = payoutsQ.data;
    setPrizeInputs(saved && saved.length > 0 ? saved.map((v) => String(v)) : ["", ""]);
    setNameInput(selectedT.name ?? "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedKey, payoutsQ.data]);

  const saveTournamentMutation = useMutation({
    mutationFn: async () => {
      const prizes = prizeInputs.map((v) => Number(v) || 0);
      await Promise.all([
        icmApi.setPayouts(selectedT!.site, selectedT!.tournament_id, prizes),
        // Só grava o nome se mudou algo — evita PUT à toa a cada save de premiação.
        nameInput.trim() !== (selectedT!.name ?? "")
          ? icmApi.setTournamentName(selectedT!.site, selectedT!.tournament_id, nameInput.trim())
          : Promise.resolve(),
      ]);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["icm-tournaments"] });
      queryClient.invalidateQueries({ queryKey: ["icm-payouts", selectedKey] });
      queryClient.invalidateQueries({ queryKey: ["icm-spots", selectedKey] });
    },
  });

  // ---- Premiação: import em lote (colar texto) ----
  const [bulkText, setBulkText] = useState("");
  const parsedBulk = useMemo(() => parseBulkPayouts(bulkText), [bulkText]);

  const bulkImportMutation = useMutation({
    mutationFn: async () => {
      const results: { key: string; ok: boolean; error?: string }[] = [];
      for (const g of parsedBulk.groups) {
        try {
          await Promise.all([
            icmApi.setPayouts(g.site, g.tournament_id, g.prizes),
            g.name ? icmApi.setTournamentName(g.site, g.tournament_id, g.name) : Promise.resolve(),
          ]);
          results.push({ key: `${g.site} · #${g.tournament_id}`, ok: true });
        } catch (e) {
          results.push({
            key: `${g.site} · #${g.tournament_id}`,
            ok: false,
            error: e instanceof Error ? e.message : String(e),
          });
        }
      }
      return results;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["icm-tournaments"] });
    },
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

      <div className="grid gap-4 xl:grid-cols-2">
        <Panel
          title="Premiação — torneio selecionado"
          subtitle={
            selectedT
              ? `${selectedT.site} · #${selectedT.tournament_id}`
              : "Selecione um torneio acima para configurar os prêmios"
          }
        >
          {!selectedT ? (
            <div className="p-8 text-center text-sm text-muted-foreground">
              Selecione um torneio para editar a premiação.
            </div>
          ) : (
            <div className="space-y-3 p-4">
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground" htmlFor="tournament-name">
                  Nome do torneio (a hand history não trás — olhe na lista do site)
                </label>
                <Input
                  id="tournament-name"
                  value={nameInput}
                  placeholder={`${selectedT.site} #${selectedT.tournament_id}`}
                  className="h-8 text-xs"
                  onChange={(e) => setNameInput(e.target.value)}
                />
              </div>

              <p className="text-xs text-muted-foreground">
                Prêmios em $ na ordem — 1º lugar primeiro.
              </p>
              <div className="space-y-2">
                {prizeInputs.map((v, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <span className="w-8 shrink-0 text-xs text-muted-foreground">{i + 1}º</span>
                    <Input
                      type="number"
                      step="0.01"
                      min="0"
                      value={v}
                      placeholder="0.00"
                      className="num h-8 text-xs"
                      onChange={(e) => {
                        const val = e.target.value;
                        setPrizeInputs((arr) => arr.map((x, idx) => (idx === i ? val : x)));
                      }}
                    />
                    <Button
                      variant="ghost"
                      size="icon"
                      className="size-8 shrink-0"
                      disabled={prizeInputs.length <= 1}
                      onClick={() => setPrizeInputs((arr) => arr.filter((_, idx) => idx !== i))}
                    >
                      <Trash2 className="size-3.5" />
                    </Button>
                  </div>
                ))}
              </div>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  className="h-8 text-xs"
                  onClick={() => setPrizeInputs((arr) => [...arr, ""])}
                >
                  <Plus className="mr-1 size-3.5" /> Lugar
                </Button>
                <Button
                  size="sm"
                  className="ml-auto h-8 text-xs"
                  disabled={saveTournamentMutation.isPending}
                  onClick={() => saveTournamentMutation.mutate()}
                >
                  Salvar torneio
                </Button>
              </div>
              {saveTournamentMutation.isSuccess && (
                <p className="text-xs text-profit">Nome e premiação salvos.</p>
              )}
              {saveTournamentMutation.isError && (
                <p className="text-xs text-loss">Erro ao salvar — tente de novo.</p>
              )}
            </div>
          )}
        </Panel>

        <Panel
          title="Importar premiação em lote"
          subtitle="Cole os dados copiados manualmente da tela de resultados (PartyPoker/PokerStars/SharkScope)"
        >
          <div className="space-y-3 p-4">
            <Textarea
              rows={5}
              className="num text-xs"
              placeholder={
                "partypoker,420849778,Sunday Major,1,1200.50\npartypoker,420849778,Sunday Major,2,780.00"
              }
              value={bulkText}
              onChange={(e) => setBulkText(e.target.value)}
            />
            <p className="text-[11px] text-muted-foreground">
              Uma linha por colocação:{" "}
              <span className="font-mono">site,tournament_id,[nome,]colocação,prêmio</span> — nome é
              opcional (repita em toda linha do torneio ou só numa, tanto faz) e{" "}
              <span className="font-mono">tournament_id</span> é o número depois de{" "}
              <span className="font-mono">#</span> no cabeçalho da mão (ex.: "MTT Tournament
              #420849778"), não o ID da mão em si. Vírgula, ponto e vírgula ou tab servem de
              separador. Linhas com # no início são ignoradas.
            </p>

            {parsedBulk.errors.length > 0 && (
              <div className="space-y-0.5 rounded-md border border-loss/40 bg-loss/5 p-2 text-[11px] text-loss">
                {parsedBulk.errors.slice(0, 5).map((e, i) => (
                  <p key={i}>{e}</p>
                ))}
                {parsedBulk.errors.length > 5 && (
                  <p>+{parsedBulk.errors.length - 5} erro(s) a mais</p>
                )}
              </div>
            )}

            {parsedBulk.groups.length > 0 && (
              <div className="overflow-x-auto rounded-md border border-border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Torneio</TableHead>
                      <TableHead>Nome</TableHead>
                      <TableHead className="text-right">Lugares</TableHead>
                      <TableHead className="text-right">Soma</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {parsedBulk.groups.map((g) => (
                      <TableRow key={`${g.site}::${g.tournament_id}`}>
                        <TableCell className="text-xs">
                          {g.site} · #{g.tournament_id}
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {g.name ?? "—"}
                        </TableCell>
                        <TableCell className="num text-right text-xs">{g.prizes.length}</TableCell>
                        <TableCell className="num text-right text-xs">
                          $
                          {g.prizes
                            .reduce((a, b) => a + b, 0)
                            .toLocaleString("pt-BR", { maximumFractionDigits: 2 })}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}

            <Button
              size="sm"
              className="h-8 text-xs"
              disabled={parsedBulk.groups.length === 0 || bulkImportMutation.isPending}
              onClick={() => bulkImportMutation.mutate()}
            >
              Importar
              {parsedBulk.groups.length > 0 ? ` ${parsedBulk.groups.length} torneio(s)` : ""}
            </Button>

            {bulkImportMutation.isSuccess && (
              <p
                className={cn(
                  "text-xs",
                  bulkImportMutation.data.every((r) => r.ok) ? "text-profit" : "text-loss",
                )}
              >
                {bulkImportMutation.data.filter((r) => r.ok).length}/
                {bulkImportMutation.data.length} torneio(s) importado(s).
                {bulkImportMutation.data
                  .filter((r) => !r.ok)
                  .map((r) => (
                    <span key={r.key} className="block">
                      {r.key}: {r.error}
                    </span>
                  ))}
              </p>
            )}
          </div>
        </Panel>
      </div>

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
