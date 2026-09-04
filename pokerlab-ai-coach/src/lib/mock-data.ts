// Static mock data for the PokerLab study platform UI.

export type Session = {
  id: string;
  date: string;
  room: string;
  tournaments: number;
  profit: number;
  roi: number;
  duration: string;
  hands: number;
  abi: number;
};

export const sessions: Session[] = [
  {
    id: "s-1",
    date: "2026-08-05",
    room: "PokerStars",
    tournaments: 34,
    profit: 412.6,
    roi: 18.4,
    duration: "4h 12m",
    hands: 1284,
    abi: 6.5,
  },
  {
    id: "s-2",
    date: "2026-08-04",
    room: "GGPoker",
    tournaments: 28,
    profit: -156.2,
    roi: -9.1,
    duration: "3h 40m",
    hands: 1012,
    abi: 5.5,
  },
  {
    id: "s-3",
    date: "2026-08-02",
    room: "PokerStars",
    tournaments: 41,
    profit: 890.4,
    roi: 27.6,
    duration: "5h 05m",
    hands: 1663,
    abi: 7.75,
  },
  {
    id: "s-4",
    date: "2026-08-01",
    room: "888poker",
    tournaments: 19,
    profit: 64.1,
    roi: 4.2,
    duration: "2h 25m",
    hands: 702,
    abi: 4.4,
  },
  {
    id: "s-5",
    date: "2026-07-30",
    room: "GGPoker",
    tournaments: 36,
    profit: -228.9,
    roi: -12.7,
    duration: "4h 48m",
    hands: 1391,
    abi: 5.0,
  },
  {
    id: "s-6",
    date: "2026-07-29",
    room: "PokerStars",
    tournaments: 30,
    profit: 305.8,
    roi: 14.9,
    duration: "3h 58m",
    hands: 1147,
    abi: 6.5,
  },
  {
    id: "s-7",
    date: "2026-07-27",
    room: "Winamax",
    tournaments: 22,
    profit: 178.3,
    roi: 11.2,
    duration: "2h 52m",
    hands: 806,
    abi: 5.5,
  },
  {
    id: "s-8",
    date: "2026-07-26",
    room: "GGPoker",
    tournaments: 25,
    profit: -92.4,
    roi: -5.4,
    duration: "3h 10m",
    hands: 918,
    abi: 5.5,
  },
];

export const bankrollCurve = [
  { d: "Mar", bankroll: 3120, profit: 210, roi: 6.4 },
  { d: "Abr", bankroll: 3480, profit: 360, roi: 9.8 },
  { d: "Mai", bankroll: 3305, profit: -175, roi: -4.1 },
  { d: "Jun", bankroll: 4010, profit: 705, roi: 14.2 },
  { d: "Jul", bankroll: 4620, profit: 610, roi: 12.7 },
  { d: "Ago", bankroll: 5480, profit: 860, roi: 18.4 },
];

export const evolutionCurve = [
  { d: "Mar", pushfold: 71, icm: 62, leaks: 2 },
  { d: "Abr", pushfold: 74, icm: 66, leaks: 4 },
  { d: "Mai", pushfold: 76, icm: 69, leaks: 5 },
  { d: "Jun", pushfold: 82, icm: 74, leaks: 8 },
  { d: "Jul", pushfold: 86, icm: 79, leaks: 11 },
  { d: "Ago", pushfold: 91, icm: 84, leaks: 14 },
];

export type Hand = {
  id: string;
  handId: string;
  tournament: string;
  position: string;
  stackBB: number;
  cards: [string, string];
  board: string[];
  result: number;
  allIn: boolean;
  showdown: boolean;
  tags: string[];
  street: string;
};

