import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Check, X } from "lucide-react";
import { useState } from "react";

import { PageHeader, Panel, StatCard } from "@/components/lab";
import { PokerTable, type TableSeat } from "@/components/poker-table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { trainerApi, type TrainerAnswer, type TrainerMode } from "@/lib/api";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/push-fold/treinar")({
  head: () => ({
    meta: [
      { title: "Treinador Push/Fold — PokerLab" },
      {
        name: "description",
        content:
          "Drills de push/fold com feedback imediato: sua resposta, resposta correta, EV e explicação.",
      },
      { property: "og:title", content: "Treinador Push/Fold — PokerLab" },
      {
        property: "og:description",
        content: "Responda spots reais e receba explicação técnica instantânea.",
      },
    ],
  }),
  component: Trainer,
});

const OPEN_ACTIONS = ["Fold", "All-in"] as const;
const FACING_SHOVE_ACTIONS = ["Fold", "Call"] as const;
type Decision = "Fold" | "All-in" | "Call";

const MODES: { key: TrainerMode; label: string; hint: string }[] = [
  { key: "open", label: "Abertura", hint: "você age primeiro" },
  { key: "facing_shove", label: "All-in antes de você", hint: "vilão já deu shove" },
];

// "Fase do torneio" é uma aproximação por profundidade de stack — a
// hand history não diz quantos jogadores restam no torneio nem a
// estrutura de blinds real, só o stack efetivo na hora da mão. Não é
// detecção de fase de verdade (isso precisaria do campo inteiro, como
// no ICM — ver poker_coach/icm.py).
const STAGE_PRESETS = [
  { key: "inicio", label: "Início", hint: "25–50 BB", bb_min: 25, bb_max: 50 },
  { key: "meio", label: "Meio", hint: "15–25 BB", bb_min: 15, bb_max: 25 },
  { key: "bolha", label: "Bolha", hint: "10–18 BB", bb_min: 10, bb_max: 18 },
  { key: "final", label: "Mesa final", hint: "5–12 BB", bb_min: 5, bb_max: 12 },
] as const;

const PLAYER_COUNTS = ["Qualquer", "2", "3", "4", "5", "6", "7", "8", "9"];

