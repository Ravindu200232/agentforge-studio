'use client'

import { Loader2, MessageCircleQuestion, ScrollText } from 'lucide-react'
import { STATE_TEXT } from '@/lib/deploy-constants'
import { cn } from '@/lib/utils'
import ChangePlan from '../ChangePlan'

const WHAT = {
  PLANNING: 'The agent is reading your project, the deployment guides for this target and the tools on this computer. '
    + 'Nothing is deployed and nothing leaves this machine while it plans.',
  NEEDS_INPUT: 'The agent has a question for you. It is in the chat beside this panel: answer it there, or let the agent decide.',
  AWAITING_APPROVAL: 'The deployment plan is ready. Read it, ask for changes in the chat if you want any, then approve it. '
    + 'Nothing is deployed until you do.',
}

/** The stretch before a deployment is carried out: planning, asking, and the plan waiting for approval. */
export default function DeployPlanStage({ live, plan, card }) {
  const [label] = STATE_TEXT[live.state] || [live.state]
  const asking = live.state === 'NEEDS_INPUT'
  const Icon = asking ? MessageCircleQuestion : live.state === 'PLANNING' ? Loader2 : ScrollText
  return (
    <div className="space-y-3">
      <div className="rounded-2xl border border-accent/25 bg-accent p-4">
        <p className="flex items-center gap-2.5 text-[13px] font-semibold text-ink">
          <Icon className={cn('size-4 text-ink', live.state === 'PLANNING' && 'animate-spin')} />
          {label}
        </p>
        <p className="mt-1.5 text-[11.5px] leading-relaxed text-muted">{WHAT[live.state]}</p>
      </div>
      {card && <ChangePlan turn={card} />}
      {!card && plan?.title && (
        <p className="rounded-xl border border-line/70 px-3.5 py-2.5 text-[12px] text-muted">{plan.title}</p>
      )}
    </div>
  )
}
