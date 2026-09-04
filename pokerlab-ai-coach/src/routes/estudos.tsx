import { createFileRoute } from "@tanstack/react-router";
import { Search } from "lucide-react";

import { PageHeader, Panel, StatCard } from "@/components/lab";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { studyCategories, studyItems } from "@/lib/mock-data";

export const Route = createFileRoute("/estudos")({
  head: () => ({
    meta: [
      { title: "Estudos — PokerLab" },
      {
        name: "description",
        content:
          "Biblioteca de estudos de MTT: push/fold, ICM, bluffs, hero calls, coolers e mais.",
      },
      { property: "og:title", content: "Estudos — PokerLab" },
      {
        property: "og:description",
        content: "Trilhas de estudo organizadas por conceito técnico.",
      },
    ],
  }),
  component: StudiesPage,
});

function StudiesPage() {
  return (
    <div className="space-y-5">
      <PageHeader
        title="Estudos"
        description="116 lições organizadas por conceito · 38% da biblioteca concluída"
        actions={<Button size="sm">Continuar de onde parei</Button>}
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="Lições concluídas" value="44" delta="+9 no mês" tone="profit" />
        <StatCard label="Tempo de estudo" value="12h 40m" delta="+3h 10m" tone="neutral" />
        <StatCard label="Sequência" value="6 dias" delta="Recorde: 11" tone="neutral" />
        <StatCard label="Leaks corrigidos" value="14" delta="+3" tone="profit" />
      </div>

      <Panel
        title="Categorias"
        subtitle="Escolha um bloco de conceitos"
        actions={
          <div className="relative w-52">
            <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input placeholder="Buscar estudo…" className="h-8 pl-8 text-xs" />
          </div>
        }
      >
        <div className="grid gap-3 p-4 sm:grid-cols-2 xl:grid-cols-4">
          {studyCategories.map((c) => (
            <button
              key={c.name}
              className="rounded-lg border border-border bg-elevated/40 p-4 text-left transition-colors hover:border-primary/40 hover:bg-accent/40"
            >
              <div className="flex items-center justify-between gap-2">
                <p className="truncate text-sm font-semibold">{c.name}</p>
                <Badge variant="secondary" className="num text-[10px]">
                  {c.count}
                </Badge>
              </div>
              <p className="mt-1.5 line-clamp-2 text-xs text-muted-foreground">{c.description}</p>
            </button>
          ))}
        </div>
      </Panel>

      <Panel title="Lições" subtitle="Ordenadas por progresso">
        <ul className="divide-y divide-border">
          {studyItems.map((s) => (
            <li
              key={s.title}
              className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-4 px-4 py-3 transition-colors hover:bg-accent/40"
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">{s.title}</p>
                <p className="num truncate text-xs text-muted-foreground">
                  {s.category} · {s.minutes} min
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-3">
                <Progress value={s.progress} className="h-1.5 w-24" />
                <span className="num w-10 text-right text-xs text-muted-foreground">
                  {s.progress}%
                </span>
                <Button variant="outline" size="sm">
                  {s.progress === 0 ? "Iniciar" : s.progress === 100 ? "Revisar" : "Continuar"}
                </Button>
              </div>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}
