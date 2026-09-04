import { createFileRoute, Link } from "@tanstack/react-router";
import { Download, Filter, Search } from "lucide-react";

import { Money, PageHeader, Panel, StatCard } from "@/components/lab";
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
import { sessions } from "@/lib/mock-data";

export const Route = createFileRoute("/sessoes")({
  head: () => ({
    meta: [
      { title: "Sessões — PokerLab" },
      {
        name: "description",
        content: "Histórico de sessões de MTT com lucro, ROI, tempo, volume de mãos e análise.",
      },
      { property: "og:title", content: "Sessões — PokerLab" },
      {
        property: "og:description",
        content: "Filtre e analise cada sessão de torneios em detalhe.",
      },
    ],
  }),
  component: SessionsPage,
});

function SessionsPage() {
  const totalProfit = sessions.reduce((acc, s) => acc + s.profit, 0);

  return (
    <div className="space-y-5">
      <PageHeader
        title="Sessões"
        description="8 sessões registradas · 235 torneios · 8.923 mãos importadas"
        actions={
          <Button variant="outline" size="sm">
            <Download className="mr-1.5 size-3.5" /> Exportar
          </Button>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="Lucro do período" value="$1.373" delta="+11,4% ROI" tone="profit" />
        <StatCard label="Sessões positivas" value="5 / 8" delta="62,5%" tone="neutral" />
        <StatCard label="Tempo total" value="30h 10m" delta="3h 46m / sessão" tone="neutral" />
        <StatCard label="Melhor sessão" value="+$890" delta="02/08 · PokerStars" tone="profit" />
      </div>

      <Panel
        title="Histórico"
        subtitle={`Resultado acumulado: ${totalProfit.toFixed(2)} USD`}
        actions={
          <Button variant="ghost" size="sm">
            <Filter className="mr-1.5 size-3.5" /> Filtros
          </Button>
        }
      >
        <div className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-3">
          <div className="relative min-w-[200px] flex-1">
            <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input placeholder="Pesquisar sala ou data…" className="h-9 pl-8 text-sm" />
          </div>
          <Select defaultValue="all">
            <SelectTrigger className="h-9 w-[150px] text-sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todas as salas</SelectItem>
              <SelectItem value="stars">PokerStars</SelectItem>
              <SelectItem value="gg">GGPoker</SelectItem>
              <SelectItem value="888">888poker</SelectItem>
            </SelectContent>
          </Select>
          <Select defaultValue="30">
            <SelectTrigger className="h-9 w-[150px] text-sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="7">Últimos 7 dias</SelectItem>
              <SelectItem value="30">Últimos 30 dias</SelectItem>
              <SelectItem value="90">Últimos 90 dias</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Data</TableHead>
                <TableHead>Sala</TableHead>
                <TableHead className="text-right">Torneios</TableHead>
                <TableHead className="text-right">ABI</TableHead>
                <TableHead className="text-right">Lucro</TableHead>
                <TableHead className="text-right">ROI</TableHead>
                <TableHead className="text-right">Tempo</TableHead>
                <TableHead className="text-right">Mãos</TableHead>
                <TableHead className="text-right">Ação</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sessions.map((s) => (
                <TableRow key={s.id}>
                  <TableCell className="num text-xs">{s.date}</TableCell>
                  <TableCell className="text-sm font-medium">
                    <Badge variant="outline" className="font-normal">
                      {s.room}
                    </Badge>
                  </TableCell>
                  <TableCell className="num text-right text-xs">{s.tournaments}</TableCell>
                  <TableCell className="num text-right text-xs">${s.abi.toFixed(2)}</TableCell>
                  <TableCell className="text-right text-xs">
                    <Money value={s.profit} />
                  </TableCell>
                  <TableCell className="text-right text-xs">
                    <Money value={s.roi} suffix="%" />
                  </TableCell>
                  <TableCell className="num text-right text-xs text-muted-foreground">
                    {s.duration}
                  </TableCell>
                  <TableCell className="num text-right text-xs text-muted-foreground">
                    {s.hands}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button variant="outline" size="sm" asChild>
                      <Link to="/maos">Analisar</Link>
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
