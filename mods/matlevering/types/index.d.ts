export type CartLine = {
  ean: string
  title: string
  quantity: number
  lineTotal: number
  isUnavailable: boolean
  isOffer: boolean
  /** What the offer saves on this line, in kr (0 without an offer). */
  saved: number
}

export type CartView = {
  lines: CartLine[]
  total: number
  unavailableCount: number
  saved: number
}

export type Dinner = { day: string; dish: string }

export type DinnerPlan = { file: string; dinners: Dinner[] }

declare module 'claude-code' {
  interface PluginState {
    matlevering: {
      cart: CartView | null
      cartError: string | null
      store: string | null
      plan: DinnerPlan | null
      isLoading: boolean
      updatedAt: number
    }
  }
}