function Trainer() {
  const queryClient = useQueryClient();
  const [refetchKey, setRefetchKey] = useState(0);
  const [mode, setMode] = useState<TrainerMode>("open");
  const [stage, setStage] = useState<(typeof STAGE_PRESETS)[number]["key"]>("meio");
  const [playerCount, setPlayerCount] = useState("Qualquer");
  const [userDecision, setUserDecision] = useState<Decision | null>(null);
  const [feedback, setFeedback] = useState<TrainerAnswer | null>(null);

  const activeStage = STAGE_PRESETS.find((s) => s.key === stage)!;
  const nPlayers = playerCount === "Qualquer" ? undefined : Number(playerCount);

  const questionQ = useQuery({
    queryKey: ["trainer-next", mode, refetchKey, activeStage.bb_min, activeStage.bb_max, nPlayers],
    queryFn: () =>
      trainerApi.next({
        mode,
        bb_min: activeStage.bb_min,
        bb_max: activeStage.bb_max,
        ...(nPlayers ? { n_players: nPlayers } : {}),
      }),
    staleTime: Infinity,
  });

  const statsQ = useQuery({
    queryKey: ["trainer-stats"],
    queryFn: trainerApi.stats,
  });

  const answerMutation = useMutation({
    mutationFn: (decision: Decision) => {
      const q = questionQ.data!;
      return trainerApi.answer(q.site, q.hand_id, q.mode, decision);
    },
    onSuccess: (data, decision) => {
      setFeedback(data);
      setUserDecision(decision);
      queryClient.invalidateQueries({ queryKey: ["trainer-stats"] });
    },
  });

  const submit = (a: Decision) => {
    if (feedback || answerMutation.isPending || !questionQ.data) return;
    answerMutation.mutate(a);
  };

  const next = () => {
    setFeedback(null);
    setUserDecision(null);
    setRefetchKey((k) => k + 1);
  };

  const changeFilters = (fn: () => void) => {
    fn();
    setFeedback(null);
    setUserDecision(null);
    setRefetchKey((k) => k + 1);
  };

  const stats = statsQ.data;
  const total = stats?.total ?? 0;
  const hits = stats?.correct ?? 0;
  const misses = total - hits;
  const accuracy = stats?.pct != null ? Math.round(stats.pct) : 0;

  const q = questionQ.data;
  const heroCards = q ? q.hero_cards.split(" ") : [];
  const answered = feedback !== null;
  const isCorrect = feedback?.correct ?? false;
  const nashDecision = feedback?.nash_decision ?? null;
  const actions: readonly Decision[] =
    q?.mode === "facing_shove" ? FACING_SHOVE_ACTIONS : OPEN_ACTIONS;

  const tableSeats: TableSeat[] = (q?.seats ?? []).map((s) => {
    const isShover = q?.mode === "facing_shove" && s.position === q.shover_position;
    return {
      key: s.position,
      position: s.position,
      label: s.is_hero ? "Você" : s.position,
      stack: s.stack,
      isHero: s.is_hero,
      cards: s.is_hero ? heroCards : null,
      actionText: isShover ? "All-in" : null,
      actionTone: isShover ? "allin" : "normal",
    };
  });

  return (
    <div className="space-y-5">
      <PageHeader
        title="Treinador Push/Fold"
        description="Spots reais das suas sessões · feedback imediato"
        actions={
          <Button variant="outline" size="sm" asChild>
            <Link to="/push-fold">
              <ArrowLeft className="mr-1.5 size-3.5" /> Voltar
            </Link>
          </Button>
        }
      />

      <Panel
        title="Cenário"
        subtitle="Fase do torneio é uma aproximação por profundidade de stack, não detecção real"
      >
        <div className="flex flex-wrap items-center gap-3 border-b border-border p-4">
          <div className="flex flex-wrap gap-1.5">
            {MODES.map((m) => (
              <Button
                key={m.key}
                size="sm"
                variant={mode === m.key ? "default" : "outline"}
                className="h-8 text-xs"
                onClick={() => changeFilters(() => setMode(m.key))}
              >
                {m.label}
                <span className="ml-1.5 text-[10px] opacity-70">{m.hint}</span>
              </Button>
            ))}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3 p-4">
          <div className="flex flex-wrap gap-1.5">
            {STAGE_PRESETS.map((s) => (
              <Button
                key={s.key}
                size="sm"
                variant={stage === s.key ? "default" : "outline"}
                className="h-8 text-xs"
                onClick={() => changeFilters(() => setStage(s.key))}
              >
                {s.label}
                <span className="num ml-1.5 text-[10px] opacity-70">{s.hint}</span>
              </Button>
            ))}
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">Jogadores na mesa</span>
            <Select
              value={playerCount}
              onValueChange={(v) => changeFilters(() => setPlayerCount(v))}
            >
              <SelectTrigger className="h-8 w-[110px] text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PLAYER_COUNTS.map((p) => (
                  <SelectItem key={p} value={p} className="text-xs">
                    {p}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      </Panel>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard
          label="Precisão acumulada"
          value={`${accuracy}%`}
          hint={`${total} spots`}
          tone="neutral"
        />
        <StatCard label="Acertos" value={String(hits)} tone="profit" />
        <StatCard label="Erros" value={String(misses)} tone="loss" />
        <StatCard
          label="Sessão"
          value={total > 0 ? `${total} spots` : "—"}
          hint="No banco de dados"
        />
      </div>

      {total > 0 && <Progress value={accuracy} className="h-1.5" />}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <Panel
          title="Situação"
          subtitle={
            q
              ? `Stack efetivo: ${q.effective_bb} BB · Pot: ${q.pot_bb} BB · ${q.n_players} jogadores`
              : questionQ.isLoading
                ? "Carregando…"
                : "Erro ao carregar"
          }
        >
          {questionQ.isLoading ? (
            <div className="p-10 text-center text-sm text-muted-foreground">Carregando spot…</div>
          ) : questionQ.isError ? (
            <div className="p-10 text-center text-sm text-loss">
              Nenhum spot encontrado com esses filtros.{" "}
              <Button size="sm" variant="outline" onClick={() => setRefetchKey((k) => k + 1)}>
                Tentar novamente
              </Button>
            </div>
          ) : q ? (
            <div className="space-y-4 p-4">
              <PokerTable seats={tableSeats} cardSize="2xl" seatCardSize="xl" />

              <div className="grid-lines flex flex-col items-center justify-center gap-3 rounded-lg border border-felt-edge bg-felt/50 py-6">
                <p className="max-w-md px-6 text-center text-sm text-muted-foreground">
                  {q.context}
                </p>
              </div>

              <div>
                <p className="text-sm font-semibold">Qual seria sua ação?</p>
                <div className="mt-3 grid gap-2 sm:grid-cols-2">
                  {actions.map((a) => {
                    const isAnswer = userDecision === a;
                    const isNash = nashDecision === a;
                    return (
                      <Button
                        key={a}
                        variant={answered && isNash ? "default" : "outline"}
                        disabled={answerMutation.isPending}
                        className={cn(
                          "h-11 justify-center text-sm font-semibold",
                          answered &&
                            isNash &&
                            "border-profit bg-profit/15 text-profit hover:bg-profit/20",
                          answered && isAnswer && !isNash && "border-loss bg-loss/15 text-loss",
                          answered && !isAnswer && !isNash && "opacity-45",
                        )}
                        onClick={() => submit(a)}
                      >
                        {answered && isNash ? <Check className="mr-1.5 size-4" /> : null}
                        {answered && isAnswer && !isNash ? <X className="mr-1.5 size-4" /> : null}
                        {a}
                      </Button>
                    );
                  })}
                </div>
              </div>
            </div>
          ) : null}
        </Panel>

        <Panel
          title="Feedback"
          subtitle={answered ? "Análise do spot" : "Responda para ver a análise"}
        >
          {answered && feedback ? (
            <div className="space-y-4 p-4 fade-up">
              <div className="grid gap-2">
                <div className="flex items-center justify-between rounded-md border border-border bg-elevated/50 px-3 py-2">
                  <span className="text-xs text-muted-foreground">Sua resposta</span>
                  <span
                    className={cn(
                      "num text-sm font-semibold",
                      isCorrect ? "text-profit" : "text-loss",
                    )}
                  >
                    {userDecision}
                  </span>
                </div>
                <div className="flex items-center justify-between rounded-md border border-border bg-elevated/50 px-3 py-2">
                  <span className="text-xs text-muted-foreground">Decisão Nash</span>
                  <span className="num text-sm font-semibold text-profit">
                    {feedback.nash_decision}
                  </span>
                </div>
                <div className="flex items-center justify-between rounded-md border border-border bg-elevated/50 px-3 py-2">
                  <span className="text-xs text-muted-foreground">
                    {q?.mode === "facing_shove" ? "EV do call" : "EV do shove"}
                  </span>
                  <span className="num text-sm font-semibold">{feedback.ev_bb.toFixed(2)} BB</span>
                </div>
                {feedback.ev_lost_bb > 0 && (
                  <div className="flex items-center justify-between rounded-md border border-border bg-elevated/50 px-3 py-2">
                    <span className="text-xs text-muted-foreground">EV perdido</span>
                    <span className="num text-sm font-semibold text-loss">
                      −{feedback.ev_lost_bb.toFixed(2)} BB
                    </span>
                  </div>
                )}
              </div>

              <Badge variant="outline" className={isCorrect ? "text-profit" : "text-loss"}>
                {isCorrect ? "Decisão ótima" : "Decisão sub-ótima"}
              </Badge>

              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">
                  Explicação
                </p>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                  {feedback.explanation}
                </p>
              </div>

              <Button className="w-full" onClick={next}>
                Próximo spot
              </Button>
            </div>
          ) : (
            <div className="p-8 text-center text-sm text-muted-foreground">
              Escolha {actions.join(" ou ")} para revelar a resposta correta, o EV e a explicação
              técnica do spot.
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}
