import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { Check, Loader2, X } from "lucide-react";

import { PageHeader, Panel, StatCard } from "@/components/lab";
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
import { icmApi, type IcmTournament } from "@/lib/api";

export const Route = createFileRoute("/torneios")({
  head: () => ({
    meta: [
      { title: "Torneios — PokerLab" },
      {
        name: "description",
        content:
          "Todos os torneios importados — ID, buy-in, datas, colocação e prêmio. Igual à tabela do banco, com filtros e edição direta.",
      },
    ],
  }),
  component: TorneiosPage,
});

// Timestamp vem como "2026-09-03T22:00:55" (ISO sem timezone, hora local
// da hand history) — sem lib de data, só fatiando a string mesmo.
function fmtDateTime(iso: string | null): string {
  if (!iso) return "—";
  const [datePart, timePart] = iso.split("T");
  if (!datePart) return iso;
  const [y, m, d] = datePart.split("-");
  const hm = timePart ? timePart.slice(0, 5) : "";
  return `${d}/${m}/${y}${hm ? ` ${hm}` : ""}`;
}

function TournamentRow({ t }: { t: IcmTournament }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState(t.name ?? "");
  const [position, setPosition] = useState(
    t.finish_position != null ? String(t.finish_position) : "",
  );
  const [prize, setPrize] = useState(t.prize != null ? String(t.prize) : "");
  const [prizeType, setPrizeType] = useState<"cash" | "ticket" | "">(t.prize_type ?? "");
  const [prizeNote, setPrizeNote] = useState(t.prize_note ?? "");

  // Ressincroniza se a linha mudar por baixo (outro filtro, refetch) —
  // não a cada keystroke, só quando os valores salvos mudam de fato.
  useEffect(() => {
    setName(t.name ?? "");
    setPosition(t.finish_position != null ? String(t.finish_position) : "");
    setPrize(t.prize != null ? String(t.prize) : "");
    setPrizeType(t.prize_type ?? "");
    setPrizeNote(t.prize_note ?? "");
  }, [t.site, t.tournament_id, t.name, t.finish_position, t.prize, t.prize_type, t.prize_note]);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["icm-tournaments"] });

  // Aviso de salvamento por linha: "Salvando…" enquanto o PUT está no ar,
  // "Salvo" por 2s depois de confirmado, "Erro" (fixo, não some sozinho)
  // se falhar — sem isso o usuário não tinha nenhum retorno visual de
  // que o onBlur realmente gravou algo.
  const [status, setStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const savedTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (savedTimeout.current) clearTimeout(savedTimeout.current);
    },
    [],
  );

  const markSaved = () => {
    setStatus("saved");
    setErrorMsg(null);
    if (savedTimeout.current) clearTimeout(savedTimeout.current);
    savedTimeout.current = setTimeout(() => setStatus("idle"), 2000);
  };

  const markError = (e: unknown) => {
    setStatus("error");
    setErrorMsg(e instanceof Error ? e.message : String(e));
  };

  const saveNameMutation = useMutation({
    mutationFn: (v: string) => icmApi.setTournamentName(t.site, t.tournament_id, v.trim()),
    onMutate: () => setStatus("saving"),
    onSuccess: () => {
      invalidate();
      markSaved();
    },
    onError: markError,
  });

  // Recebe os valores explícitos em vez de ler os states fechados no
  // closure — o Select de tipo de prêmio dispara o save no mesmo
  // handler que atualiza o state, antes do re-render, então o closure
  // ainda pegaria o valor antigo se lesse `prizeType` direto.
  const saveResultMutation = useMutation({
    mutationFn: (vars: { position: string; prize: string; prizeType: string; prizeNote: string }) =>
      icmApi.setTournamentResult(t.site, t.tournament_id, {
        finish_position: vars.position.trim() ? Number(vars.position) : null,
        prize: vars.prize.trim() ? Number(vars.prize) : null,
        prize_type: vars.prizeType ? (vars.prizeType as "cash" | "ticket") : null,
        prize_note: vars.prizeNote.trim() || null,
      }),
    onMutate: () => setStatus("saving"),
    onSuccess: () => {
      invalidate();
      markSaved();
    },
    onError: markError,
  });

  const positionDirty = position !== (t.finish_position != null ? String(t.finish_position) : "");
  const prizeDirty = prize !== (t.prize != null ? String(t.prize) : "");
  const prizeNoteDirty = prizeNote.trim() !== (t.prize_note ?? "");

  return (
    <TableRow>
      <TableCell className="text-xs text-muted-foreground">{t.site}</TableCell>
      <TableCell className="num text-xs">#{t.tournament_id}</TableCell>
      <TableCell>
        <Input
          value={name}
          placeholder="—"
          className="h-7 min-w-[140px] text-xs"
          onChange={(e) => setName(e.target.value)}
          onBlur={() => name.trim() !== (t.name ?? "") && saveNameMutation.mutate(name)}
        />
      </TableCell>
      <TableCell className="num text-right text-xs">
        {t.buyin != null ? `${t.currency ?? "$"}${t.buyin.toFixed(2)}` : "—"}
      </TableCell>
      <TableCell className="num text-xs text-muted-foreground" title={t.first_seen ?? undefined}>
        {fmtDateTime(t.first_seen)}
      </TableCell>
      <TableCell className="num text-xs text-muted-foreground" title={t.last_seen ?? undefined}>
        {fmtDateTime(t.last_seen)}
      </TableCell>
      <TableCell className="num text-right text-xs">{t.n_hands}</TableCell>
      <TableCell>
        <Input
          type="number"
          min="1"
          step="1"
          value={position}
          placeholder="—"
          className="num h-7 w-16 text-xs"
          onChange={(e) => setPosition(e.target.value)}
          onBlur={() =>
            (positionDirty || prizeDirty) &&
            saveResultMutation.mutate({ position, prize, prizeType, prizeNote })
          }
        />
      </TableCell>
      <TableCell>
        <Input
          type="number"
          min="0"
          step="0.01"
          value={prize}
          placeholder="0.00"
          className="num h-7 w-20 text-xs"
          onChange={(e) => setPrize(e.target.value)}
          onBlur={() =>
            (positionDirty || prizeDirty) &&
            saveResultMutation.mutate({ position, prize, prizeType, prizeNote })
          }
        />
      </TableCell>
      <TableCell>
        <Select
          value={prizeType || "none"}
          onValueChange={(v) => {
            const val = v === "none" ? "" : (v as "cash" | "ticket");
            setPrizeType(val);
            saveResultMutation.mutate({ position, prize, prizeType: val, prizeNote });
          }}
        >
          <SelectTrigger className="h-7 w-[110px] text-xs">
            <SelectValue placeholder="—" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="none" className="text-xs">
              —
            </SelectItem>
            <SelectItem value="cash" className="text-xs">
              Dinheiro
            </SelectItem>
            <SelectItem value="ticket" className="text-xs">
              Ticket
            </SelectItem>
          </SelectContent>
        </Select>
      </TableCell>
      <TableCell>
        <Input
          value={prizeNote}
          placeholder="ex.: classifiquei via satélite"
          className="h-7 min-w-[160px] text-xs"
          onChange={(e) => setPrizeNote(e.target.value)}
          onBlur={() =>
            prizeNoteDirty && saveResultMutation.mutate({ position, prize, prizeType, prizeNote })
          }
        />
      </TableCell>
      <TableCell
        className="w-24 text-[11px]"
        title={status === "error" ? (errorMsg ?? undefined) : undefined}
      >
        {status === "saving" && (
          <span className="inline-flex items-center gap-1 text-muted-foreground">
            <Loader2 className="size-3 animate-spin" /> Salvando…
          </span>
        )}
        {status === "saved" && (
          <span className="inline-flex items-center gap-1 text-profit">
            <Check className="size-3" /> Salvo
          </span>
        )}
        {status === "error" && (
          <span className="inline-flex items-center gap-1 text-loss">
            <X className="size-3" /> Erro ao salvar
          </span>
        )}
      </TableCell>
    </TableRow>
  );
}

