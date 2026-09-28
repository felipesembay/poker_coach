import { useQuery } from "@tanstack/react-query";
import { Check, RotateCw, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Hole } from "@/components/lab";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { icmApi, type IcmSpot } from "@/lib/api";
import { cn } from "@/lib/utils";

// Drill de ICM: usa os spots reais já calculados pelo motor
// (poker_coach/icm_analyze.py — abertura preflop, vilão = BB) e esconde a
// resposta até você decidir. Mesmo escopo e mesmas limitações da tabela
// "Spots de ICM": só vale pra torneios com premiação salva.

type Scope = { site: string; tournament_id: string; label: string };
type Decision = "push" | "fold";

function shuffle<T>(arr: T[]): T[] {
  const out = [...arr];
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [out[i], out[j]] = [out[j]!, out[i]!];
  }
  return out;
}

const fmt$ = (v: number) => `$${v.toFixed(2)}`;

export function IcmTrainerDialog({
  open,
  onOpenChange,
  tournament,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  // Torneio selecionado na tela (com premiação) — null = só "todos".
  tournament: Scope | null;
}) {
  const tKey = tournament ? `${tournament.site}::${tournament.tournament_id}` : "";
  const [onlyTournament, setOnlyTournament] = useState(!!tournament);
  // Ao abrir, começa pelo torneio selecionado (se houver).
  useEffect(() => {
    if (open) setOnlyTournament(!!tKey);
  }, [open, tKey]);

  const scoped = onlyTournament && tournament;
  const spotsQ = useQuery({
    queryKey: ["icm-trainer-spots", scoped ? tKey : "all"],
    queryFn: () =>
      icmApi.trainerSpots(
        scoped
          ? { site: tournament.site, tournament_id: tournament.tournament_id, confirmed: true }
          : { confirmed: true },
      ),
    enabled: open,
  });

  const [round, setRound] = useState(0);
  const deck = useMemo<IcmSpot[]>(
    () => shuffle(spotsQ.data ?? []),
    // `round` reembaralha no "Reiniciar".
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [spotsQ.data, round],
  );

  const [idx, setIdx] = useState(0);
  const [answer, setAnswer] = useState<Decision | null>(null);
  const [score, setScore] = useState({ right: 0, total: 0, evLost: 0 });

  const reset = () => {
    setIdx(0);
    setAnswer(null);
    setScore({ right: 0, total: 0, evLost: 0 });
  };
  // Troca de escopo/baralho novo = placar zerado.
  useEffect(reset, [deck]);

  const spot = deck[idx];
  const finished = deck.length > 0 && idx >= deck.length;

  const decide = (d: Decision) => {
    if (!spot || answer) return;
    setAnswer(d);
    const correct = d === spot.icm_decision;
    setScore((s) => ({
      right: s.right + (correct ? 1 : 0),
      total: s.total + 1,
      evLost: s.evLost + (correct ? 0 : Math.abs(spot.icm_ev_push - spot.icm_ev_fold)),
    }));
  };

  const next = () => {
    setAnswer(null);
    setIdx((i) => i + 1);
  };

  // Atalhos: F = fold, P/A = push, Enter/espaço = próximo.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      const k = e.key.toLowerCase();
      if (!answer && k === "f") decide("fold");
      else if (!answer && (k === "p" || k === "a")) decide("push");
      else if (answer && (k === "enter" || k === " ")) {
        e.preventDefault();
        next();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const correct = answer != null && spot != null && answer === spot.icm_decision;
  const accuracy = score.total ? Math.round((score.right / score.total) * 100) : null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Treinar ICM</DialogTitle>
          <DialogDescription>
            Spots reais de abertura (fold até você, vilão = BB). Decida push ou fold pelo ICM — a
            resposta usa a premiação que você cadastrou.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-wrap items-center gap-2">
          {tournament && (
            <Button
              size="sm"
              variant={onlyTournament ? "default" : "outline"}
              className="h-7 text-xs"
              onClick={() => setOnlyTournament(true)}
            >
              {tournament.label}
            </Button>
          )}
          <Button
            size="sm"
            variant={!onlyTournament || !tournament ? "default" : "outline"}
            className="h-7 text-xs"
            onClick={() => setOnlyTournament(false)}
          >
            Todos com premiação
          </Button>
          <span className="num ml-auto text-xs text-muted-foreground">
            {score.total > 0 && `${score.right}/${score.total} · ${accuracy}% · `}
            {deck.length > 0 && `${Math.min(idx + 1, deck.length)}/${deck.length}`}
          </span>
        </div>

        {spotsQ.isLoading ? (
          <p className="py-10 text-center text-sm text-muted-foreground">Carregando spots…</p>
        ) : spotsQ.isError ? (
          <p className="py-10 text-center text-sm text-loss">
            Erro ao carregar spots: {(spotsQ.error as Error).message}
          </p>
        ) : deck.length === 0 ? (
          <p className="py-10 text-center text-sm text-muted-foreground">
            Nenhum spot de ICM encontrado. Cadastre a premiação de um torneio (com mãos de abertura
            até 40 BB) pra gerar spots.
          </p>
        ) : finished ? (
          <div className="space-y-3 py-6 text-center">
            <p className="text-lg font-semibold">
              {score.right}/{score.total} corretas ({accuracy}%)
            </p>
            <p className="text-sm text-muted-foreground">
              $EV perdido nas erradas: {fmt$(score.evLost)}
            </p>
            <Button size="sm" onClick={() => setRound((r) => r + 1)}>
              <RotateCw className="mr-1.5 size-3.5" /> Treinar de novo
            </Button>
          </div>
        ) : spot ? (
          <div className="space-y-4">
            <div className="rounded-lg border border-border bg-elevated/40 p-4">
              <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <Badge variant="secondary" className="text-[10px] font-normal">
                  {spot.category}
                </Badge>
                <span className="truncate">
                  {spot.tournament_name ?? `${spot.site} #${spot.tournament_id}`}
                </span>
                <span className="num ml-auto">#{spot.hand_id.slice(-6)}</span>
              </div>
              <div className="mt-4 flex items-center justify-between gap-4">
                <Hole cards={spot.hero_cards.split(" ")} size="lg" />
                <div className="num space-y-0.5 text-right text-sm">
                  <p>
                    <span className="font-semibold">{spot.position}</span> · {spot.n_players}{" "}
                    jogadores
                  </p>
                  <p>{spot.effective_bb} BB efetivos</p>
                  <p className="text-xs text-muted-foreground">
                    Risk premium {spot.risk_premium_pct.toFixed(1)}% ({spot.risk})
                  </p>
                </div>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2">
              {(["fold", "push"] as const).map((d) => {
                const isIcm = answer != null && spot.icm_decision === d;
                const isWrongPick = answer === d && !correct;
                return (
                  <Button
                    key={d}
                    variant="outline"
                    disabled={answer != null}
                    onClick={() => decide(d)}
                    className={cn(
                      "h-11 disabled:opacity-100",
                      isIcm && "border-profit bg-profit/10 text-profit",
                      isWrongPick && "border-loss bg-loss/10 text-loss",
                    )}
                  >
                    {d === "fold" ? "Fold (F)" : "All-in (P)"}
                  </Button>
                );
              })}
            </div>

            {answer && (
              <div
                className={cn(
                  "space-y-1.5 rounded-lg border p-3 text-sm",
                  correct ? "border-profit/40 bg-profit/5" : "border-loss/40 bg-loss/5",
                )}
              >
                <p
                  className={cn(
                    "flex items-center gap-1.5 font-semibold",
                    correct ? "text-profit" : "text-loss",
                  )}
                >
                  {correct ? <Check className="size-4" /> : <X className="size-4" />}
                  {correct ? "Correto" : "Errado"} — ICM manda{" "}
                  {spot.icm_decision === "push" ? "all-in" : "fold"}
                </p>
                <p className="num text-xs">
                  $EV fold {fmt$(spot.icm_ev_fold)} · $EV push {fmt$(spot.icm_ev_push)} · diferença{" "}
                  {fmt$(Math.abs(spot.icm_ev_push - spot.icm_ev_fold))}
                </p>
                <p className="text-xs text-muted-foreground">
                  Na mão real você deu {spot.hero_decision === "push" ? "all-in" : "fold"}
                  {spot.hero_decision === spot.icm_decision
                    ? " (bateu com o ICM)."
                    : ` (custou ${fmt$(spot.icm_ev_lost)}).`}
                </p>
                <div className="flex justify-end pt-1">
                  <Button size="sm" className="h-8 text-xs" onClick={next}>
                    Próximo (Enter)
                  </Button>
                </div>
              </div>
            )}

            <div className="flex justify-between">
              <Button
                variant="ghost"
                size="sm"
                className="h-7 text-xs"
                onClick={() => setRound((r) => r + 1)}
              >
                <RotateCw className="mr-1 size-3" /> Reiniciar
              </Button>
              {!answer && (
                <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={next}>
                  Pular
                </Button>
              )}
            </div>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
