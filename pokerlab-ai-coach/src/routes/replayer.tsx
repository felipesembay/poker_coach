import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ChevronLeft,
  ChevronRight,
  Gauge,
  Pause,
  Play,
  SkipBack,
  SkipForward,
  Star,
  Search,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { z } from "zod";

import { Hole, Money, PageHeader, Panel } from "@/components/lab";
import { PokerTable, type TableSeat } from "@/components/poker-table";
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
import { Separator } from "@/components/ui/separator";
import { Slider } from "@/components/ui/slider";
import { Textarea } from "@/components/ui/textarea";
import { icmApi, replayerApi, handsApi, type ReplayHand, type HandSummary } from "@/lib/api";
import { cn } from "@/lib/utils";

const replayerSearchSchema = z.object({
  site: z.string().optional(),
  handId: z.string().optional(),
});

const POSITIONS = ["UTG", "HJ", "CO", "BTN", "SB", "BB"];
const PLAYER_COUNTS = ["2", "3", "4", "5", "6", "7", "8", "9"];
const TRI = ["Todos", "Sim", "Não"] as const;
type Tri = (typeof TRI)[number];

type Filters = {
  q: string;
  tournamentKey: string; // "" | "site::tournament_id"
  position: string; // "" | POSITIONS[number]
  result: "Todos" | "Ganhou" | "Perdeu";
  showdown: Tri;
  allIn: Tri;
  favorite: Tri;
  nPlayers: string; // "" | PLAYER_COUNTS[number]
  bbRange: [number, number];
};

const DEFAULT_FILTERS: Filters = {
  q: "",
  tournamentKey: "",
  position: "",
  result: "Todos",
  showdown: "Todos",
  allIn: "Todos",
  favorite: "Todos",
  nPlayers: "",
  bbRange: [0, 100],
};

function triToBool(v: Tri): boolean | undefined {
  return v === "Sim" ? true : v === "Não" ? false : undefined;
}

export const Route = createFileRoute("/replayer")({
  validateSearch: replayerSearchSchema,
  head: () => ({
    meta: [
      { title: "Replayer — PokerLab" },
      {
        name: "description",
        content:
          "Reveja cada mão passo a passo com análise da IA, pot odds, equidade, SPR e pressão de ICM.",
      },
      { property: "og:title", content: "Replayer — PokerLab" },
      {
        property: "og:description",
        content: "Mesa interativa com timeline de ações e painel técnico de análise.",
      },
    ],
  }),
  component: Replayer,
});

/** Monta a descrição curta de um step para a timeline. */
function stepText(step: ReplayHand["steps"][number]): string {
  if (step.action === "deal") {
    const cards = step.board_so_far.split(" ").filter(Boolean);
    const dealt = cards.slice(-(step.street === "flop" ? 3 : 1));
    return `Board: ${dealt.join(" ")} (all-in, sem mais ação)`;
  }
  if (step.action === "resolve") return "Mão resolvida";
  if (!step.player) return step.street;
  const who = step.player;
  const action = step.action;
  if (step.amount) return `${who}: ${action} ${step.amount.toLocaleString("pt-BR")}`;
  return `${who}: ${action}`;
}

// ---- Componente principal ----

function FilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (v: string) => void;
}) {
  return (
    <div className="space-y-1">
      <label className="text-[11px] text-muted-foreground">{label}</label>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger className="h-8 text-xs">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {options.map((o) => (
            <SelectItem key={o} value={o} className="text-xs">
              {o}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

function Replayer() {
  const { site, handId } = Route.useSearch();
  const navigate = useNavigate({ from: "/replayer" });
  const queryClient = useQueryClient();
  const [step, setStep] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<0.5 | 1 | 2>(1);
  const [note, setNote] = useState("");
  const [noteSaved, setNoteSaved] = useState(false);
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [qInput, setQInput] = useState("");

  // Busca livre com debounce simples pra não refazer a query a cada tecla
  useEffect(() => {
    const t = setTimeout(() => setFilters((f) => ({ ...f, q: qInput })), 300);
    return () => clearTimeout(t);
  }, [qInput]);

  // Torneios pro seletor — reusa o mesmo endpoint do ICM (já filtra só
  // torneios com mãos importadas).
  const tournamentsQ = useQuery({ queryKey: ["icm-tournaments"], queryFn: icmApi.tournaments });
  const [tSite, tTid] = filters.tournamentKey
    ? filters.tournamentKey.split("::")
    : [undefined, undefined];

  // Lista de mãos filtradas — sempre visível na lateral e usada pra
  // "mão anterior"/"próxima mão" percorrer o torneio/sessão inteiro.
  const resultParam =
    filters.result === "Ganhou" ? "win" : filters.result === "Perdeu" ? "loss" : undefined;
  const showdownParam = triToBool(filters.showdown);
  const allInParam = triToBool(filters.allIn);
  const favoriteParam = triToBool(filters.favorite);

  const listQ = useQuery({
    queryKey: ["replayer-search", filters],
    queryFn: () =>
      replayerApi.search({
        ...(tSite ? { site: tSite } : {}),
        ...(tTid ? { tournament_id: tTid } : {}),
        ...(filters.position ? { position: filters.position } : {}),
        ...(resultParam ? { result: resultParam } : {}),
        ...(showdownParam !== undefined ? { showdown: showdownParam } : {}),
        ...(allInParam !== undefined ? { all_in: allInParam } : {}),
        ...(favoriteParam !== undefined ? { favorite: favoriteParam } : {}),
        ...(filters.nPlayers ? { n_players: Number(filters.nPlayers) } : {}),
        ...(filters.bbRange[0] > 0 ? { bb_min: filters.bbRange[0] } : {}),
        ...(filters.bbRange[1] < 100 ? { bb_max: filters.bbRange[1] } : {}),
        ...(filters.q ? { q: filters.q } : {}),
        limit: 300,
      }),
  });
  const hands = listQ.data ?? [];
  const currentIndex = hands.findIndex((h) => h.site === site && h.hand_id === handId);

  // Busca a mão pelo par site+handId
  const handQ = useQuery({
    queryKey: ["replay", site, handId],
    queryFn: () => replayerApi.get(site!, handId!),
    enabled: !!site && !!handId,
  });

  const hand = handQ.data;

  // ICM (Fold/Call/Push com $EV real) — só faz sentido com premiação
  // salva pro torneio dessa mão; reusa a mesma lista de torneios do
  // seletor de filtro pra saber se já tem `has_payouts`.
  const currentTournament = tournamentsQ.data?.find(
    (t) => t.site === hand?.site && t.tournament_id === hand?.tournament_id,
  );
  const icmHandQ = useQuery({
    queryKey: ["icm-hand", hand?.site, hand?.hand_id],
    queryFn: () => icmApi.hand(hand!.site, hand!.hand_id, true),
    enabled: !!hand && !!currentTournament?.has_payouts,
  });

  // Sincroniza nota e volta pro início ao trocar de mão
  useEffect(() => {
    if (hand) {
      setNote(hand.note ?? "");
      setNoteSaved(false);
      setStep(0);
      setPlaying(false);
    }
  }, [hand?.hand_id]);

  // Autoplay: o botão "Play" só ligava o estado, sem nada avançando os
  // passos de verdade — a mão parecia travada (geralmente no preflop,
  // o passo inicial). Avança 1 ação por vez em intervalos, na velocidade
  // escolhida, e para sozinho ao chegar no fim da mão.
  const stepCount = hand?.steps.length ?? 0;
  useEffect(() => {
    if (!playing || stepCount === 0) return;
    if (step >= stepCount - 1) {
      setPlaying(false);
      return;
    }
    const delay = 1400 / speed;
    const t = setTimeout(() => setStep((s) => Math.min(stepCount - 1, s + 1)), delay);
    return () => clearTimeout(t);
  }, [playing, step, stepCount, speed]);

  // Mutation: salvar nota
  const noteMutation = useMutation({
    mutationFn: () => handsApi.setNote(hand!.site, hand!.hand_id, note),
    onSuccess: () => {
      setNoteSaved(true);
      queryClient.invalidateQueries({ queryKey: ["replay", site, handId] });
    },
  });

  // Mutation: togglear favorito
  const favMutation = useMutation({
    mutationFn: (fav: boolean) => handsApi.setFavorite(hand!.site, hand!.hand_id, fav),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["replay", site, handId] });
      queryClient.invalidateQueries({ queryKey: ["replayer-search"] });
    },
  });

  function openHand(h: { site: string; hand_id: string }) {
    navigate({ search: (prev) => ({ ...prev, site: h.site, handId: h.hand_id }) });
  }

  function clearFilters() {
    setFilters(DEFAULT_FILTERS);
    setQInput("");
  }

  const hasFilters = Boolean(
    filters.q ||
    filters.tournamentKey ||
    filters.position ||
    filters.result !== "Todos" ||
    filters.showdown !== "Todos" ||
    filters.allIn !== "Todos" ||
    filters.favorite !== "Todos" ||
    filters.nPlayers ||
    filters.bbRange[0] !== 0 ||
    filters.bbRange[1] !== 100,
  );

  // ---- Painel de filtros + mãos filtradas (sempre visível) ----
  const filtersPanel = (
    <div className="space-y-4">
      <Panel title="Filtros" subtitle="Encontre o spot exato">
        <div className="space-y-3 p-4">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={qInput}
              onChange={(e) => setQInput(e.target.value)}
              placeholder="ID, cartas, board, notas, tags…"
              className="h-9 pl-8 pr-8 text-sm"
            />
            {qInput && (
              <button
                type="button"
                onClick={() => setQInput("")}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                aria-label="Limpar busca"
              >
                <X className="size-3.5" />
              </button>
            )}
          </div>

          <div className="space-y-1">
            <label className="text-[11px] text-muted-foreground">Torneio</label>
            <Select
              value={filters.tournamentKey || "__all"}
              onValueChange={(v) =>
                setFilters((f) => ({ ...f, tournamentKey: v === "__all" ? "" : v }))
              }
            >
              <SelectTrigger className="h-8 text-xs">
                <SelectValue placeholder="Todos" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__all" className="text-xs">
                  Todos
                </SelectItem>
                {(tournamentsQ.data ?? []).map((t) => (
                  <SelectItem
                    key={`${t.site}::${t.tournament_id}`}
                    value={`${t.site}::${t.tournament_id}`}
                    className="text-xs"
                  >
                    {t.name ?? `${t.site} #${t.tournament_id}`}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <FilterSelect
              label="Posição"
              value={filters.position || "Todas"}
              options={["Todas", ...POSITIONS]}
              onChange={(v) => setFilters((f) => ({ ...f, position: v === "Todas" ? "" : v }))}
            />
            <FilterSelect
              label="Jogadores"
              value={filters.nPlayers || "Todos"}
              options={["Todos", ...PLAYER_COUNTS]}
              onChange={(v) => setFilters((f) => ({ ...f, nPlayers: v === "Todos" ? "" : v }))}
            />
            <FilterSelect
              label="Resultado"
              value={filters.result}
              options={["Todos", "Ganhou", "Perdeu"]}
              onChange={(v) => setFilters((f) => ({ ...f, result: v as Filters["result"] }))}
            />
            <FilterSelect
              label="Showdown"
              value={filters.showdown}
              options={[...TRI]}
              onChange={(v) => setFilters((f) => ({ ...f, showdown: v as Tri }))}
            />
            <FilterSelect
              label="All-in"
              value={filters.allIn}
              options={[...TRI]}
              onChange={(v) => setFilters((f) => ({ ...f, allIn: v as Tri }))}
            />
            <FilterSelect
              label="Favoritos"
              value={filters.favorite}
              options={[...TRI]}
              onChange={(v) => setFilters((f) => ({ ...f, favorite: v as Tri }))}
            />
          </div>

          <div className="space-y-1.5 pt-1">
            <div className="flex items-center justify-between text-[11px] text-muted-foreground">
              <span>Stack mínimo</span>
              <span className="num">{filters.bbRange[0]} BB</span>
            </div>
            <Slider
              min={0}
              max={100}
              step={1}
              value={[filters.bbRange[0]]}
              onValueChange={(v) => {
                const val = v[0] ?? filters.bbRange[0];
                setFilters((f) => ({ ...f, bbRange: [Math.min(val, f.bbRange[1]), f.bbRange[1]] }));
              }}
            />
          </div>
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-[11px] text-muted-foreground">
              <span>Stack máximo</span>
              <span className="num">{filters.bbRange[1]} BB</span>
            </div>
            <Slider
              min={0}
              max={100}
              step={1}
              value={[filters.bbRange[1]]}
              onValueChange={(v) => {
                const val = v[0] ?? filters.bbRange[1];
                setFilters((f) => ({ ...f, bbRange: [f.bbRange[0], Math.max(val, f.bbRange[0])] }));
              }}
            />
          </div>

          {hasFilters && (
            <Button variant="outline" size="sm" className="w-full" onClick={clearFilters}>
              Limpar filtros
            </Button>
          )}
        </div>
      </Panel>

      <Panel
        title="Mãos filtradas"
        subtitle={`${hands.length} mão${hands.length === 1 ? "" : "s"} encontrada${hands.length === 1 ? "" : "s"}`}
      >
        {listQ.isLoading && (
          <p className="p-6 text-center text-sm text-muted-foreground">Carregando…</p>
        )}
        {!listQ.isLoading && hands.length === 0 && (
          <p className="p-6 text-center text-sm text-muted-foreground">Nenhuma mão encontrada.</p>
        )}
        <div className="max-h-[560px] divide-y divide-border overflow-y-auto">
          {hands.map((h: HandSummary) => {
            const active = h.site === site && h.hand_id === handId;
            return (
              <button
                key={`${h.site}-${h.hand_id}`}
                type="button"
                onClick={() => openHand(h)}
                className={cn(
                  "block w-full px-4 py-2.5 text-left transition-colors hover:bg-accent/40",
                  active && "bg-primary/10",
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="num text-xs text-muted-foreground">#{h.hand_id.slice(-8)}</span>
                  <Money value={h.net_bb} suffix=" BB" />
                </div>
                <div className="mt-1 flex items-center gap-2">
                  {h.hero_cards ? <Hole cards={h.hero_cards.split(" ")} size="sm" /> : null}
                  {h.position && (
                    <Badge variant="secondary" className="text-[10px]">
                      {h.position}
                    </Badge>
                  )}
                  <span className="num text-[11px] text-muted-foreground">
                    {h.stack_bb != null ? `${h.stack_bb} BB` : "—"}
                  </span>
                </div>
                <p className="mt-1 truncate text-[11px] text-muted-foreground">
                  {h.tournament_name ?? h.tournament_id}
                  {h.ts ? ` · ${new Date(h.ts).toLocaleDateString("pt-BR")}` : ""}
                </p>
              </button>
            );
          })}
        </div>
      </Panel>
    </div>
  );

  // ---- VIEW: sem mão selecionada ----
  if (!site || !handId) {
    return (
      <div className="space-y-5">
        <PageHeader
          title="Replayer"
          description={`${hands.length} mão${hands.length === 1 ? "" : "s"} filtrada${hands.length === 1 ? "" : "s"} · selecione uma para rever passo a passo`}
        />
        <div className="grid gap-4 xl:grid-cols-[300px_minmax(0,1fr)]">
          {filtersPanel}
          <Panel>
            <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">
              Selecione uma mão na lista à esquerda para começar.
            </div>
          </Panel>
        </div>
      </div>
    );
  }

  // ---- VIEW: carregando ----
  if (handQ.isLoading) {
    return (
      <div className="grid gap-4 xl:grid-cols-[300px_minmax(0,1fr)]">
        {filtersPanel}
        <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">
          Carregando mão…
        </div>
      </div>
    );
  }

  if (handQ.isError || !hand) {
    return (
      <div className="grid gap-4 xl:grid-cols-[300px_minmax(0,1fr)]">
        {filtersPanel}
        <div className="flex h-64 flex-col items-center justify-center gap-3">
          <p className="text-sm text-loss">Erro ao carregar a mão.</p>
        </div>
      </div>
    );
  }

  // ---- Dados do step atual ----
  const steps = hand.steps;
  const currentStep = steps[step];
  const boardCards = currentStep ? currentStep.board_so_far.split(" ").filter(Boolean) : [];
  const pot = currentStep?.pot_after ?? 0;
  const heroCards = hand.hero_cards ? hand.hero_cards.split(" ") : [];

  // Última ação de cada jogador até o step atual
  const lastActionMap: Record<string, { action: string; amount: number; all_in: boolean }> = {};
  for (let i = 0; i <= step; i++) {
    const s = steps[i];
    if (s) lastActionMap[s.player] = { action: s.action, amount: s.amount, all_in: s.all_in };
  }

  const tableSeats: TableSeat[] = hand.seats.map((s) => {
    const la = lastActionMap[s.player];
    const stackNow = currentStep?.stacks_after[s.player] ?? s.starting_stack;
    const actionText = la
      ? la.all_in
        ? `All-in ${la.amount.toLocaleString("pt-BR")}`
        : la.amount
          ? `${la.action} ${la.amount.toLocaleString("pt-BR")}`
          : la.action
      : null;
    const actionTone: TableSeat["actionTone"] = la?.all_in
      ? "allin"
      : la?.action === "Fold" || la?.action === "fold"
        ? "fold"
        : "normal";
    return {
      key: s.player,
      position: s.position,
      label: s.player,
      stack: stackNow,
      isHero: s.is_hero,
      cards: s.is_hero ? heroCards : s.cards ? s.cards.split(" ") : null,
      actionText,
      actionTone,
    };
  });

  const ia = hand.painel_ia;

  const streetLabels: Record<string, string> = {
    preflop: "Preflop",
    flop: "Flop",
    turn: "Turn",
    river: "River",
  };
  const streetEntries = [
    ...Object.entries(hand.street_first_index)
      .sort((a, b) => a[1] - b[1])
      .map(([street, idx]) => ({ key: street, label: streetLabels[street] ?? street, idx })),
    { key: "showdown", label: "Showdown", idx: Math.max(0, steps.length - 1) },
  ];
  const currentStreetIdx = [...streetEntries].reverse().find((e) => e.idx <= step)?.idx ?? 0;

  const heroSeat = hand.seats.find((s) => s.is_hero);
  const heroStackNowChips =
    currentStep?.stacks_after[hand.hero ?? ""] ?? heroSeat?.starting_stack ?? null;
  const heroStackBB =
    heroStackNowChips != null && hand.bb ? (heroStackNowChips / hand.bb).toFixed(1) : null;
  const tournamentLabel = hand.tournament_name
    ? `${hand.tournament_name}${hand.buyin ? ` $${hand.buyin}` : ""}`
    : `torneio #${hand.tournament_id}`;

  const description = [
    `${hands.length} mão${hands.length === 1 ? "" : "s"} filtrada${hands.length === 1 ? "" : "s"}`,
    `#${hand.hand_id.slice(-8)}`,
    tournamentLabel,
    heroSeat?.position && heroStackBB ? `Hero ${heroSeat.position} com ${heroStackBB} BB` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div className="space-y-5">
      <PageHeader
        title="Replayer"
        description={description}
        actions={
          <>
            {hasFilters && (
              <Button variant="outline" size="sm" onClick={clearFilters}>
                Limpar filtros
              </Button>
            )}
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                const prev = hands[currentIndex - 1];
                if (prev) openHand(prev);
              }}
              disabled={currentIndex <= 0}
            >
              <ChevronLeft className="mr-1 size-3.5" /> Mão anterior
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                const next = hands[currentIndex + 1];
                if (next) openHand(next);
              }}
              disabled={currentIndex < 0 || currentIndex >= hands.length - 1}
            >
              Próxima mão <ChevronRight className="ml-1 size-3.5" />
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => favMutation.mutate(!hand.favorite)}
              disabled={favMutation.isPending}
            >
              <Star
                className={cn("mr-1.5 size-3.5", hand.favorite && "fill-primary text-primary")}
              />
              {hand.favorite ? "Favoritado" : "Favoritar"}
            </Button>
          </>
        }
      />

      <div className="grid gap-4 xl:grid-cols-[280px_minmax(0,1fr)_320px]">
        {filtersPanel}

        <div className="space-y-4">
          {/* Mesa */}
          <Panel>
            <div className="flex flex-wrap items-center gap-1 border-b border-border px-4 py-2.5">
              {streetEntries.map((e, i) => (
                <span key={e.key} className="flex items-center gap-1">
                  {i > 0 && <ChevronRight className="size-3 text-muted-foreground" />}
                  <button
                    type="button"
                    onClick={() => setStep(e.idx)}
                    className={cn(
                      "rounded px-2 py-1 text-xs font-medium transition-colors",
                      currentStreetIdx === e.idx
                        ? "bg-primary/15 text-primary"
                        : "text-muted-foreground hover:text-foreground",
                    )}
                  >
                    {e.label}
                  </button>
                </span>
              ))}
            </div>

            <PokerTable
              seats={tableSeats}
              board={boardCards}
              pot={pot}
              cardSize="2xl"
              seatCardSize="xl"
            />

            {/* Controles */}
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border px-4 py-3">
              <div className="flex items-center gap-1.5">
                <Button
                  variant="outline"
                  size="icon"
                  onClick={() => setStep(0)}
                  aria-label="Ir para o início"
                >
                  <SkipBack className="size-4" />
                </Button>
                <Button
                  variant="outline"
                  size="icon"
                  onClick={() => setStep((s) => Math.max(0, s - 1))}
                  aria-label="Ação anterior"
                >
                  <ChevronLeft className="size-4" />
                </Button>
                <Button
                  variant={playing ? "secondary" : "default"}
                  size="sm"
                  onClick={() => {
                    if (!playing && step >= steps.length - 1) setStep(0);
                    setPlaying((p) => !p);
                  }}
                >
                  {playing ? (
                    <>
                      <Pause className="mr-1.5 size-3.5" /> Pause
                    </>
                  ) : (
                    <>
                      <Play className="mr-1.5 size-3.5" /> Play
                    </>
                  )}
                </Button>
                <Button
                  variant="outline"
                  size="icon"
                  onClick={() => setStep((s) => Math.min(steps.length - 1, s + 1))}
                  aria-label="Próxima ação"
                >
                  <ChevronRight className="size-4" />
                </Button>
                <Button
                  variant="outline"
                  size="icon"
                  onClick={() => setStep(steps.length - 1)}
                  aria-label="Ir para o fim"
                >
                  <SkipForward className="size-4" />
                </Button>
              </div>
              <div className="flex items-center gap-2">
                <Gauge className="size-3.5 text-muted-foreground" />
                {([0.5, 1, 2] as const).map((v) => (
                  <Button
                    key={v}
                    variant={v === speed ? "secondary" : "ghost"}
                    size="sm"
                    className="num h-7 px-2 text-xs"
                    onClick={() => setSpeed(v)}
                  >
                    {v}x
                  </Button>
                ))}
              </div>
              <span className="num text-xs text-muted-foreground">
                Ação {step + 1} de {steps.length}
              </span>
            </div>
          </Panel>

          {/* Timeline */}
          <Panel title="Timeline" subtitle="Sequência completa da mão">
            <ol className="divide-y divide-border">
              {steps.map((t, i) => (
                <li
                  key={t.order}
                  className={cn(
                    "grid cursor-pointer grid-cols-[64px_minmax(0,1fr)_auto] items-center gap-3 px-4 py-2.5 transition-colors",
                    i === step ? "bg-primary/10" : "hover:bg-accent/40",
                  )}
                  onClick={() => setStep(i)}
                >
                  <span className="num text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
                    {t.street}
                  </span>
                  <span className="truncate text-xs">{stepText(t)}</span>
                  <span className="num shrink-0 text-[11px] text-muted-foreground">
                    {t.pot_after ? `Pot ${t.pot_after.toLocaleString("pt-BR")}` : ""}
                  </span>
                </li>
              ))}
            </ol>
          </Panel>
        </div>

        {/* Painel lateral */}
        <div className="space-y-4">
          {/* Análise da IA */}
          <Panel title="Análise da IA" subtitle="Nash equilibrium · MTT">
            <div className="space-y-3 p-4 text-sm leading-relaxed">
              {!ia.in_scope ? (
                <p className="text-muted-foreground">
                  {ia.reason ?? "Spot fora do escopo da análise push/fold."}
                </p>
              ) : (
                <>
                  <p>
                    A decisão do Hero foi{" "}
                    <strong
                      className={
                        ia.hero_decision === ia.nash_decision ? "text-profit" : "text-loss"
                      }
                    >
                      {ia.hero_decision === ia.nash_decision ? "correta" : "incorreta"}
                    </strong>
                    {ia.nash_decision && (
                      <>
                        {" "}
                        — a jogada Nash é <strong>{ia.nash_decision}</strong>.
                      </>
                    )}
                  </p>
                  {ia.ev_push_bb != null && (
                    <p className="text-muted-foreground">
                      EV do shove: <strong>{ia.ev_push_bb.toFixed(2)} BB</strong>
                      {ia.ev_lost_bb != null && ia.ev_lost_bb > 0 && (
                        <>
                          {" "}
                          · EV perdido:{" "}
                          <strong className="text-loss">−{ia.ev_lost_bb.toFixed(2)} BB</strong>
                        </>
                      )}
                    </p>
                  )}
                  <Badge
                    variant="outline"
                    className={ia.hero_decision === ia.nash_decision ? "text-profit" : "text-loss"}
                  >
                    {ia.hero_decision === ia.nash_decision
                      ? `Decisão correta · +${(ia.ev_push_bb ?? 0).toFixed(2)} BB EV`
                      : `Decisão incorreta · −${(ia.ev_lost_bb ?? 0).toFixed(2)} BB perdido`}
                  </Badge>
                </>
              )}
            </div>
          </Panel>

          {/* Análise ICM */}
          <Panel title="Análise ICM" subtitle="Fold/Call/Push · $EV real do payout">
            <div className="space-y-3 p-4 text-sm leading-relaxed">
              {!currentTournament?.has_payouts ? (
                <p className="text-muted-foreground">
                  Cadastre a premiação desse torneio em{" "}
                  <Link to="/icm" className="text-primary underline">
                    ICM
                  </Link>{" "}
                  pra habilitar essa análise — sem ela o $EV seria inventado.
                </p>
              ) : icmHandQ.isLoading ? (
                <p className="text-muted-foreground">Calculando ICM…</p>
              ) : !icmHandQ.data?.in_scope ? (
                <p className="text-muted-foreground">
                  {icmHandQ.data?.reason ?? "Spot fora do escopo do motor de ICM."}
                </p>
              ) : (
                <>
                  <p>
                    A decisão do Hero foi{" "}
                    <strong
                      className={
                        icmHandQ.data.hero_decision === icmHandQ.data.icm_decision
                          ? "text-profit"
                          : "text-loss"
                      }
                    >
                      {icmHandQ.data.hero_decision === icmHandQ.data.icm_decision
                        ? "correta"
                        : "incorreta"}
                    </strong>
                    {icmHandQ.data.icm_decision && (
                      <>
                        {" "}
                        — o ICM manda <strong>{icmHandQ.data.icm_decision}</strong>.
                      </>
                    )}
                  </p>
                  {icmHandQ.data.icm_ev_fold != null && icmHandQ.data.icm_ev_push != null && (
                    <p className="text-muted-foreground">
                      $EV fold: <strong>${icmHandQ.data.icm_ev_fold.toFixed(2)}</strong> · $EV push:{" "}
                      <strong>${icmHandQ.data.icm_ev_push.toFixed(2)}</strong>
                      {icmHandQ.data.icm_ev_lost != null && icmHandQ.data.icm_ev_lost > 0 && (
                        <>
                          {" "}
                          · $EV perdido:{" "}
                          <strong className="text-loss">
                            −${icmHandQ.data.icm_ev_lost.toFixed(2)}
                          </strong>
                        </>
                      )}
                    </p>
                  )}
                  {icmHandQ.data.risk_premium_pct != null && (
                    <p className="text-muted-foreground">
                      Prêmio de risco do ICM:{" "}
                      <strong>{icmHandQ.data.risk_premium_pct.toFixed(1)}%</strong> mais tight que
                      chip EV
                      {icmHandQ.data.effective_bb != null && (
                        <> · efetivo {icmHandQ.data.effective_bb} BB</>
                      )}
                    </p>
                  )}
                  <Badge
                    variant="outline"
                    className={
                      icmHandQ.data.hero_decision === icmHandQ.data.icm_decision
                        ? "text-profit"
                        : "text-loss"
                    }
                  >
                    {icmHandQ.data.hero_decision === icmHandQ.data.icm_decision
                      ? "Decisão correta pelo ICM"
                      : `Decisão incorreta · −$${(icmHandQ.data.icm_ev_lost ?? 0).toFixed(2)} perdido`}
                  </Badge>
                </>
              )}
            </div>
          </Panel>

          {/* Métricas */}
          <Panel title="Métricas">
            <dl className="divide-y divide-border">
              {[
                { label: "Torneio", value: hand.tournament_name ?? `#${hand.tournament_id}` },
                { label: "Buy-in", value: hand.buyin != null ? `$${hand.buyin}` : "—" },
                {
                  label: "Data",
                  value: hand.ts ? new Date(hand.ts).toLocaleDateString("pt-BR") : "—",
                },
                {
                  label: "Blinds",
                  value: `${hand.sb}/${hand.bb}${hand.ante ? ` (${hand.ante} ante)` : ""}`,
                },
                {
                  label: "Hero",
                  value: hand.hero
                    ? `${hand.hero}${heroSeat?.position ? ` · ${heroSeat.position}` : ""}`
                    : "—",
                },
                { label: "Cartas", value: hand.hero_cards ?? "—" },
                { label: "Assentos", value: String(hand.seats.length) },
              ].map((m) => (
                <div key={m.label} className="flex items-center justify-between gap-3 px-4 py-2.5">
                  <dt className="text-xs text-muted-foreground">{m.label}</dt>
                  <dd className="num text-sm font-semibold">{m.value}</dd>
                </div>
              ))}
            </dl>
          </Panel>

          {/* Notas e Tags */}
          <Panel title="Notas">
            <div className="space-y-3 p-4">
              <Textarea
                value={note}
                onChange={(e) => {
                  setNote(e.target.value);
                  setNoteSaved(false);
                }}
                placeholder="Anote a leitura, o plano para o spot e o que treinar depois…"
                className="min-h-24 resize-none text-sm"
              />
              <Separator />
              <div className="flex flex-wrap gap-1.5">
                {hand.tags.map((t) => (
                  <Badge key={t} variant="secondary" className="text-[10px] font-normal">
                    {t}
                  </Badge>
                ))}
                {hand.tags.length === 0 && (
                  <span className="text-xs text-muted-foreground">Sem tags</span>
                )}
              </div>
              <Button
                size="sm"
                className="w-full"
                onClick={() => noteMutation.mutate()}
                disabled={noteMutation.isPending || noteSaved}
              >
                {noteSaved ? "Nota salva ✓" : "Salvar nota"}
              </Button>
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}