export const hands: Hand[] = [
  {
    id: "h-1",
    handId: "#48219301",
    tournament: "Bounty Builder $5.50",
    position: "BTN",
    stackBB: 14.2,
    cards: ["Ah", "Jd"],
    board: ["Kd", "9c", "4s", "2h", "Qs"],
    result: 12.4,
    allIn: true,
    showdown: true,
    tags: ["push/fold", "steal"],
    street: "Showdown",
  },
  {
    id: "h-2",
    handId: "#48219288",
    tournament: "Hot $11 Turbo",
    position: "CO",
    stackBB: 22.8,
    cards: ["Qs", "Qc"],
    board: ["7h", "5d", "2c", "Ks"],
    result: -22.8,
    allIn: true,
    showdown: true,
    tags: ["cooler"],
    street: "Turn",
  },
  {
    id: "h-3",
    handId: "#48219240",
    tournament: "Micro Deep $3.30",
    position: "SB",
    stackBB: 41.5,
    cards: ["Td", "9d"],
    board: ["Jd", "8d", "3c"],
    result: 18.6,
    allIn: false,
    showdown: false,
    tags: ["bluff"],
    street: "Flop",
  },
  {
    id: "h-4",
    handId: "#48219188",
    tournament: "Bounty Builder $5.50",
    position: "BB",
    stackBB: 9.7,
    cards: ["Ks", "Th"],
    board: [],
    result: -9.7,
    allIn: true,
    showdown: true,
    tags: ["icm", "bolha"],
    street: "Preflop",
  },
  {
    id: "h-5",
    handId: "#48219150",
    tournament: "Sunday Storm $11",
    position: "HJ",
    stackBB: 31.2,
    cards: ["As", "Ks"],
    board: ["Ac", "8s", "6h", "3d", "9s"],
    result: 46.9,
    allIn: false,
    showdown: true,
    tags: ["value"],
    street: "Showdown",
  },
  {
    id: "h-6",
    handId: "#48219101",
    tournament: "Hot $11 Turbo",
    position: "UTG",
    stackBB: 17.4,
    cards: ["9c", "9h"],
    board: ["Qd", "Jh", "4c"],
    result: -17.4,
    allIn: true,
    showdown: true,
    tags: ["bad beat"],
    street: "Flop",
  },
  {
    id: "h-7",
    handId: "#48219044",
    tournament: "Micro Deep $3.30",
    position: "BTN",
    stackBB: 12.1,
    cards: ["Ad", "5c"],
    board: [],
    result: 6.5,
    allIn: true,
    showdown: false,
    tags: ["push/fold"],
    street: "Preflop",
  },
  {
    id: "h-8",
    handId: "#48218990",
    tournament: "Sunday Storm $11",
    position: "BB",
    stackBB: 26.3,
    cards: ["Jh", "Jc"],
    board: ["9s", "7c", "2d", "Jd"],
    result: 58.2,
    allIn: false,
    showdown: true,
    tags: ["hero call"],
    street: "Showdown",
  },
];

export type PushFoldSpot = {
  id: string;
  spot: string;
  stack: string;
  position: string;
  taken: string;
  correct: string;
  ev: number;
};

export const pushFoldSpots: PushFoldSpot[] = [
  {
    id: "pf-1",
    spot: "Open shove vs 2 limpers",
    stack: "13.4 BB",
    position: "BTN",
    taken: "Fold",
    correct: "All-in",
    ev: -0.42,
  },
  {
    id: "pf-2",
    spot: "Vs BTN shove",
    stack: "9.1 BB",
    position: "BB",
    taken: "Call",
    correct: "Call",
    ev: 0.18,
  },
  {
    id: "pf-3",
    spot: "Open shove folded to",
    stack: "16.8 BB",
    position: "SB",
    taken: "Raise",
    correct: "All-in",
    ev: -0.11,
  },
  {
    id: "pf-4",
    spot: "Vs CO shove",
    stack: "11.2 BB",
    position: "BTN",
    taken: "Fold",
    correct: "Fold",
    ev: 0.0,
  },
  {
    id: "pf-5",
    spot: "Open shove vs limp",
    stack: "14.0 BB",
    position: "CO",
    taken: "Fold",
    correct: "All-in",
    ev: -0.57,
  },
  {
    id: "pf-6",
    spot: "Vs SB shove",
    stack: "8.4 BB",
    position: "BB",
    taken: "Call",
    correct: "Call",
    ev: 0.31,
  },
];

export type TrainerQuestion = {
  id: string;
  hero: [string, string];
  position: string;
  stack: string;
  context: string;
  blinds: string;
  correct: "Fold" | "Raise" | "All-in";
  ev: string;
  explanation: string;
};

export const trainerQuestions: TrainerQuestion[] = [
  {
    id: "q-1",
    hero: ["Ah", "Jc"],
    position: "BTN",
    stack: "14 BB",
    context: "Todos foldaram até você. 6 jogadores na mesa, fase média do torneio.",
    blinds: "600 / 1.200 (150 ante)",
    correct: "All-in",
    ev: "+0,54 BB",
    explanation:
      "Com 14 BB no BTN e a mesa foldada, AJo está claramente na range de shove. Fold perde ~0,54 BB de EV, e um min-raise cria spots ruins com stack raso ao enfrentar 3-bet dos blinds.",
  },
  {
    id: "q-2",
    hero: ["8d", "8s"],
    position: "SB",
    stack: "11 BB",
    context:
      "BB é um regular agressivo com 26 BB. Bolha próxima (28 jogadores restantes, 25 pagos).",
    blinds: "800 / 1.600 (200 ante)",
    correct: "All-in",
    ev: "+1,12 BB",
    explanation:
      "88 no SB com 11 BB é um shove padrão mesmo com pressão de ICM. O BB coberto precisa de uma range de call apertada; sua equidade contra ela ainda é lucrativa.",
  },
  {
    id: "q-3",
    hero: ["Ks", "9h"],
    position: "BB",
    stack: "9 BB",
    context: "CO shove 9,5 BB. Bolha da mesa final (10 jogadores restantes).",
    blinds: "1.000 / 2.000 (250 ante)",
    correct: "Fold",
    ev: "+0,22 BB",
    explanation:
      "K9o parece jogável, mas o ICM da bolha de FT aumenta o custo de eliminação. Contra a range de shove do CO, o call é levemente -EV em chips e claramente -EV em $EV.",
  },
];

