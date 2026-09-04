import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Search, SlidersHorizontal } from "lucide-react";

import { Hole, Money, PageHeader, Panel, PlayingCard, StatCard } from "@/components/lab";
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
import { handsApi } from "@/lib/api";

export const Route = createFileRoute("/maos")({
  head: () => ({
    meta: [
      { title: "Hand History — PokerLab" },
      {
        name: "description",
        content:
          "Explore todas as mãos importadas com filtros de posição, stack, cartas, all-in e showdown.",
      },
      { property: "og:title", content: "Hand History — PokerLab" },
      {
        property: "og:description",
        content: "Tabela avançada de mãos com tags, resultado e revisão detalhada.",
      },
    ],
  }),
  component: HandsPage,
});

const POSITIONS = ["Todas", "UTG", "HJ", "CO", "BTN", "SB", "BB"];

function HandsPage() {
  const [position, setPosition] = useState("Todas");
  const [showdownOnly, setShowdownOnly] = useState("Todos");
  const [allInOnly, setAllInOnly] = useState("Todos");

  const { data: hands = [], isLoading } = useQuery({
    queryKey: ["hands", position, showdownOnly, allInOnly],
    queryFn: () =>
      handsApi.list({
        ...(position !== "Todas" ? { position } : {}),
        ...(showdownOnly === "Sim" ? { showdown_only: true } : {}),
        ...(allInOnly === "Sim" ? { all_in_only: true } : {}),
        limit: 200,
      }),
  });

  const allIns = hands.filter((h) => h.all_in).length;
  const showdowns = hands.filter((h) => h.showdown).length;

  return (
    <div className="space-y-5">
      <PageHeader
        title="Hand History"
        description={`${hands.length} mãos carregadas`}
        actions={
          <Button variant="outline" size="sm">
            <SlidersHorizontal className="mr-1.5 size-3.5" /> Filtro avançado
          </Button>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="Mãos" value={String(hands.length)} tone="neutral" />
        <StatCard label="All-ins" value={String(allIns)} tone="neutral" />
        <StatCard label="Showdowns" value={String(showdowns)} tone="profit" />
        <StatCard
          label="Favoritos"
          value={String(hands.filter((h) => h.favorite).length)}
          tone="neutral"
        />
      </div>

      <Panel title="Mãos" subtitle="Clique em revisar para abrir o replayer">
        <div className="border-b border-border px-4 py-3">
          <div className="relative mb-3">
            <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Pesquisar por ID, torneio ou cartas…"
              className="h-9 pl-8 text-sm"
            />
          </div>
          <div className="flex flex-wrap gap-2">
            <Select value={position} onValueChange={setPosition}>
              <SelectTrigger className="h-8 w-[142px] text-xs">
                <SelectValue placeholder="Posição" />
              </SelectTrigger>
              <SelectContent>
                {POSITIONS.map((p) => (
                  <SelectItem key={p} value={p} className="text-xs">
                    Posição: {p}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={showdownOnly} onValueChange={setShowdownOnly}>
              <SelectTrigger className="h-8 w-[142px] text-xs">
                <SelectValue placeholder="Showdown" />
              </SelectTrigger>
              <SelectContent>
                {["Todos", "Sim", "Não"].map((o) => (
                  <SelectItem key={o} value={o} className="text-xs">
                    Showdown: {o}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={allInOnly} onValueChange={setAllInOnly}>
              <SelectTrigger className="h-8 w-[142px] text-xs">
                <SelectValue placeholder="All-in" />
              </SelectTrigger>
              <SelectContent>
                {["Todos", "Sim", "Não"].map((o) => (
                  <SelectItem key={o} value={o} className="text-xs">
                    All-in: {o}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Mão</TableHead>
                <TableHead>Torneio</TableHead>
                <TableHead>Pos.</TableHead>
                <TableHead className="text-right">Stack</TableHead>
                <TableHead>Cartas</TableHead>
                <TableHead>Board</TableHead>
                <TableHead>Street</TableHead>
                <TableHead>Tags</TableHead>
                <TableHead className="text-right">Resultado</TableHead>
                <TableHead className="text-right">Ação</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading && (
                <TableRow>
                  <TableCell
                    colSpan={10}
                    className="py-10 text-center text-sm text-muted-foreground"
                  >
                    Carregando…
                  </TableCell>
                </TableRow>
              )}
              {!isLoading && hands.length === 0 && (
                <TableRow>
                  <TableCell
                    colSpan={10}
                    className="py-10 text-center text-sm text-muted-foreground"
                  >
                    Nenhuma mão encontrada.
                  </TableCell>
                </TableRow>
              )}
              {hands.map((h) => (
                <TableRow key={`${h.site}-${h.hand_id}`}>
                  <TableCell className="num text-xs text-muted-foreground">
                    {h.hand_display_id}
                  </TableCell>
                  <TableCell className="max-w-[180px] truncate text-xs">{h.tournament}</TableCell>
                  <TableCell>
                    {h.position ? (
                      <Badge variant="secondary" className="num text-[10px]">
                        {h.position}
                      </Badge>
                    ) : (
                      <span className="text-xs text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  <TableCell className="num text-right text-xs">
                    {h.stack_bb != null ? `${h.stack_bb} BB` : "—"}
                  </TableCell>
                  <TableCell>
                    {h.cards.length >= 2 ? (
                      <Hole cards={h.cards} size="sm" />
                    ) : (
                      <span className="text-xs text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  <TableCell>
                    {h.board.length ? (
                      <span className="flex gap-0.5">
                        {h.board.map((c, i) => (
                          <PlayingCard key={`${h.hand_id}-board-${i}`} card={c} size="sm" />
                        ))}
                      </span>
                    ) : (
                      <span className="text-xs text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">{h.street}</TableCell>
                  <TableCell>
                    <span className="flex flex-wrap gap-1">
                      {h.tags.map((t) => (
                        <Badge key={t} variant="outline" className="text-[10px] font-normal">
                          {t}
                        </Badge>
                      ))}
                    </span>
                  </TableCell>
                  <TableCell className="text-right text-xs">
                    <Money value={h.result_bb} suffix=" BB" />
                  </TableCell>
                  <TableCell className="text-right">
                    <Button variant="outline" size="sm" asChild>
                      <Link to="/replayer" search={{ site: h.site, handId: h.hand_id }}>
                        Revisar
                      </Link>
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
