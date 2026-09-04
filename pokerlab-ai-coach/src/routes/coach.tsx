import { createFileRoute } from "@tanstack/react-router";
import { ArrowUp, Spade } from "lucide-react";
import { useState } from "react";

import { PageHeader, Panel } from "@/components/lab";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Textarea } from "@/components/ui/textarea";
import { coachMessages } from "@/lib/mock-data";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/coach")({
  head: () => ({
    meta: [
      { title: "Coach IA — PokerLab" },
      {
        name: "description",
        content:
          "Converse com o Coach IA sobre suas mãos: resumo de sessão, erros, acertos e plano de estudo.",
      },
      { property: "og:title", content: "Coach IA — PokerLab" },
      {
        property: "og:description",
        content: "Seu treinador pessoal de MTT explicando cada decisão com contexto técnico.",
      },
    ],
  }),
  component: CoachPage,
});

const suggestions = [
  "Analise minha sessão de hoje",
  "Onde perdi mais EV nesta semana?",
  "Monte um drill de push/fold de 12 a 18 BB",
  "Explique o bubble factor na minha última bolha",
];

function renderInline(text: string) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((chunk, i) =>
    chunk.startsWith("**") && chunk.endsWith("**") ? (
      <strong key={i} className="font-semibold text-foreground">
        {chunk.slice(2, -2)}
      </strong>
    ) : (
      <span key={i}>{chunk}</span>
    ),
  );
}

function CoachPage() {
  const [draft, setDraft] = useState("");

  return (
    <div className="space-y-5">
      <PageHeader
        title="Coach IA"
        description="Contexto ativo: 8 sessões · 8.923 mãos · 4 leaks detectados"
        actions={
          <Button variant="outline" size="sm">
            Nova conversa
          </Button>
        }
      />

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_300px]">
        <Panel className="flex min-h-[560px] flex-col">
          <ScrollArea className="flex-1">
            <div className="space-y-6 p-5">
              {coachMessages.map((m, i) => (
                <div
                  key={i}
                  className={cn(
                    "fade-up flex gap-3",
                    m.role === "user" ? "flex-row-reverse" : "flex-row",
                  )}
                >
                  <div
                    className={cn(
                      "grid size-8 shrink-0 place-items-center rounded-md border border-border",
                      m.role === "assistant" ? "bg-primary/12" : "bg-elevated",
                    )}
                  >
                    {m.role === "assistant" ? (
                      <Spade className="size-4 text-primary" />
                    ) : (
                      <span className="num text-[10px] font-bold">LV</span>
                    )}
                  </div>
                  <div className={cn("min-w-0 max-w-[76ch]", m.role === "user" && "text-right")}>
                    <div
                      className={cn(
                        "space-y-2 text-sm leading-relaxed",
                        m.role === "user" &&
                          "inline-block rounded-lg bg-primary px-3 py-2 text-left text-primary-foreground",
                      )}
                    >
                      {m.content.split("\n\n").map((p, j) => (
                        <p
                          key={j}
                          className={m.role === "assistant" ? "text-muted-foreground" : undefined}
                        >
                          {renderInline(p)}
                        </p>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </ScrollArea>

          <div className="border-t border-border p-3">
            <div className="mb-2 flex flex-wrap gap-1.5">
              {suggestions.map((s) => (
                <button
                  key={s}
                  onClick={() => setDraft(s)}
                  className="rounded-full border border-border px-2.5 py-1 text-[11px] text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
                >
                  {s}
                </button>
              ))}
            </div>
            <div className="rounded-lg border border-border bg-card p-2">
              <Textarea
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder="Pergunte sobre uma mão, um spot ou peça um plano de estudo…"
                className="min-h-16 resize-none border-0 bg-transparent p-1 text-sm shadow-none focus-visible:ring-0"
              />
              <div className="flex justify-end">
                <Button size="icon" className="size-8" aria-label="Enviar mensagem">
                  <ArrowUp className="size-4" />
                </Button>
              </div>
            </div>
          </div>
        </Panel>

        <div className="space-y-4">
          <Panel title="Resumo automático" subtitle="Sessão de 05/08">
            <div className="space-y-3 p-4 text-sm">
              <div>
                <p className="text-[10px] uppercase tracking-[0.14em] text-loss">Principal erro</p>
                <p className="mt-1 text-muted-foreground">
                  Fold excessivo entre 12 e 18 BB · 9 spots
                </p>
              </div>
              <div>
                <p className="text-[10px] uppercase tracking-[0.14em] text-profit">
                  Principal acerto
                </p>
                <p className="mt-1 text-muted-foreground">Steals do BTN · 42% de frequência</p>
              </div>
              <div>
                <p className="text-[10px] uppercase tracking-[0.14em] text-primary">
                  Objetivo para amanhã
                </p>
                <p className="mt-1 text-muted-foreground">Treinar Push/Fold por 15 minutos</p>
              </div>
            </div>
          </Panel>

          <Panel title="Contexto da análise">
            <div className="flex flex-wrap gap-1.5 p-4">
              {["8 sessões", "1.284 mãos", "push/fold", "icm", "bolha", "steal", "12–18 BB"].map(
                (t) => (
                  <Badge key={t} variant="outline" className="text-[10px] font-normal">
                    {t}
                  </Badge>
                ),
              )}
            </div>
          </Panel>

          <Panel title="Ações sugeridas">
            <div className="space-y-2 p-4">
              <Button variant="outline" size="sm" className="w-full justify-start">
                Criar drill de 20 spots
              </Button>
              <Button variant="outline" size="sm" className="w-full justify-start">
                Marcar 9 mãos para revisão
              </Button>
              <Button variant="outline" size="sm" className="w-full justify-start">
                Adicionar meta de precisão 92%
              </Button>
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}