export type IcmSpot = {
  id: string;
  scenario: string;
  category: "Mesa Final" | "Bolha" | "Satélite" | "FT" | "Hero Call";
  stack: string;
  risk: string;
  accuracy: number;
  evDiff: number;
};

export const icmSpots: IcmSpot[] = [
  {
    id: "icm-1",
    scenario: "3 left, chip leader abre BTN",
    category: "Mesa Final",
    stack: "18 BB",
    risk: "Alto",
    accuracy: 88,
    evDiff: 0.4,
  },
  {
    id: "icm-2",
    scenario: "Bolha, short shove UTG",
    category: "Bolha",
    stack: "12 BB",
    risk: "Crítico",
    accuracy: 64,
    evDiff: -1.2,
  },
  {
    id: "icm-3",
    scenario: "Satélite, 2 vagas restantes",
    category: "Satélite",
    stack: "22 BB",
    risk: "Extremo",
    accuracy: 71,
    evDiff: -0.8,
  },
  {
    id: "icm-4",
    scenario: "FT 7-handed, call vs BB",
    category: "FT",
    stack: "15 BB",
    risk: "Médio",
    accuracy: 92,
    evDiff: 0.6,
  },
  {
    id: "icm-5",
    scenario: "Hero call river 2/3 pot",
    category: "Hero Call",
    stack: "34 BB",
    risk: "Médio",
    accuracy: 79,
    evDiff: 0.1,
  },
  {
    id: "icm-6",
    scenario: "Bolha, defesa de BB vs SB",
    category: "Bolha",
    stack: "9 BB",
    risk: "Alto",
    accuracy: 58,
    evDiff: -1.6,
  },
];

export const leaks = [
  {
    name: "Fold excessivo entre 12 e 18 BB",
    severity: "Alto",
    evLost: "-3,4 BB/100",
    occurrences: 42,
    trend: -8,
  },
  {
    name: "Call de all-in largo na bolha",
    severity: "Alto",
    evLost: "-2,8 BB/100",
    occurrences: 27,
    trend: -5,
  },
  {
    name: "3-bet insuficiente vs steals do BTN",
    severity: "Médio",
    evLost: "-1,6 BB/100",
    occurrences: 61,
    trend: 3,
  },
  {
    name: "C-bet em flops multiway",
    severity: "Baixo",
    evLost: "-0,7 BB/100",
    occurrences: 88,
    trend: 6,
  },
];

export const studyCategories = [
  { name: "Push/Fold", count: 34, description: "Ranges de shove e call por stack efetivo" },
  { name: "ICM", count: 21, description: "Bolha, mesa final e satélites" },
  { name: "Bluffs", count: 18, description: "Construção de range de blefe por street" },
  { name: "Hero Calls", count: 12, description: "Leitura de linhas polarizadas no river" },
  { name: "Bad Beats", count: 9, description: "Revisão de variância e decisões corretas" },
  { name: "Coolers", count: 7, description: "Spots inevitáveis e controle de dano" },
  { name: "Favoritos", count: 15, description: "Mãos e lições marcadas por você" },
];

export const studyItems = [
  { title: "Shoves de BTN entre 10 e 15 BB", category: "Push/Fold", minutes: 12, progress: 100 },
  { title: "Ranges de call do BB vs SB shove", category: "Push/Fold", minutes: 15, progress: 70 },
  { title: "Pressão de ICM na bolha", category: "ICM", minutes: 18, progress: 45 },
  { title: "Satélites: sobrevivência vs chips", category: "ICM", minutes: 10, progress: 0 },
  { title: "Blefes de river com blockers", category: "Bluffs", minutes: 22, progress: 30 },
  { title: "Hero call vs regs passivos", category: "Hero Calls", minutes: 14, progress: 0 },
];

export const tags = [
  { name: "push/fold", count: 128, color: "primary" },
  { name: "icm", count: 74, color: "primary" },
  { name: "bolha", count: 52, color: "primary" },
  { name: "bluff", count: 43, color: "primary" },
  { name: "hero call", count: 31, color: "primary" },
  { name: "cooler", count: 26, color: "loss" },
  { name: "bad beat", count: 22, color: "loss" },
  { name: "value", count: 61, color: "profit" },
  { name: "steal", count: 88, color: "profit" },
];

