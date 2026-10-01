'use client'

/** Attach and record, for the editing chats. */
import { useRef, useState } from 'react'
import { FileText, Image as ImageIcon, Loader2, Mic, Paperclip, Square, X } from 'lucide-react'

import { ACCEPT_UPLOAD, api } from '@/lib/api'
import { useRecorder } from '@/lib/use-attachments'
import { Button } from './ui'
import { cn } from '@/lib/utils'

const PICTURE = /\.(png|jpe?g|webp|gif|bmp)$/i
const SOUND = /\.(wav|mp3|m4a|ogg|webm|flac)$/i

export default function EditAttach({ attach, disabled, className, project, onSpoken }) {
  const picker = useRef(null)
  const [hearing, setHearing] = useState(false)
  const [heard, setHeard] = useState('')

  /** Transcribes recorded voice audio directly into the chat input box. */
  const recorder = useRecorder(async file => {
    if (!onSpoken) return attach.add([file])
    setHearing(true); setHeard('')
    try {
      const got = await api.attach(file, { project })
      const said = (got?.text || '').trim()
      if (said) onSpoken(said)
      else setHeard(got?.note || 'Nothing could be made out in that recording.')
    } catch (e) {
      setHeard(e.message || 'That recording could not be read.')
    } finally {
      setHearing(false)
    }
  })

  return (
    <div className={cn('flex min-w-0 shrink-0 items-center gap-1.5', className)}>
      <input ref={picker} type="file" multiple hidden accept={ACCEPT_UPLOAD}
             onChange={e => { attach.add(e.target.files); e.target.value = '' }} />

      <Button variant="ghost" size="sm" disabled={disabled}
              onClick={() => picker.current?.click()}
              title="Save a picture or file in this project's media folder">
        <Paperclip className="size-3" />
      </Button>

      <Button variant={recorder.recording ? 'solid' : 'ghost'} size="sm"
              disabled={disabled || hearing} onClick={recorder.toggle}
              title={recorder.recording ? 'Stop recording' : 'Say it instead of typing it'}>
        {recorder.recording
          ? <><Square className="size-2.5 fill-current" /> {recorder.seconds}s</>
          : hearing ? <Loader2 className="size-3 animate-spin" />
            : <Mic className="size-3" />}
      </Button>

      {(recorder.error || heard) && (
        <span className="text-[10px] text-deep">{recorder.error || heard}</span>
      )}

      {attach.items.length > 0 && (
        <span className="flex min-w-0 items-center gap-1 overflow-x-auto no-scrollbar">
          {attach.items.map(it => {
            const Icon = PICTURE.test(it.name) ? ImageIcon : SOUND.test(it.name) ? Mic : FileText
            const failed = it.state === 'failed'
            return (
              <span key={it.key}
                    title={it.note || it.read?.slice(0, 300) || it.name}
                    aria-label={`Attached ${it.name}`}
                    className={cn('group relative grid size-6 shrink-0 place-items-center',
                                  'border text-[10.5px]',
                                  failed ? 'border-accent bg-tint text-deep'
                                         : 'border-line2 bg-panel2 text-muted')}>
                {it.state === 'reading'
                  ? <Loader2 className="size-2.5 animate-spin text-accent" />
                  : <Icon className="size-3" />}
                <button onClick={() => attach.remove(it.key)}
                        aria-label={`Remove ${it.name} from this message`}
                        title="Remove from this message; the saved file stays in media"
                        disabled={it.state === 'reading'}
                        className="absolute -right-1 -top-1 hidden size-3.5 place-items-center rounded-full border border-line bg-panel text-muted2 hover:text-ink group-hover:grid focus:grid disabled:opacity-30">
                  <X className="size-2" />
                </button>
              </span>
            )
          })}
        </span>
      )}
    </div>
  )
}
