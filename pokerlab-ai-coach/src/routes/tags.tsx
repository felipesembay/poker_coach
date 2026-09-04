import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Plus, Search } from "lucide-react";

import { PageHeader, Panel, StatCard } from "@/components/lab";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { tagsApi } from "@/lib/api";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/tags")({
  head: () => ({
    meta: [
      { title: "Tags — PokerLab" },
      {
        name: "description",
        content: "Organize mãos e estudos por tags como push/fold, ICM, bluff, cooler e hero call.",
      },
      { property: "og:title", content: "Tags — PokerLab" },
      {
        property: "og:description",
        content: "Sistema de marcação para revisão estruturada de mãos.",
      },
    ],
  }),
  component: TagsPage,
});

function TagsPage() {
  const { data: tags = [] } = useQuery({ queryKey: ["tags"], queryFn: tagsApi.list });
  const max = Math.max(...tags.map((t) => t.count), 1);

  return (
    <div className="space-y-5">
      <PageHeader
        title="Tags"
        description="9 tags ativas · 526 mãos marcadas"
        actions={
          <Button size="sm">
            <Plus className="mr-1.5 size-3.5" /> Nova tag
          </Button>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="Tags ativas" value={String(tags.length)} hint="Total de categorias" />
        <StatCard
          label="Mãos marcadas"
          value={String(tags.reduce((s, t) => s + t.count, 0))}
          tone="neutral"
        />
        <StatCard
          label="Tag mais usada"
          value={tags.length ? tags.reduce((a, b) => (a.count > b.count ? a : b)).name : "—"}
          hint={tags.length ? `${Math.max(...tags.map((t) => t.count))} mãos` : ""}
        />
        <StatCard
          label="Tags de erro"
          value={String(tags.filter((t) => t.color === "loss").reduce((s, t) => s + t.count, 0))}
          delta={
            tags
              .filter((t) => t.color === "loss")
              .map((t) => t.name)
              .join(" + ") || "—"
          }
          tone="loss"
        />
      </div>

      <Panel
        title="Distribuição"
        subtitle="Volume de mãos por tag"
        actions={
          <div className="relative w-52">
            <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input placeholder="Buscar tag…" className="h-8 pl-8 text-xs" />
          </div>
        }
      >
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Tag</TableHead>
                <TableHead className="w-1/2">Volume</TableHead>
                <TableHead className="text-right">Mãos</TableHead>
                <TableHead className="text-right">Ação</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {tags.map((t) => (
                <TableRow key={t.name}>
                  <TableCell className="num text-sm">#{t.name}</TableCell>
                  <TableCell>
                    <div className="h-2 overflow-hidden rounded-full bg-elevated">
                      <div
                        className={cn(
                          "h-full rounded-full",
                          t.color === "profit"
                            ? "bg-profit"
                            : t.color === "loss"
                              ? "bg-loss"
                              : "bg-primary",
                        )}
                        style={{ width: `${(t.count / max) * 100}%` }}
                      />
                    </div>
                  </TableCell>
                  <TableCell className="num text-right text-xs">{t.count}</TableCell>
                  <TableCell className="text-right">
                    <Button variant="outline" size="sm">
                      Ver mãos
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </Panel>
    </div>
  );
}