export const coachMessages = [
  {
    role: "assistant" as const,
    content:
      "**Resumo da sessão de 05/08 — 34 torneios, 1.284 mãos**\n\nHoje você jogou muito bem. Seu ROI de 18,4% está acima da sua média de 90 dias (12,1%).\n\n**Principal erro:** fold excessivo entre 12 e 18 BB — 9 spots identificados, custo estimado de -3,4 BB/100.\n\n**Principal acerto:** steals do BTN. Sua frequência de 42% está bem calibrada e a taxa de fold dos blinds contra você é de 61%.\n\n**Objetivo para amanhã:** 15 minutos no treinador de Push/Fold com stacks de 12 a 18 BB.",
  },
  {
    role: "user" as const,
    content: "Por que o fold com AJo no BTN com 14BB é ruim?",
  },
  {
    role: "assistant" as const,
    content:
      "Com 14 BB efetivos e a mesa foldada até o BTN, você tem duas boas opções: shove ou raise pequeno. AJo tem equidade forte contra as ranges de call de SB/BB e ganha o pote sem showdown com frequência alta.\n\nFoldar entrega ~0,54 BB de EV por spot. Repetido 9 vezes na sessão, isso é praticamente um buy-in de $5,50 descartado.\n\nQuer que eu monte um drill de 20 spots exatamente nessa faixa de stack?",
  },
];

export const favorites = [
  {
    title: "Hero call no river com JJ",
    type: "Mão",
    meta: "Sunday Storm $11 · +58,2 BB",
    tag: "hero call",
  },
  {
    title: "Shove de 14 BB no BTN com AJo",
    type: "Mão",
    meta: "Bounty Builder $5.50 · +12,4 BB",
    tag: "push/fold",
  },
  { title: "Pressão de ICM na bolha", type: "Estudo", meta: "18 min · 45% concluído", tag: "icm" },
  {
    title: "Cooler QQ vs KK na turn",
    type: "Mão",
    meta: "Hot $11 Turbo · -22,8 BB",
    tag: "cooler",
  },
  {
    title: "Blefes de river com blockers",
    type: "Estudo",
    meta: "22 min · 30% concluído",
    tag: "bluff",
  },
  {
    title: "Defesa de BB vs SB shove",
    type: "Drill",
    meta: "20 spots · 78% precisão",
    tag: "push/fold",
  },
];

export const goals = [
  { name: "Precisão Push/Fold ≥ 92%", current: 91, target: 92 },
  { name: "Precisão ICM ≥ 88%", current: 84, target: 88 },
  { name: "ROI de 90 dias ≥ 15%", current: 12.1, target: 15 },
  { name: "Leaks corrigidos: 18", current: 14, target: 18 },
];

// Heatmap: 13x13 hand grid (AA top-left) with a synthetic frequency value.
const RANKS = ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"];

export const handMatrix = RANKS.flatMap((r1, i) =>
  RANKS.map((r2, j) => {
    const label = i === j ? `${r1}${r2}` : i < j ? `${r1}${r2}s` : `${r2}${r1}o`;
    const strength = Math.max(0, 1 - (i + j) / 20 - (i === j ? 0 : 0.12) - (i > j ? 0.16 : 0));
    return { label, row: i, col: j, value: Math.round(strength * 100) / 100 };
  }),
);

export const sessionCalendar = Array.from({ length: 35 }, (_, i) => {
  const seeded = Math.sin(i * 12.9898) * 43758.5453;
  const frac = seeded - Math.floor(seeded);
  const played = frac > 0.38;
  return {
    day: i + 1,
    played,
    profit: played ? Math.round((frac - 0.55) * 1400) : 0,
  };
});

export const dashboardStats = [
  {
    label: "Lucro",
    value: "$5.482",
    delta: "+18,4%",
    tone: "profit" as const,
    hint: "Últimos 90 dias",
  },
  { label: "ROI", value: "12,1%", delta: "+2,3 pp", tone: "profit" as const, hint: "235 torneios" },
  { label: "ABI", value: "$6,12", delta: "+$0,40", tone: "neutral" as const, hint: "Buy-in médio" },
  { label: "ITM", value: "17,8%", delta: "+1,1 pp", tone: "profit" as const, hint: "In the money" },
  { label: "FT", value: "3,4%", delta: "-0,2 pp", tone: "loss" as const, hint: "Mesas finais" },
  {
    label: "Bankroll",
    value: "$5.480",
    delta: "+$860",
    tone: "profit" as const,
    hint: "894 BI médios",
  },
  {
    label: "Horas jogadas",
    value: "148h",
    delta: "+22h",
    tone: "neutral" as const,
    hint: "Este mês",
  },
  {
    label: "Torneios",
    value: "1.842",
    delta: "+235",
    tone: "neutral" as const,
    hint: "Amostra total",
  },
];
