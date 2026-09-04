import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Loader2, Upload, XCircle } from "lucide-react";
import { useRef, useState } from "react";

import { PageHeader, Panel } from "@/components/lab";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { importApi, type ImportResult } from "@/lib/api";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/configuracoes")({
  head: () => ({
    meta: [
      { title: "Configurações — PokerLab" },
      {
        name: "description",
        content: "Ajuste importação de hand history, moeda, salas, preferências de estudo e IA.",
      },
      { property: "og:title", content: "Configurações — PokerLab" },
      { property: "og:description", content: "Preferências da sua conta e do motor de análise." },
    ],
  }),
  component: SettingsPage,
});

const toggles = [
  { label: "Detecção automática de leaks", hint: "Analisa cada sessão importada", on: true },
  { label: "Resumo diário da IA", hint: "Enviado ao final de cada sessão", on: true },
  { label: "Marcar all-ins automaticamente", hint: "Cria tags de push/fold e ICM", on: true },
  { label: "Alertas de meta", hint: "Avisa quando uma meta é atingida", on: false },
];

function SettingsPage() {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [result, setResult] = useState<ImportResult | null>(null);

  const uploadMutation = useMutation({
    mutationFn: (files: File[]) => importApi.upload(files),
    onSuccess: (data) => {
      setResult(data);
      setSelectedFiles([]);
      if (fileInputRef.current) fileInputRef.current.value = "";
      // qualquer página que já tenha buscado mãos/torneios fica stale após importar
      queryClient.invalidateQueries();
    },
  });

  return (
    <div className="space-y-5">
      <PageHeader
        title="Configurações"
        description="Conta, importação e preferências do motor de análise"
        actions={<Button size="sm">Salvar alterações</Button>}
      />

      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title="Perfil" subtitle="Dados usados nos relatórios">
          <div className="space-y-4 p-4">
            <div className="grid gap-1.5">
              <Label htmlFor="name" className="text-xs">
                Nome
              </Label>
              <Input id="name" defaultValue="Felipe Sembay" className="h-9 text-sm" />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="nick" className="text-xs">
                Nickname principal
              </Label>
              <Input id="nick" defaultValue="lvpoker" className="h-9 text-sm" />
            </div>
            <div className="grid gap-1.5">
              <Label className="text-xs">Nível de stakes</Label>
              <Select defaultValue="low">
                <SelectTrigger className="h-9 text-sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="micro">Micro Stakes</SelectItem>
                  <SelectItem value="low">Low Stakes</SelectItem>
                  <SelectItem value="mid">Mid Stakes</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </Panel>

        <Panel title="Importação" subtitle="Upload de hand history (.txt)">
          <div className="space-y-4 p-4">
            <div className="grid gap-1.5">
              <Label className="text-xs">Salas com parser (detecção automática)</Label>
              <div className="flex flex-wrap gap-2">
                {["PartyPoker", "PokerStars"].map((r) => (
                  <span
                    key={r}
                    className="rounded-md border border-border bg-elevated/50 px-2.5 py-1 text-xs"
                  >
                    {r}
                  </span>
                ))}
              </div>
              <p className="text-[11px] text-muted-foreground">
                GGPoker/888poker/Winamax ainda não têm parser — importar arquivo dessas salas dá
                erro de "formato não reconhecido".
              </p>
            </div>

            <Separator />

            <div className="grid gap-1.5">
              <Label htmlFor="file-upload" className="text-xs">
                Arquivos de hand history
              </Label>
              <input
                ref={fileInputRef}
                id="file-upload"
                type="file"
                accept=".txt"
                multiple
                className="hidden"
                onChange={(e) => setSelectedFiles(Array.from(e.target.files ?? []))}
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className={cn(
                  "flex min-h-24 flex-col items-center justify-center gap-2 rounded-md border border-dashed border-border bg-elevated/30 p-4 text-center transition-colors hover:border-primary/50",
                )}
              >
                <Upload className="size-5 text-muted-foreground" />
                <span className="text-xs text-muted-foreground">
                  {selectedFiles.length > 0
                    ? `${selectedFiles.length} arquivo${selectedFiles.length > 1 ? "s" : ""} selecionado${selectedFiles.length > 1 ? "s" : ""}`
                    : "Clique para escolher arquivos .txt"}
                </span>
              </button>
              {selectedFiles.length > 0 && (
                <ul className="num space-y-0.5 text-[11px] text-muted-foreground">
                  {selectedFiles.map((f) => (
                    <li key={f.name} className="truncate">
                      {f.name}
                    </li>
                  ))}
                </ul>
              )}
              <Button
                size="sm"
                disabled={selectedFiles.length === 0 || uploadMutation.isPending}
                onClick={() => uploadMutation.mutate(selectedFiles)}
              >
                {uploadMutation.isPending ? (
                  <>
                    <Loader2 className="mr-1.5 size-3.5 animate-spin" /> Importando…
                  </>
                ) : (
                  "Importar"
                )}
              </Button>
            </div>

            {uploadMutation.isError && (
              <p className="text-xs text-loss">
                Erro ao importar: {(uploadMutation.error as Error).message}
              </p>
            )}

            {result && (
              <div className="space-y-2 rounded-md border border-border bg-elevated/40 p-3">
                <p className="text-xs font-semibold">
                  {result.total_new} mão{result.total_new !== 1 ? "s" : ""} nova
                  {result.total_new !== 1 ? "s" : ""} importada{result.total_new !== 1 ? "s" : ""}
                </p>
                <ul className="space-y-1">
                  {result.files.map((f) => (
                    <li key={f.filename} className="flex items-start gap-2 text-[11px]">
                      {f.error ? (
                        <XCircle className="mt-0.5 size-3 shrink-0 text-loss" />
                      ) : (
                        <CheckCircle2 className="mt-0.5 size-3 shrink-0 text-profit" />
                      )}
                      <span className="min-w-0 flex-1">
                        <span className="truncate font-medium">{f.filename}</span>
                        {f.error ? (
                          <span className="block text-loss">{f.error}</span>
                        ) : (
                          <span className="block text-muted-foreground">
                            {f.site} · {f.hands_in_file} mãos no arquivo · {f.hands_new} novas
                          </span>
                        )}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </Panel>
      </div>

      <Panel title="Motor de análise" subtitle="Automação e IA">
        <div className="divide-y divide-border">
          {toggles.map((t) => (
            <div
              key={t.label}
              className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-4 px-4 py-3"
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">{t.label}</p>
                <p className="truncate text-xs text-muted-foreground">{t.hint}</p>
              </div>
              <Switch defaultChecked={t.on} />
            </div>
          ))}
        </div>
        <Separator />
        <div className="flex flex-wrap items-center justify-between gap-3 p-4">
          <p className="text-xs text-muted-foreground">
            Os dados de mãos ficam vinculados apenas à sua conta.
          </p>
          <Button variant="outline" size="sm">
            Exportar meus dados
          </Button>
        </div>
      </Panel>
    </div>
  );
}