function TorneiosPage() {
  const tournamentsQ = useQuery({
    queryKey: ["icm-tournaments"],
    queryFn: icmApi.tournaments,
  });
  const tournaments = tournamentsQ.data ?? [];

  const [search, setSearch] = useState("");
  const [siteFilter, setSiteFilter] = useState("Todos");
  const [buyinMin, setBuyinMin] = useState("");
  const [buyinMax, setBuyinMax] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const sites = useMemo(
    () => Array.from(new Set(tournaments.map((t) => t.site))).sort(),
    [tournaments],
  );

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return tournaments.filter((t) => {
      if (q && !t.tournament_id.includes(q) && !(t.name ?? "").toLowerCase().includes(q))
        return false;
      if (siteFilter !== "Todos" && t.site !== siteFilter) return false;
      if (buyinMin.trim() && (t.buyin ?? 0) < Number(buyinMin)) return false;
      if (buyinMax.trim() && (t.buyin ?? 0) > Number(buyinMax)) return false;
      const day = t.first_seen?.slice(0, 10);
      if (dateFrom.trim() && (!day || day < dateFrom)) return false;
      if (dateTo.trim() && (!day || day > dateTo)) return false;
      return true;
    });
  }, [tournaments, search, siteFilter, buyinMin, buyinMax, dateFrom, dateTo]);

  const clearFilters = () => {
    setSearch("");
    setSiteFilter("Todos");
    setBuyinMin("");
    setBuyinMax("");
    setDateFrom("");
    setDateTo("");
  };

  const totalBuyin = tournaments.reduce((a, t) => a + (t.buyin ?? 0), 0);
  const withPayouts = tournaments.filter((t) => t.has_payouts).length;
  const withResult = tournaments.filter((t) => t.finish_position != null).length;

  return (
    <div className="space-y-5">
      <PageHeader
        title="Torneios"
        description={
          tournamentsQ.isLoading
            ? "Carregando…"
            : `${tournaments.length} torneios importados · ${filtered.length} com os filtros atuais`
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="Torneios importados" value={String(tournaments.length)} />
        <StatCard label="Com premiação configurada" value={String(withPayouts)} tone="profit" />
        <StatCard label="Com colocação registrada" value={String(withResult)} />
        <StatCard label="Total em buy-ins" value={`$${totalBuyin.toFixed(2)}`} />
      </div>

      <Panel title="Filtros">
        <div className="flex flex-wrap items-end gap-3 p-4">
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground" htmlFor="t-search">
              Buscar (ID ou nome)
            </label>
            <Input
              id="t-search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="420849778…"
              className="h-8 w-[200px] text-xs"
            />
          </div>
          {sites.length > 1 && (
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">Site</label>
              <Select value={siteFilter} onValueChange={setSiteFilter}>
                <SelectTrigger className="h-8 w-[140px] text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="Todos">Todos</SelectItem>
                  {sites.map((s) => (
                    <SelectItem key={s} value={s}>
                      {s}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground" htmlFor="t-buyin-min">
              Buy-in mín.
            </label>
            <Input
              id="t-buyin-min"
              type="number"
              min="0"
              step="0.01"
              value={buyinMin}
              onChange={(e) => setBuyinMin(e.target.value)}
              placeholder="0"
              className="num h-8 w-[90px] text-xs"
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground" htmlFor="t-buyin-max">
              Buy-in máx.
            </label>
            <Input
              id="t-buyin-max"
              type="number"
              min="0"
              step="0.01"
              value={buyinMax}
              onChange={(e) => setBuyinMax(e.target.value)}
              placeholder="—"
              className="num h-8 w-[90px] text-xs"
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground" htmlFor="t-date-from">
              De
            </label>
            <Input
              id="t-date-from"
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="num h-8 text-xs"
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground" htmlFor="t-date-to">
              Até
            </label>
            <Input
              id="t-date-to"
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="num h-8 text-xs"
            />
          </div>
          <Button variant="outline" size="sm" className="h-8 text-xs" onClick={clearFilters}>
            Limpar filtros
          </Button>
        </div>
      </Panel>

      <Panel
        title="Torneios importados"
        subtitle="Colocação e prêmio são sempre manuais — a hand history não trás isso, só ID/buy-in/data"
      >
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Site</TableHead>
                <TableHead>ID</TableHead>
                <TableHead>Nome</TableHead>
                <TableHead className="text-right">Buy-in</TableHead>
                <TableHead>Início</TableHead>
                <TableHead>Fim</TableHead>
                <TableHead className="text-right">Mãos</TableHead>
                <TableHead>Colocação</TableHead>
                <TableHead>Prêmio</TableHead>
                <TableHead>Tipo</TableHead>
                <TableHead>Nota</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {tournamentsQ.isLoading && (
                <TableRow>
                  <TableCell
                    colSpan={12}
                    className="py-10 text-center text-sm text-muted-foreground"
                  >
                    Carregando…
                  </TableCell>
                </TableRow>
              )}
              {!tournamentsQ.isLoading && filtered.length === 0 && (
                <TableRow>
                  <TableCell
                    colSpan={12}
                    className="py-10 text-center text-sm text-muted-foreground"
                  >
                    Nenhum torneio encontrado com esses filtros.
                  </TableCell>
                </TableRow>
              )}
              {filtered.map((t) => (
                <TournamentRow key={`${t.site}::${t.tournament_id}`} t={t} />
              ))}
            </TableBody>
          </Table>
        </div>
      </Panel>
    </div>
  );
}
