import type { ActionAttempt } from './types'
// Retain request IDs when switching console pages, but never persist credentials or IDs to disk.
const attempts = new Map<string, ActionAttempt>()
export function getAttempt(shop: string): ActionAttempt | undefined { return attempts.get(shop) }
export function saveAttempt(shop: string, attempt: ActionAttempt) { attempts.set(shop, attempt) }
export function clearAttempt(shop: string) { attempts.delete(shop) }
export function clearActionLedger() { attempts.clear() }
