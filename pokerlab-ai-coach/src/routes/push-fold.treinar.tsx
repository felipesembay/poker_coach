import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery, useQueries, useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Check, RotateCw, X } from "lucide-react";
import { useState } from "react";

import { Hole, PageHeader, Panel, StatCard } from "@/components/lab";
import { PokerTable, type TableSeat } from "@/components/poker-table";
import { RangeGridPanel } from "@/components/range-grid";
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
import { trainerApi, type TrainerAnswer, type TrainerMode, type TrainerQuestion } from "@/lib/api";
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
type Answered = { decision: Decision; feedback: TrainerAnswer };

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

// Quantos spots simultâneos treinar — "1" é a visão rica de sempre (mesa +
// grid de range); "4" troca por um lote compacto de mãos reais diferentes,
// cada uma respondida na hora (estilo drill de quiz em série).
const COUNTS = [1, 4] as const;

function ScenarioCard({
  index,
  q,
  isLoading,
  isError,
  answered,
  pending,
  active,
  onAnswer,
  onSelect,
}: {
  index: number;
  q: TrainerQuestion | undefined;
  isLoading: boolean;
  isError: boolean;
  answered: Answered | null;
  pending: boolean;
  active: boolean;
  onAnswer: (d: Decision) => void;
  onSelect: () => void;
}) {
  const heroCards = q ? q.hero_cards.split(" ") : [];
  const actions: readonly Decision[] =
    q?.mode === "facing_shove" ? FACING_SHOVE_ACTIONS : OPEN_ACTIONS;
  const isCorrect = answered?.feedback.correct ?? false;
  const nashDecision = answered?.feedback.nash_decision ?? null;

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(e) => e.key === "Enter" && onSelect()}
      className={cn(
        "cursor-pointer rounded-lg border p-3 transition-colors",
        active && "ring-2 ring-primary/70",
        answered
          ? isCorrect
            ? "border-profit/40 bg-profit/5"
            : "border-loss/40 bg-loss/5"
          : "border-border bg-elevated/40",
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-semibold text-muted-foreground">Cenário {index + 1}</span>
        {q && (
          <span className="num text-[11px] text-muted-foreground">
            #{q.hand_id.slice(-6)} · {q.position} · {q.effective_bb} BB
          </span>
        )}
      </div>

      {isLoading ? (
        <div className="py-8 text-center text-xs text-muted-foreground">Carregando…</div>
      ) : isError || !q ? (
        <div className="py-8 text-center text-xs text-loss">Nenhum spot encontrado.</div>
      ) : (
        <>
          <p className="mt-1.5 truncate text-xs text-muted-foreground">
            {q.mode === "facing_shove"
              ? `${q.shover_position} deu shove — vilão all-in`
              : "Fold to you — você é o primeiro a agir"}
          </p>
          <div className="mt-2 flex items-center justify-between gap-2">
            <Hole cards={heroCards} size="md" />
            <span className="num text-[11px] text-muted-foreground">{q.n_players} jogadores</span>
          </div>

          <div className="mt-3 grid grid-cols-2 gap-1.5">
            {actions.map((a) => {
              const isAnswer = answered?.decision === a;
              const isNash = nashDecision === a;
              return (
                <Button
                  key={a}
                  size="sm"
                  variant={answered && isNash ? "default" : "outline"}
                  disabled={pending || !!answered}
                  className={cn(
                    "h-9 text-xs font-semibold",
                    answered &&
                      isNash &&
                      "border-profit bg-profit/15 text-profit hover:bg-profit/20",
                    answered && isAnswer && !isNash && "border-loss bg-loss/15 text-loss",
                    answered && !isAnswer && !isNash && "opacity-45",
                  )}
                  onClick={(e) => {
                    e.stopPropagation();
                    onAnswer(a);
                  }}
                >
                  {answered && isNash ? <Check className="mr-1 size-3.5" /> : null}
                  {answered && isAnswer && !isNash ? <X className="mr-1 size-3.5" /> : null}
                  {a}
                </Button>
              );
            })}
          </div>

          {answered && (
            <p
              className={cn(
                "num mt-2 text-center text-[11px]",
                isCorrect ? "text-profit" : "text-loss",
              )}
            >
              {isCorrect
                ? `Correto · ${answered.feedback.ev_bb >= 0 ? "+" : ""}${answered.feedback.ev_bb.toFixed(2)} BB`
                : `Nash: ${nashDecision} · −${answered.feedback.ev_lost_bb.toFixed(2)} BB perdido`}
            </p>
          )}
        </>
      )}
    </div>
  );
}

