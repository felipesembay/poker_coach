// Cliente da API do PokerLab (FastAPI, poker_coach/api/) — substitui
// lib/mock-data.ts progressivamente, página por página.
//
// Ver poker_coach/api/TESTING.md pro que é real vs. heurística/templado
// em cada endpoint.

const BASE_URL = import.meta.env["VITE_API_URL"] ?? "http://localhost:8100";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${path}: ${body}`);
  }
  return res.json() as Promise<T>;
}

function qs(params: Record<string, string | number | boolean | undefined | null>): string {
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") s.set(k, String(v));
  }
  const str = s.toString();
  return str ? `?${str}` : "";
}

// ---------------- Push/Fold ----------------

export type PushFoldSpot = {
  site: string;
  hand_id: string;
  tournament_id: string;
  spot: string;
  position: string;
  stack: string;
  hero_cards: string;
  taken: "Fold" | "All-in";
  correct: "Fold" | "All-in";
  ev: number;
  ev_lost_bb: number;
};

export type PushFoldSummary = {
  spots: number;
  leak_spots: number;
  total_ev_lost_bb: number;
  by_position: Record<string, { spots: number; ev_lost_bb: number; leaks: number }>;
};

export type RangeGrid = {
  effective_bb: number;
  pot_bb: number;
  shove_pct: number;
  call_pct: number;
  grid: Record<string, number>;
};

export const pushfoldApi = {
  spots: (params: { bb_min?: number; bb_max?: number; limit?: number } = {}) =>
    request<PushFoldSpot[]>(`/api/pushfold/spots${qs(params)}`),
  summary: (params: { bb_min?: number; bb_max?: number } = {}) =>
    request<PushFoldSummary>(`/api/pushfold/summary${qs(params)}`),
  rangeGrid: (params: { effective_bb: number; pot_bb: number }) =>
    request<RangeGrid>(`/api/pushfold/range-grid${qs(params)}`),
  callGrid: (params: { effective_bb: number; pot_bb: number }) =>
    request<RangeGrid>(`/api/pushfold/call-grid${qs(params)}`),
};

// ---------------- Leak Finder / heatmap Push/Fold ----------------
// Mesma agregação (posição × faixa de stack) por trás das duas telas —
// ver poker_coach/pushfold/analyze.py:leak_categories.

export type DecisionScope = "open_shove" | "facing_shove";

export type LeakCategory = {
  category_key: string;
  decision_scope: DecisionScope;
  position: string;
  stack_bucket: string;
  opportunities: number;
  incorrect: number;
  error_rate_pct: number | null;
  ev_lost_total_bb: number;
  ev_lost_avg_bb: number | null;
};

export type LeakHand = {
  site: string;
  hand_id: string;
  tournament_id: string;
  decision_scope: DecisionScope;
  position: string;
  effective_bb: number;
  hero_cards: string;
  action_taken: string;
  action_reference: string;
  ev_lost_bb: number;
};

export const leaksApi = {
  categories: (params: { bb_min?: number; bb_max?: number } = {}) =>
    request<LeakCategory[]>(`/api/pushfold/leaks${qs(params)}`),
  hands: (params: {
    decision_scope: DecisionScope;
    position: string;
    stack_bucket: string;
    bb_min?: number;
    bb_max?: number;
  }) => request<LeakHand[]>(`/api/pushfold/leaks/hands${qs(params)}`),
};

// ---------------- Leak Detector (Fase 3 do plano de RL — Padrões de comportamento) ----------------
// Distinto do Leak Finder acima: lê o snapshot do dataset exportado
// (`export-rl`), preflop E pós-flop, agrupado por categoria de
// comportamento — ver poker_coach/api/routers/leak_detector.py.

export type LeakConfidence = "alta" | "média" | "baixa";

export type LeakDetectorCategoryRow = {
  leak_category: string;
  sample_size: number;
  reference_coverage: number | null;
  mean_ev_gap: number | null;
  median_ev_gap: number | null;
  std_ev_gap: number | null;
  confidence: LeakConfidence;
};

export type LeakDetectorReport = {
  n_decisions: number;
  n_leaks: number;
  n_reference_available: number;
  sizing_note: string;
  by_category: LeakDetectorCategoryRow[];
};

export type LeakDetectorBreakdownRow = {
  leak_category: string;
  dimension_value: string | null;
  sample_size: number;
  reference_coverage: number | null;
  mean_ev_gap: number | null;
  median_ev_gap: number | null;
  std_ev_gap: number | null;
  confidence: LeakConfidence;
};

export const leakDetectorApi = {
  report: () => request<LeakDetectorReport>("/api/leak-detector/report"),
  breakdown: (category: string, dimension: "position" | "stack" = "position") =>
    request<LeakDetectorBreakdownRow[]>(
      `/api/leak-detector/breakdown${qs({ category, dimension })}`,
    ),
};

// ---------------- Treinador ----------------

export type TrainerSeat = { position: string; is_hero: boolean; stack: number };

export type TrainerMode = "open" | "facing_shove";

export type TrainerQuestion = {
  site: string;
  hand_id: string;
  mode: TrainerMode;
  hero_cards: string;
  position: string;
  shover_position?: string | null;
  effective_bb: number;
  pot_bb: number;
  n_players: number;
  bb: number;
  seats: TrainerSeat[];
  context: string;
};

export type TrainerDecision = "Fold" | "All-in" | "Call";

export type TrainerAnswer = {
  correct: boolean;
  nash_decision: TrainerDecision;
  ev_bb: number;
  ev_lost_bb: number;
  explanation: string;
  // Personal Policy (Fase 2 do plano de RL, Behavioral Cloning) — null
  // quando o modelo treinado não existe no backend, nunca quebra a tela.
  personal_policy_decision?: string | null;
  personal_policy_probs?: Record<string, number> | null;
};

export type TrainerStats = { total: number; correct: number; pct: number | null };

export const trainerApi = {
  next: (
    params: { mode?: TrainerMode; bb_min?: number; bb_max?: number; n_players?: number } = {},
  ) => request<TrainerQuestion>(`/api/pushfold/trainer/next${qs(params)}`),
  nextSameScenario: (
    params: {
      mode?: TrainerMode;
      bb_min?: number;
      bb_max?: number;
      n_players?: number;
      count?: number;
    } = {},
  ) => request<TrainerQuestion[]>(`/api/pushfold/trainer/next-same-scenario${qs(params)}`),
  answer: (
    site: string,
    hand_id: string,
    mode: TrainerMode,
    decision: TrainerDecision,
    hero_cards?: string,
  ) =>
    request<TrainerAnswer>("/api/pushfold/trainer/answer", {
      method: "POST",
      body: JSON.stringify({ site, hand_id, mode, decision, hero_cards }),
    }),
  stats: () => request<TrainerStats>("/api/pushfold/trainer/stats"),
  byDay: () => request<TrainingDay[]>("/api/pushfold/trainer/by-day"),
  byDayDetail: (date: string) =>
    request<TrainingDayDetail>(`/api/pushfold/trainer/by-day/${date}`),
};

export type TrainingDay = {
  date: string;
  hands: number;
  correct: number;
  accuracy_pct: number | null;
  avg_ev_lost_bb: number | null;
  duration_min: number;
};

export type TrainingAnswer = {
  site: string;
  hand_id: string;
  ts: string;
  user_decision: string;
  nash_decision: string;
  correct: boolean;
  ev_lost_bb: number | null;
  hero_stack_bb: number | null;
  hero_position: string | null;
};

export type TrainingStackBucket = { bucket: string; hands: number };
export type TrainingSession = { site: string; tournaments: number; profit: number | null };

export type TrainingDayDetail = {
  date: string;
  answers: TrainingAnswer[];
  stack_buckets: TrainingStackBucket[];
  sessions: TrainingSession[];
};

// ---------------- ICM ----------------

export type IcmTournament = {
  site: string;
  tournament_id: string;
  name: string | null;
  buyin: number | null;
  currency: string | null;
  first_seen: string | null;
  last_seen: string | null;
  n_hands: number;
  finish_position: number | null;
  prize: number | null;
  prize_type: "cash" | "ticket" | null;
  prize_note: string | null;
  has_payouts: boolean;
  rebuys: number;
  entry_type: "cash" | "ticket";
  entry_ticket_site: string | null;
  entry_ticket_tournament_id: string | null;
};

// Ticket ganho (prêmio tipo ticket) e onde foi usado — ver
// poker_coach/api/routers/icm.py::ticket_sources.
export type TicketSource = {
  site: string;
  tournament_id: string;
  name: string | null;
  value: number;
  won_at: string | null;
  used_by_site: string | null;
  used_by_tournament_id: string | null;
};

export type IcmSpot = {
  site: string;
  hand_id: string;
  tournament_id: string;
  scenario: string;
  category: "Mesa Final" | "Bolha" | "Satélite";
  stack: string;
  risk: string;
  risk_premium_pct: number;
  hero_decision: "push" | "fold";
  icm_decision: "push" | "fold";
  icm_ev_fold: number;
  icm_ev_push: number;
  ev_diff: number;
  icm_ev_lost: number;
};

export type IcmSummary = {
  spots: number;
  leak_spots: number;
  total_ev_lost: number;
  rows: IcmSpot[];
};

export type IcmHand = {
  in_scope: boolean;
  reason?: string | null;
  hero_decision?: "push" | "fold" | null;
  icm_decision?: "push" | "fold" | null;
  icm_ev_fold?: number | null;
  icm_ev_push?: number | null;
  icm_ev_lost?: number | null;
  risk_premium_pct?: number | null;
  effective_bb?: number | null;
};

export const icmApi = {
  tournaments: () => request<IcmTournament[]>("/api/icm/tournaments"),
  getPayouts: (site: string, tournamentId: string) =>
    request<number[]>(`/api/icm/tournaments/${site}/${tournamentId}/payouts`),
  setPayouts: (site: string, tournamentId: string, prizes: number[]) =>
    request(`/api/icm/tournaments/${site}/${tournamentId}/payouts`, {
      method: "PUT",
      body: JSON.stringify({ prizes }),
    }),
  setTournamentName: (site: string, tournamentId: string, name: string) =>
    request(`/api/icm/tournaments/${site}/${tournamentId}/name`, {
      method: "PUT",
      body: JSON.stringify({ name }),
    }),
  setTournamentResult: (
    site: string,
    tournamentId: string,
    payload: {
      finish_position: number | null;
      prize: number | null;
      prize_type?: "cash" | "ticket" | null;
      prize_note?: string | null;
    },
  ) =>
    request(`/api/icm/tournaments/${site}/${tournamentId}/result`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  setTournamentEntry: (
    site: string,
    tournamentId: string,
    payload: {
      rebuys: number;
      entry_type: "cash" | "ticket";
      ticket_site: string | null;
      ticket_tournament_id: string | null;
    },
  ) =>
    request(`/api/icm/tournaments/${site}/${tournamentId}/entry`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  ticketSources: () => request<TicketSource[]>("/api/icm/ticket-sources"),
  spots: (params: {
    site: string;
    tournament_id: string;
    confirmed: boolean;
    max_table_size?: number;
  }) => request<IcmSummary>(`/api/icm/spots${qs(params)}`),
  hand: (site: string, handId: string, confirmed: boolean) =>
    request<IcmHand>(`/api/icm/hand/${site}/${handId}${qs({ confirmed })}`),
};

// ---------------- Replayer ----------------

export type HandSummary = {
  site: string;
  hand_id: string;
  tournament_id: string;
  tournament_name: string | null;
  buyin: number | null;
  ts: string | null;
  position: string | null;
  hero_cards: string | null;
  stack_bb: number | null;
  net_bb: number;
  favorite: boolean;
  board: string | null;
  n_players: number | null;
  showdown: boolean;
  all_in: boolean;
};

export type ReplaySeat = {
  seat_no: number;
  player: string;
  starting_stack: number;
  position: string | null;
  is_hero: boolean;
  cards: string | null;
};

export type ReplayStep = {
  order: number;
  street: string;
  player: string;
  position: string | null;
  action: string;
  amount: number;
  all_in: boolean;
  pot_after: number;
  stacks_after: Record<string, number>;
  board_so_far: string;
};

export type PainelIa = {
  in_scope: boolean;
  reason?: string | null;
  spot_kind?: "open" | "facing_shove" | null;
  shover_position?: string | null;
  hero_decision?: string | null;
  nash_decision?: string | null;
  ev_push_bb?: number | null;
  ev_lost_bb?: number | null;
  effective_bb?: number | null;
  pot_bb?: number | null;
};

export type ReplayHand = {
  site: string;
  hand_id: string;
  tournament_id: string;
  tournament_name: string | null;
  buyin: number | null;
  ts: string | null;
  sb: number;
  bb: number;
  ante: number;
  hero: string | null;
  hero_cards: string | null;
  board: string | null;
  seats: ReplaySeat[];
  steps: ReplayStep[];
  street_first_index: Record<string, number>;
  painel_ia: PainelIa;
  note: string;
  tags: string[];
  favorite: boolean;
};

// ---------------- Decision Analysis (Etapa 6 — Equity/Pot Odds/EV contextual) ----------------
//
// Camada nova por cima do painel_ia acima (que só cobre abertura/facing-shove
// preflop). Cobre qualquer passo do hero — ver poker_coach/context.py e
// poker_coach/replay_decision.py.

export type DecisionContext = {
  context_type: string;
  recommended_model: "pushfold_nash" | "contextual_ev" | "postflop_check_only";
  reasoning: string[];
};

export type NashDecision = {
  recommendation: "push" | "fold";
  ev_push_bb: number;
  equity_vs_call_range: number;
  call_pct: number;
  effective_bb: number;
  pot_bb: number;
};

export type DecisionEV = {
  action: "fold" | "call" | "push" | "check";
  applicable: boolean;
  ev: number | null;
  note: string;
};

export type EquityResult = {
  hero_equity: number;
  win_probability: number;
  tie_probability: number;
  loss_probability: number;
  outs: string[];
  turn_improvement_probability: number | null;
  river_improvement_probability: number | null;
  simulation_method: "exact" | "monte_carlo";
  iterations: number;
  confidence_interval: [number, number] | null;
  num_opponents: number;
  assumptions: string[];
};

export type PotOddsResult = {
  pot_before_bet: number;
  villain_bet: number;
  hero_already_in: number;
  additional_money_in: number;
  hero_call_cost: number;
  pot_after_call: number;
  required_equity: number;
  pot_odds_ratio: string;
  facing: "bet" | "raise" | "allin";
  is_partial_call: boolean;
  hero_stack_after_call: number | null;
  assumptions: string[];
};

export type ContextualEV = {
  decisions: DecisionEV[];
  equity: EquityResult | null;
  pot_odds: PotOddsResult | null;
  model: string;
  assumptions: string[];
};

export type PolicySuggestion = {
  // Personal Policy (Fase 2 do plano de RL, Behavioral Cloning) — "o que
  // você costuma fazer" nesse spot, não recomendação de EV (isso é
  // `nash`/`contextual` acima). `null` em `policy` quando o artefato
  // treinado não existe.
  recommended_action: string;
  probs: Record<string, number>;
};

export type DecisionAnalysis = {
  context: DecisionContext;
  nash: NashDecision | null;
  contextual: ContextualEV | null;
  policy: PolicySuggestion | null;
};

export const replayerApi = {
  search: (
    params: {
      site?: string;
      tournament_id?: string;
      position?: string;
      bb_min?: number;
      bb_max?: number;
      n_players?: number;
      result?: "win" | "loss";
      tag?: string;
      q?: string;
      favorite?: boolean;
      showdown?: boolean;
      all_in?: boolean;
      date_from?: string;
      date_to?: string;
      limit?: number;
    } = {},
  ) => request<HandSummary[]>(`/api/replayer/search${qs(params)}`),
  get: (site: string, handId: string) => request<ReplayHand>(`/api/replayer/${site}/${handId}`),
  decision: (site: string, handId: string, step: number) =>
    request<DecisionAnalysis>(`/api/replayer/${site}/${handId}/decision/${step}`),
};

// ---------------- Mãos / Tags / Favoritos ----------------

export type Hand = {
  site: string;
  hand_id: string;
  hand_display_id: string;
  tournament: string;
  tournament_id: string;
  position: string | null;
  stack_bb: number | null;
  cards: string[];
  board: string[];
  result_bb: number;
  all_in: boolean;
  showdown: boolean;
  tags: string[];
  street: string;
  favorite: boolean;
};

export const handsApi = {
  list: (
    params: {
      site?: string;
      position?: string;
      bb_min?: number;
      bb_max?: number;
      tag?: string;
      favorite_only?: boolean;
      showdown_only?: boolean;
      all_in_only?: boolean;
      date_from?: string;
      date_to?: string;
      limit?: number;
      offset?: number;
    } = {},
  ) => request<Hand[]>(`/api/hands${qs(params)}`),
  setFavorite: (site: string, handId: string, favorite: boolean) =>
    request(`/api/hands/${site}/${handId}/favorite`, {
      method: "PUT",
      body: JSON.stringify({ favorite }),
    }),
  setNote: (site: string, handId: string, text: string) =>
    request(`/api/hands/${site}/${handId}/note`, {
      method: "PUT",
      body: JSON.stringify({ text }),
    }),
  setTags: (site: string, handId: string, tags: string[]) =>
    request(`/api/hands/${site}/${handId}/tags`, {
      method: "PUT",
      body: JSON.stringify({ tags }),
    }),
};

export type Tag = { name: string; count: number; color: string };

export const tagsApi = {
  list: () => request<Tag[]>("/api/tags"),
};

export type Favorite = {
  site: string;
  hand_id: string;
  type: string;
  title: string;
  meta: string;
  tags: string[];
};

export const favoritesApi = {
  list: () => request<Favorite[]>("/api/favorites"),
};

// ---------------- Estatísticas (Dashboard / Sessões / Estatísticas) ----------------
// Fininho sobre poker_coach/stats.py — o MESMO módulo usado pelas páginas
// Streamlit em app_pages/*.py. Lucro/ROI/ITM/ABI só existem pra torneios
// com resultado registrado (posição final + prêmio); o resto (saldo em
// BB, VPIP/PFR, horas jogadas) vem 100% da hand history.

export type RoiStats = {
  tournaments: number;
  invested: number;
  won: number;
  profit: number;
  roi_pct: number;
  itm_pct: number;
  abi: number;
};

export type OverviewStats = {
  hands: number;
  tournaments: number;
  vpip_pct: number;
  pfr_pct: number;
  net_bb: number;
  hours_played: number;
  roi: RoiStats | null; // null = nenhum torneio com resultado registrado ainda
};

export type PeriodProfit = { period: string; profit: number; tournaments: number };
export type DayNetBb = { date: string; net_bb: number; hands: number };
export type HourNetBb = { hour: number; net_bb: number; hands: number };
export type WeekdayNetBb = { weekday: string; net_bb: number; hands: number };
export type BuyinProfit = {
  buyin: number;
  tournaments: number;
  profit: number;
  roi_pct: number | null;
  itm_pct: number | null;
};
export type PositionStat = {
  position: string;
  spots: number;
  vpip_pct: number;
  pfr_pct: number;
  net_bb: number;
};
export type StackBucketStat = {
  bucket: string;
  spots: number;
  fold_pct: number | null;
  push_pct: number | null;
  call_pct: number | null;
  net_bb: number;
};
export type CashTicketSummary = {
  cash: { count: number; total: number };
  ticket: { count: number; total: number };
};
export type SatelliteRow = {
  torneio: string;
  site: string;
  buyin: number | null;
  converteu: "sim" | "não";
  valor_estimado: number | null;
  nota: string;
  data: string | null;
};
export type SatellitesSummary = {
  attempts: number;
  converted: number;
  pct: number | null;
  rows: SatelliteRow[];
};
export type SessionRow = {
  date: string;
  site: string;
  tournaments: number;
  hands: number;
  duration_min: number;
  profit: number | null;
  roi_pct: number | null;
  abi: number | null;
  with_result: number;
};

// Evolução de bankroll: BB (sempre disponível) | money/buyins (só
// torneios com resultado registrado — ver poker_coach/bankroll.py).
// cash = fluxo de caixa real da conta (todos os torneios, re-buys, tickets
// fora); money = resultado dos torneios com resultado registrado.
export type BankrollUnit = "bb" | "money" | "buyins" | "cash";
export type BankrollPoint = { period: string; value: number; cumulative: number; n: number };
export type Downswing = {
  unit: string;
  value: number;
  start: string | null;
  trough: string | null;
  recovery: string | null;
} | null;
export type SessionAverage = {
  unit: string;
  avg: number | null;
  n_sessions: number;
  n_excluded: number;
};
export type NormalizedResult = {
  basis: string;
  unit: string;
  value: number | null;
  n: number;
  min_required: number;
  insufficient: boolean;
  reason?: string | null;
};
export type CurrencyCount = { currency: string; tournaments: number };
export type CashSummary = {
  cash_profit: number;
  cash_in: number;
  cash_out: number;
  buyins_cash: number;
  rebuys: number;
  rebuys_cost: number;
  tournaments: number;
  pending_results: number;
  pending_buyins: number;
  ticket_entries: number;
  ticket_entries_value: number;
  ticket_entries_linked: number;
  tickets_won: number;
  tickets_won_value: number;
  tickets_unlinked: number;
  tickets_unlinked_value: number;
};

export const statsApi = {
  overview: () => request<OverviewStats>("/api/stats/overview"),
  profitByPeriod: (period: "day" | "week" | "month" = "day") =>
    request<PeriodProfit[]>(`/api/stats/profit-by-period${qs({ period })}`),
  netBbByDay: () => request<DayNetBb[]>("/api/stats/net-bb-by-day"),
  netBbByHour: () => request<HourNetBb[]>("/api/stats/net-bb-by-hour"),
  netBbByWeekday: () => request<WeekdayNetBb[]>("/api/stats/net-bb-by-weekday"),
  profitByBuyin: () => request<BuyinProfit[]>("/api/stats/profit-by-buyin"),
  position: () => request<PositionStat[]>("/api/stats/position"),
  stackBuckets: () => request<StackBucketStat[]>("/api/stats/stack-buckets"),
  cashVsTicket: () => request<CashTicketSummary>("/api/stats/cash-vs-ticket"),
  satellites: () => request<SatellitesSummary>("/api/stats/satellites"),
  sessions: () => request<SessionRow[]>("/api/stats/sessions"),
  currencies: () => request<CurrencyCount[]>("/api/stats/currencies"),
  cashSummary: () => request<CashSummary>("/api/stats/cash-summary"),
  bankrollSeries: (params: { unit: BankrollUnit; currency?: string | undefined }) =>
    request<BankrollPoint[]>(`/api/stats/bankroll-series${qs(params)}`),
  downswing: (params: { unit: BankrollUnit; currency?: string | undefined }) =>
    request<Downswing>(`/api/stats/downswing${qs(params)}`),
  sessionAverage: (params: { unit: BankrollUnit; currency?: string | undefined }) =>
    request<SessionAverage>(`/api/stats/session-average${qs(params)}`),
  normalized: (params: {
    basis: "per_100_tournaments" | "per_1000_hands";
    unit: BankrollUnit;
  }) => request<NormalizedResult>(`/api/stats/normalized${qs(params)}`),
};

// ---------------- Estilo de Jogo ----------------
// poker_coach/api/routers/play_style.py — toda métrica vem com o
// denominador (`opps` / `<m>_n`); `pct` null = nenhuma oportunidade.

export type PlayStyleMetricKey =
  "vpip" | "pfr" | "threebet" | "f3b" | "ats" | "fts" | "cbet" | "fcb";

export type PlayStyleMetricDef = { key: PlayStyleMetricKey; label: string; description: string };

export type PlayStyleTournament = {
  site: string;
  tournament_id: string;
  name: string | null;
  buyin: number | null;
  first_ts: string | null;
  hands: number;
};

export type PlayStyleOptions = {
  buyins: number[];
  tournaments: PlayStyleTournament[];
  positions: string[];
  stack_ranges: string[];
  date_min: string | null;
  date_max: string | null;
  metrics: PlayStyleMetricDef[];
};

export type PlayStyleMetricValue = { pct: number | null; made: number; opps: number };

export type PlayStyleSummary = {
  hands: number;
  tournaments: number;
  date_min: string | null;
  date_max: string | null;
  gap: number | null;
} & Record<PlayStyleMetricKey, PlayStyleMetricValue>;

export type PlayStyleRow = {
  position: string | null;
  stack_range: string | null;
  period: string | null;
  hands: number;
  gap: number | null;
} & Record<PlayStyleMetricKey, number | null> &
  Record<`${PlayStyleMetricKey}_n`, number>;

export type PlayStyleReport = {
  summary: PlayStyleSummary;
  by_stack: PlayStyleRow[];
  by_position: PlayStyleRow[];
  evolution: PlayStyleRow[];
  table: PlayStyleRow[];
};

export type PlayStylePeriod = "all" | "today" | "7d" | "30d" | "custom";
export type PlayStyleFreq = "D" | "W" | "M";

export type PlayStyleFilters = {
  period: PlayStylePeriod;
  date_from?: string | undefined;
  date_to?: string | undefined;
  site?: string | undefined;
  tournament_id?: string | undefined;
  buyin?: number | undefined;
  stack?: string | undefined;
  position?: string | undefined;
  freq: PlayStyleFreq;
};

export const playStyleApi = {
  options: () => request<PlayStyleOptions>("/api/play-style/options"),
  report: (params: PlayStyleFilters) =>
    request<PlayStyleReport>(`/api/play-style/report${qs(params)}`),
};

// ---------------- Importação ----------------

export type ImportFileResult = {
  filename: string;
  site: string | null;
  hands_in_file: number;
  hands_new: number;
  error: string | null;
};

export type ImportResult = { files: ImportFileResult[]; total_new: number };

export const importApi = {
  upload: async (files: File[]): Promise<ImportResult> => {
    const form = new FormData();
    for (const f of files) form.append("files", f);
    const res = await fetch(`${BASE_URL}/api/import`, { method: "POST", body: form });
    if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
    return res.json() as Promise<ImportResult>;
  },
};
