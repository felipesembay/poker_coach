import { Link, useRouterState } from "@tanstack/react-router";
import {
  Home,
  Layers,
  Table2,
  PlayCircle,
  LineChart,
  Target,
  Coins,
  Brain,
  Star,
  Tag,
  TrendingUp,
  Settings,
  Spade,
} from "lucide-react";

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";

const groups = [
  {
    label: "Visão geral",
    items: [
      { title: "Dashboard", url: "/", icon: Home },
      { title: "Sessões", url: "/sessoes", icon: Layers },
      { title: "Hand History", url: "/maos", icon: Table2 },
      { title: "Replayer", url: "/replayer", icon: PlayCircle },
      { title: "Estatísticas", url: "/estatisticas", icon: LineChart },
    ],
  },
  {
    label: "Treino",
    items: [
      { title: "Push/Fold", url: "/push-fold", icon: Target },
      { title: "ICM", url: "/icm", icon: Coins },
      { title: "Coach IA", url: "/coach", icon: Brain },
    ],
  },
  {
    label: "Biblioteca",
    items: [
      { title: "Favoritos", url: "/favoritos", icon: Star },
      { title: "Tags", url: "/tags", icon: Tag },
      { title: "Evolução", url: "/evolucao", icon: TrendingUp },
      { title: "Configurações", url: "/configuracoes", icon: Settings },
    ],
  },
];

export function AppSidebar() {
  const pathname = useRouterState({ select: (s) => s.location.pathname });

  const isActive = (url: string) =>
    url === "/" ? pathname === "/" : pathname === url || pathname.startsWith(`${url}/`);

  return (
    <Sidebar collapsible="icon" className="border-sidebar-border">
      <SidebarHeader className="border-b border-sidebar-border">
        <div className="flex min-w-0 items-center gap-2.5 px-1 py-1.5">
          <div className="grid size-8 shrink-0 place-items-center rounded-md border border-sidebar-border bg-sidebar-accent">
            <Spade className="size-4 text-primary" />
          </div>
          <div className="min-w-0 group-data-[collapsible=icon]:hidden">
            <p className="truncate text-sm font-extrabold tracking-tight text-sidebar-accent-foreground">
              PokerLab
            </p>
            <p className="num truncate text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
              MTT Study Suite
            </p>
          </div>
        </div>
      </SidebarHeader>

      <SidebarContent>
        {groups.map((group) => (
          <SidebarGroup key={group.label}>
            <SidebarGroupLabel className="text-[10px] uppercase tracking-[0.16em]">
              {group.label}
            </SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {group.items.map((item) => (
                  <SidebarMenuItem key={item.url}>
                    <SidebarMenuButton asChild isActive={isActive(item.url)} tooltip={item.title}>
                      <Link to={item.url} className="flex items-center gap-2.5">
                        <item.icon className="size-4 shrink-0" />
                        <span className="truncate">{item.title}</span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        ))}
      </SidebarContent>

      <SidebarFooter className="border-t border-sidebar-border">
        <div className="flex min-w-0 items-center gap-2.5 px-1 py-1">
          <div className="num grid size-8 shrink-0 place-items-center rounded-md bg-primary/15 text-xs font-bold text-primary">
            LV
          </div>
          <div className="min-w-0 group-data-[collapsible=icon]:hidden">
            <p className="truncate text-xs font-semibold">Felipe Sembay</p>
            <p className="truncate text-[11px] text-muted-foreground">Micro / Low MTT</p>
          </div>
        </div>
      </SidebarFooter>
    </Sidebar>
  );
}
