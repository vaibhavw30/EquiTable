import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Terminal, Zap, CheckCircle, AlertTriangle, RefreshCw } from 'lucide-react'
import { clsx } from 'clsx'

/**
 * LiveFeed - A terminal-style scrolling log of system events
 *
 * Props:
 * - events: Array of { id, type, message, timestamp }
 * - maxItems: Maximum items to display (default 8)
 */

const EVENT_ICONS = {
  system: Terminal,
  success: CheckCircle,
  warning: AlertTriangle,
  update: RefreshCw,
  action: Zap,
}

const EVENT_COLORS = {
  system: 'text-zinc-400',
  success: 'text-emerald-400',
  warning: 'text-amber-400',
  update: 'text-blue-400',
  action: 'text-purple-400',
}

// Generate mock events for demo
function generateMockEvents() {
  const mockMessages = [
    { type: 'system', message: 'System initialized. Autonomous agents online.' },
    { type: 'update', message: 'Scraping Midtown Assistance Center...' },
    { type: 'success', message: 'Midtown Assistance Center: OPEN (Tues-Thurs)' },
    { type: 'update', message: 'Scanning Venable Food Market...' },
    { type: 'success', message: 'Venable Food Market: OPEN (ID Required)' },
    { type: 'warning', message: 'Grace House: Low confidence (2/10)' },
    { type: 'update', message: 'Auditing St. Francis Table...' },
    { type: 'action', message: 'Geospatial index optimized' },
    { type: 'success', message: 'Atlanta Mission updated: hours_today=Closed' },
    { type: 'system', message: 'Data sync complete. 15 pantries active.' },
    { type: 'update', message: 'Monitoring Wheat Street Baptist...' },
    { type: 'warning', message: 'Ebenezer Baptist: No hours data found' },
    { type: 'success', message: 'Klemis Kitchen: 24/7 access confirmed' },
    { type: 'action', message: 'Near-me query served: 5 results' },
  ]

  return mockMessages.map((msg, i) => ({
    id: `mock-${i}`,
    ...msg,
    timestamp: new Date(Date.now() - (mockMessages.length - i) * 60000),
  }))
}

export default function LiveFeed({ events: externalEvents, maxItems = 8, className }) {
  const [events, setEvents] = useState(generateMockEvents)
  const [isLive, setIsLive] = useState(true)

  // Simulate live updates
  useEffect(() => {
    if (!isLive) return

    const messages = [
      { type: 'update', message: 'Scanning food infrastructure...' },
      { type: 'success', message: 'Data integrity verified.' },
      { type: 'action', message: 'User query processed.' },
      { type: 'system', message: 'Autonomous audit cycle complete.' },
    ]

    const interval = setInterval(() => {
      const randomMsg = messages[Math.floor(Math.random() * messages.length)]
      const newEvent = {
        id: `live-${Date.now()}`,
        ...randomMsg,
        timestamp: new Date(),
      }

      setEvents((prev) => [newEvent, ...prev].slice(0, 50))
    }, 5000)

    return () => clearInterval(interval)
  }, [isLive])

  const displayEvents = (externalEvents || events).slice(0, maxItems)

  return (
    <div
      className={clsx(
        'relative overflow-hidden rounded-2xl',
        'bg-zinc-900/80 backdrop-blur-xl',
        'border border-zinc-800/50',
        className
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-zinc-800/50 px-4 py-3">
        <div className="flex items-center gap-2">
          <Terminal className="h-4 w-4 text-emerald-400" />
          <span className="text-xs font-semibold uppercase tracking-wider text-zinc-400">
            Live Feed
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={clsx(
              'h-2 w-2 rounded-full',
              isLive ? 'bg-emerald-400 animate-pulse' : 'bg-zinc-600'
            )}
          />
          <button
            onClick={() => setIsLive(!isLive)}
            className={clsx(
              'text-xs font-medium',
              isLive ? 'text-emerald-400' : 'text-zinc-500'
            )}
          >
            {isLive ? 'LIVE' : 'PAUSED'}
          </button>
        </div>
      </div>

      {/* Terminal content */}
      <div className="h-48 overflow-hidden px-4 py-3 font-mono text-xs">
        <AnimatePresence mode="popLayout">
          {displayEvents.map((event, index) => {
            const Icon = EVENT_ICONS[event.type] || Terminal
            const colorClass = EVENT_COLORS[event.type] || 'text-zinc-400'

            return (
              <motion.div
                key={event.id}
                initial={{ opacity: 0, y: -10, height: 0 }}
                animate={{ opacity: 1, y: 0, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ duration: 0.2 }}
                className="flex items-start gap-2 py-1"
              >
                <span className="text-zinc-600 select-none">
                  {event.timestamp.toLocaleTimeString('en-US', {
                    hour: '2-digit',
                    minute: '2-digit',
                    hour12: false,
                  })}
                </span>
                <Icon className={clsx('h-3 w-3 mt-0.5 flex-shrink-0', colorClass)} />
                <span className={clsx('leading-tight', colorClass)}>
                  {event.message}
                </span>
              </motion.div>
            )
          })}
        </AnimatePresence>

        {/* Scanline effect */}
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-transparent via-emerald-500/[0.02] to-transparent animate-scan" />
      </div>
    </div>
  )
}