function Trainer() {
  const queryClient = useQueryClient();
  const [batchKey, setBatchKey] = useState(0);
  const [mode, setMode] = useState<TrainerMode>("open");
  const [stage, setStage] = useState<(typeof STAGE_PRESETS)[number]["key"]>("meio");
  const [playerCount, setPlayerCount] = useState("Qualquer");
  const [count, setCount] = useState<(typeof COUNTS)[number]>(1);
  const [answers, setAnswers] = useState<Record<number, Answered>>({});
  // Qual dos N cenários está em foco na mesa (modo 4 cenários) — clicar
  // num card troca o que a mesa mostra, sem precisar de mesa por card.
  const [activeSlot, setActiveSlot] = useState(0);

  const activeStage = STAGE_PRESETS.find((s) => s.key === stage)!;
  const nPlayers = playerCount === "Qualquer" ? undefined : Number(playerCount);

  // 1 ou 4 spots buscados em paralelo, cada um independente (site+hand_id
  // próprios) — o mesmo endpoint de sempre, só chamado N vezes por lote.
  const questionQueries = useQueries({
    queries: Array.from({ length: count }, (_, i) => ({
      queryKey: [
        "trainer-next",
        mode,
        batchKey,
        i,
        activeStage.bb_min,
        activeStage.bb_max,
        nPlayers,
      ],
      queryFn: () =>
        trainerApi.next({
          mode,
          bb_min: activeStage.bb_min,
          bb_max: activeStage.bb_max,
          ...(nPlayers ? { n_players: nPlayers } : {}),
        }),
      staleTime: Infinity,
    })),
  });

  const statsQ = useQuery({
    queryKey: ["trainer-stats"],
    queryFn: trainerApi.stats,
  });

  const answerMutation = useMutation({
    mutationFn: async ({ slot, decision }: { slot: number; decision: Decision }) => {
      const q = questionQueries[slot]?.data;
      if (!q) throw new Error("Spot não carregado.");
      const feedback = await trainerApi.answer(q.site, q.hand_id, q.mode, decision);
      return { slot, decision, feedback };
    },
    onSuccess: ({ slot, decision, feedback }) => {
      setAnswers((a) => ({ ...a, [slot]: { decision, feedback } }));
      queryClient.invalidateQueries({ queryKey: ["trainer-stats"] });
    },
  });

  const submit = (slot: number, decision: Decision) => {
    if (answers[slot] || answerMutation.isPending) return;
    setActiveSlot(slot);
    answerMutation.mutate({ slot, decision });
  };

  const newBatch = () => {
    setAnswers({});
    setActiveSlot(0);
    setBatchKey((k) => k + 1);
  };

  const changeFilters = (fn: () => void) => {
    fn();
    setAnswers({});
    setActiveSlot(0);
    setBatchKey((k) => k + 1);
  };

  const stats = statsQ.data;
  const total = stats?.total ?? 0;
  const hits = stats?.correct ?? 0;
  const misses = total - hits;
  const accuracy = stats?.pct != null ? Math.round(stats.pct) : 0;

  const allAnswered = Array.from({ length: count }).every((_, i) => answers[i]);

  // ---- Mesa — sempre reflete o cenário "em foco" (activeSlot); no modo
  // 1 mão isso é sempre o slot 0, no modo 4 cenários é o card clicado. ----
  const q0 = questionQueries[activeSlot]?.data;
  const feedback0 = answers[activeSlot]?.feedback ?? null;
  const userDecision0 = answers[activeSlot]?.decision ?? null;
  const answered0 = !!feedback0;
  const heroCards0 = q0 ? q0.hero_cards.split(" ") : [];
  const actions0: readonly Decision[] =
    q0?.mode === "facing_shove" ? FACING_SHOVE_ACTIONS : OPEN_ACTIONS;

  const tableSeats0: TableSeat[] = (q0?.seats ?? []).map((s) => {
    const isShover = q0?.mode === "facing_shove" && s.position === q0.shover_position;
    return {
      key: s.position,
      position: s.position,
      label: s.is_hero ? "Você" : s.position,
      stack: s.stack,
      isHero: s.is_hero,
      cards: s.is_hero ? heroCards0 : null,
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
          <div className="ml-auto flex flex-wrap items-center gap-1.5">
            <span className="text-xs text-muted-foreground">Treinar</span>
            {COUNTS.map((c) => (
              <Button
                key={c}
                size="sm"
                variant={count === c ? "default" : "outline"}
                className="h-8 text-xs"
                onClick={() => changeFilters(() => setCount(c))}
              >
                {c === 1 ? "1 mão" : `${c} cenários`}
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
          <Button variant="outline" size="sm" className="ml-auto h-8 text-xs" onClick={newBatch}>
            <RotateCw className="mr-1.5 size-3.5" />
            {count === 1 ? "Próximo spot" : "Novo lote"}
          </Button>
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

      {count === 1 ? (
        <>
          {/* Mesa (menor, largura travada) + mapa de mãos e feedback
              empilhados ao lado — cabem juntos na mesma coluna, sem
              precisar de um card cheio embaixo disputando espaço com a
              mesa. */}
          <div className="flex flex-wrap items-start gap-4">
            <Panel
              className="w-full min-w-0 max-w-[680px]"
              title="Situação"
              subtitle={
                q0
                  ? `Stack efetivo: ${q0.effective_bb} BB · Pot: ${q0.pot_bb} BB · ${q0.n_players} jogadores`
                  : questionQueries[activeSlot]?.isLoading
                    ? "Carregando…"
                    : "Erro ao carregar"
              }
            >
              {questionQueries[activeSlot]?.isLoading ? (
                <div className="p-10 text-center text-sm text-muted-foreground">
                  Carregando spot…
                </div>
              ) : questionQueries[activeSlot]?.isError ? (
                <div className="p-10 text-center text-sm text-loss">
                  Nenhum spot encontrado com esses filtros.{" "}
                  <Button size="sm" variant="outline" onClick={newBatch}>
                    Tentar novamente
                  </Button>
                </div>
              ) : q0 ? (
                <div className="space-y-4 p-4">
                  <PokerTable seats={tableSeats0} cardSize="xl" seatCardSize="lg" bb={q0.bb} />

                  <div className="grid-lines flex flex-col items-center justify-center gap-3 rounded-lg border border-felt-edge bg-felt/50 py-6">
                    <p className="max-w-md px-6 text-center text-sm text-muted-foreground">
                      {q0.context}
                    </p>
                  </div>

                  <div>
                    <p className="text-sm font-semibold">Qual seria sua ação?</p>
                    <div className="mt-3 grid gap-2 sm:grid-cols-2">
                      {actions0.map((a) => {
                        const isAnswer = userDecision0 === a;
                        const isNash = feedback0?.nash_decision === a;
                        return (
                          <Button
                            key={a}
                            variant={answered0 && isNash ? "default" : "outline"}
                            disabled={answerMutation.isPending}
                            className={cn(
                              "h-11 justify-center text-sm font-semibold",
                              answered0 &&
                                isNash &&
                                "border-profit bg-profit/15 text-profit hover:bg-profit/20",
                              answered0 &&
                                isAnswer &&
                                !isNash &&
                                "border-loss bg-loss/15 text-loss",
                              answered0 && !isAnswer && !isNash && "opacity-45",
                            )}
                            onClick={() => submit(activeSlot, a)}
                          >
                            {answered0 && isNash ? <Check className="mr-1.5 size-4" /> : null}
                            {answered0 && isAnswer && !isNash ? (
                              <X className="mr-1.5 size-4" />
                            ) : null}
                            {a}
                          </Button>
                        );
                      })}
                    </div>
                  </div>
                </div>
              ) : null}
            </Panel>

            {/* Mapa de mãos + Feedback empilhados na mesma coluna lateral —
                o mapa só existe depois de responder (precisa saber o que
                comparar contra), o feedback idem. */}
            <div className="min-w-0 flex-1 space-y-4">
              {answered0 && q0 ? (
                <RangeGridPanel
                  effectiveBb={q0.effective_bb}
                  potBb={q0.pot_bb}
                  heroCards={heroCards0}
                  kind={q0.mode === "facing_shove" ? "call" : "push"}
                  cellPx={26}
                />
              ) : (
                <Panel title="Mapa de mãos" subtitle="Aparece depois de responder">
                  <div className="flex h-40 items-center justify-center p-4 text-center text-sm text-muted-foreground">
                    Escolha {actions0.join(" ou ")} pra ver o mapa 13×13 comparado com o Nash desse
                    stack/pot.
                  </div>
                </Panel>
              )}

              <Panel
                title="Feedback"
                subtitle={answered0 ? "Análise do spot" : "Responda para ver a análise"}
              >
                {answered0 && feedback0 ? (
                  <div className="space-y-3 p-4 fade-up">
                    <div className="grid gap-2">
                      <div className="flex items-center justify-between rounded-md border border-border bg-elevated/50 px-3 py-2">
                        <span className="text-xs text-muted-foreground">Sua resposta</span>
                        <span
                          className={cn(
                            "num text-sm font-semibold",
                            feedback0.correct ? "text-profit" : "text-loss",
                          )}
                        >
                          {userDecision0}
                        </span>
                      </div>
                      <div className="flex items-center justify-between rounded-md border border-border bg-elevated/50 px-3 py-2">
                        <span className="text-xs text-muted-foreground">Decisão Nash</span>
                        <span className="num text-sm font-semibold text-profit">
                          {feedback0.nash_decision}
                        </span>
                      </div>
                      <div className="flex items-center justify-between rounded-md border border-border bg-elevated/50 px-3 py-2">
                        <span className="text-xs text-muted-foreground">
                          {q0?.mode === "facing_shove" ? "EV do call" : "EV do shove"}
                        </span>
                        <span className="num text-sm font-semibold">
                          {feedback0.ev_bb.toFixed(2)} BB
                        </span>
                      </div>
                      {feedback0.ev_lost_bb > 0 && (
                        <div className="flex items-center justify-between rounded-md border border-border bg-elevated/50 px-3 py-2">
                          <span className="text-xs text-muted-foreground">EV perdido</span>
                          <span className="num text-sm font-semibold text-loss">
                            −{feedback0.ev_lost_bb.toFixed(2)} BB
                          </span>
                        </div>
                      )}
                    </div>

                    <Badge
                      variant="outline"
                      className={feedback0.correct ? "text-profit" : "text-loss"}
                    >
                      {feedback0.correct ? "Decisão ótima" : "Decisão sub-ótima"}
                    </Badge>

                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">
                        Explicação
                      </p>
                      <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                        {feedback0.explanation}
                      </p>
                    </div>

                    <Button className="w-full" onClick={newBatch}>
                      Próximo spot
                    </Button>
                  </div>
                ) : (
                  <div className="p-8 text-center text-sm text-muted-foreground">
                    Escolha {actions0.join(" ou ")} para revelar a resposta correta, o EV e a
                    explicação técnica do spot.
                  </div>
                )}
              </Panel>
            </div>
          </div>
        </>
      ) : (
        <>
          {/* Mesa — sempre mostra o cenário em foco (clique num card
              abaixo pra trocar); os 4 cenários ficam logo abaixo dela. */}
          <Panel
            title={`Mesa · Cenário ${activeSlot + 1}`}
            subtitle={
              q0
                ? `${q0.position} · ${q0.effective_bb} BB efetivo · ${q0.n_players} jogadores`
                : "Carregando…"
            }
          >
            {q0 ? (
              <PokerTable seats={tableSeats0} cardSize="lg" seatCardSize="md" bb={q0.bb} />
            ) : (
              <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">
                Carregando…
              </div>
            )}
          </Panel>

          <Panel
            title="Cenários"
            subtitle={`${count} mãos reais diferentes · clique num card pra ver na mesa acima · responda cada uma`}
            actions={
              allAnswered ? (
                <Button size="sm" onClick={newBatch}>
                  <RotateCw className="mr-1.5 size-3.5" /> Novo lote
                </Button>
              ) : null
            }
          >
            <div className="grid gap-3 p-4 sm:grid-cols-2">
              {Array.from({ length: count }).map((_, i) => (
                <ScenarioCard
                  key={`${batchKey}-${i}`}
                  index={i}
                  q={questionQueries[i]?.data}
                  isLoading={!!questionQueries[i]?.isLoading}
                  isError={!!questionQueries[i]?.isError}
                  answered={answers[i] ?? null}
                  pending={answerMutation.isPending && answerMutation.variables?.slot === i}
                  active={activeSlot === i}
                  onAnswer={(d) => submit(i, d)}
                  onSelect={() => setActiveSlot(i)}
                />
              ))}
            </div>
          </Panel>

          {answered0 && q0 && (
            <RangeGridPanel
              effectiveBb={q0.effective_bb}
              potBb={q0.pot_bb}
              heroCards={heroCards0}
              kind={q0.mode === "facing_shove" ? "call" : "push"}
            />
          )}
        </>
      )}
    </div>
  );
}
