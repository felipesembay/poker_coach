import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Search, Star } from "lucide-react";
import { useState } from "react";

import { PageHeader, Panel, StatCard } from "@/components/lab";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { favoritesApi } from "@/lib/api";

export const Route = createFileRoute("/favoritos")({
  head: () => ({
    meta: [
      { title: "Favoritos — PokerLab" },
      {
        name: "description",
        content: "Mãos, estudos e drills marcados para revisão futura em um só lugar.",
      },
      { property: "og:title", content: "Favoritos — PokerLab" },
      { property: "og:description", content: "Sua coleção pessoal de spots e lições de MTT." },
    ],
  }),
  component: FavoritesPage,
});

function FavoritesPage() {
  const { data: favorites = [] } = useQuery({
    queryKey: ["favorites"],
    queryFn: favoritesApi.list,
  });
  const [tab, setTab] = useState("Todos");

  const filtered = tab === "Todos" ? favorites : favorites.filter((f) => f.type === tab);

  return (
    <div className="space-y-5">
      <PageHeader
        title="Favoritos"
        description={`${favorites.length} item${favorites.length !== 1 ? "s" : ""} salvos`}
        actions={
          <Button variant="outline" size="sm">
            Criar coleção
          </Button>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard
          label="Mãos salvas"
          value={String(favorites.filter((f) => f.type === "Mão").length)}
          hint="Para revisão"
        />
        <StatCard
          label="Estudos salvos"
          value={String(favorites.filter((f) => f.type === "Estudo").length)}
          hint="Em progresso"
        />
        <StatCard
          label="Drills salvos"
          value={String(favorites.filter((f) => f.type === "Drill").length)}
          tone="profit"
        />
        <StatCard label="Total" value={String(favorites.length)} hint="Todos os tipos" />
      </div>

      <Panel
        title="Coleção"
        subtitle="Filtre por tipo de conteúdo"
        actions={
          <div className="relative w-52">
            <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input placeholder="Buscar favorito…" className="h-8 pl-8 text-xs" />
          </div>
        }
      >
        <div className="border-b border-border px-4 py-3">
          <Tabs value={tab} onValueChange={setTab}>
            <TabsList className="h-8">
              {["Todos", "Mão", "Estudo", "Drill"].map((t) => (
                <TabsTrigger key={t} value={t} className="text-xs">
                  {t}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        </div>

        <div className="grid gap-3 p-4 sm:grid-cols-2 xl:grid-cols-3">
          {filtered.map((f) => (
            <article
              key={`${f.site}-${f.hand_id}`}
              className="fade-up rounded-lg border border-border bg-elevated/40 p-4 transition-colors hover:border-primary/40"
            >
              <div className="flex items-start justify-between gap-2">
                <p className="text-sm font-semibold leading-snug">{f.title}</p>
                <Star className="size-4 shrink-0 text-primary" />
              </div>
              <p className="num mt-2 text-xs text-muted-foreground">{f.meta}</p>
              <div className="mt-3 flex items-center justify-between gap-2">
                <div className="flex flex-wrap gap-1">
                  {f.tags.slice(0, 2).map((t) => (
                    <Badge key={t} variant="outline" className="text-[10px] font-normal">
                      {t}
                    </Badge>
                  ))}
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                    {f.type}
                  </span>
                  <Button variant="outline" size="sm" asChild className="h-7 text-xs">
                    <Link to="/replayer" search={{ site: f.site, handId: f.hand_id }}>
                      Revisar
                    </Link>
                  </Button>
                </div>
              </div>
            </article>
          ))}
          {filtered.length === 0 && (
            <p className="col-span-full py-10 text-center text-sm text-muted-foreground">
              Nenhum favorito encontrado.
            </p>
          )}
        </div>
      </Panel>
    </div>
  );
}
