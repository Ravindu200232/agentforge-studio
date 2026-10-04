'use client'

import { Check, Loader2 } from 'lucide-react'
import { Button } from './ui'

/**
 * The accounts signed in here for one provider (Supabase, MongoDB Atlas), with the one new projects are
 * made in marked. `busy` is "switch:<id>" or "remove:<id>" while one of them is being done.
 */
export default function AccountList({ accounts, busy = '', onSwitch, onRemove }) {
  if (!accounts?.length) return null
  return (
    <ul className="space-y-1.5">
      {accounts.map(account => (
        <li key={account.id} className="flex flex-wrap items-center gap-2 rounded-xl bg-bg/60 px-3 py-2">
          <span className="min-w-0 flex-1 truncate text-[11px] text-ink">
            {account.active && <Check className="mr-1 inline size-3 text-ok" />}{account.label}
          </span>
          {account.active
            ? <span className="text-[10px] font-bold uppercase tracking-wider text-muted2">in use</span>
            : (
              <Button size="sm" variant="soft" disabled={Boolean(busy)} onClick={() => onSwitch(account.id)}>
                {busy === `switch:${account.id}` && <Loader2 className="size-3 animate-spin" />} Use this account
              </Button>
            )}
          <Button size="sm" variant="ghost" disabled={Boolean(busy)} onClick={() => onRemove(account.id)}>
            {busy === `remove:${account.id}` && <Loader2 className="size-3 animate-spin" />} Sign out
          </Button>
        </li>
      ))}
    </ul>
  )
}
