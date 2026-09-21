import dayjs from 'dayjs'

import type { IsoDate } from '../api/types'

/** Today as an ISO date. One helper so "today" is easy to find (and fake in tests). */
export function todayIso(): IsoDate {
  return dayjs().format('YYYY-MM-DD')
}
