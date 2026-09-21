import { createContext, useContext, type ReactNode } from 'react'

import { api as defaultApi } from './index'
import type { Api } from './types'

const ApiContext = createContext<Api>(defaultApi)

/** Wrap the app (or a test) to choose which `Api` implementation pages talk to. */
export function ApiProvider({ api, children }: { api?: Api; children: ReactNode }) {
  return <ApiContext.Provider value={api ?? defaultApi}>{children}</ApiContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useApi(): Api {
  return useContext(ApiContext)
}
