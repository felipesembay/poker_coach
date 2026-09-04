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
};

export type TrainerStats = { total: number; correct: number; pct: number | null };

export const trainerApi = {
  next: (
    params: { mode?: TrainerMode; bb_min?: number; bb_max?: number; n_players?: number } = {},
  ) => request<TrainerQuestion>(`/api/pushfold/trainer/next${qs(params)}`),
  answer: (site: string, hand_id: string, mode: TrainerMode, decision: TrainerDecision) =>
    request<TrainerAnswer>("/api/pushfold/trainer/answer", {
      method: "POST",
      body: JSON.stringify({ site, hand_id, mode, decision }),
    }),
  stats: () => request<TrainerStats>("/api/pushfold/trainer/stats"),
};

// ---------------- ICM ----------------

export type IcmTournament = {
  site: string;
  tournament_id: string;
  name: string | null;
  buyin: number | null;
  has_payouts: boolean;
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
  hero_decision?: string | null;
  nash_decision?: string | null;
  ev_push_bb?: number | null;
  ev_lost_bb?: number | null;
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
