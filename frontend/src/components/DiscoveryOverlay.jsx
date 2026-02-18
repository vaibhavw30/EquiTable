import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Loader2, X, AlertTriangle, CheckCircle, Search } from 'lucide-react'
import { clsx } from 'clsx'
import useReducedMotion from '../hooks/useReducedMotion'

/**
 * Radar ripple animation — 3 concentric rings that pulse outward.
 * Shown on the map while discovery is in progress.
 * Falls back to a simple "Searching..." text when reduced motion is on.
 */
function RadarPulse({ reducedMotion }) {
  if (reducedMotion) {
    return (
      <div className="flex items-center gap-2" data-testid="radar-reduced">
        <div className="w-3 h-3 rounded-full bg-emerald-500" />
        <span className="text-xs text-emerald-700 font-medium">Searching...</span>
      </div>
    )
  }

  return (
    <div className="relative w-16 h-16" data-testid="radar-pulse">
      {/* Center dot */}
      <div className="absolute inset-0 m-auto w-3 h-3 rounded-full bg-emerald-500 z-10" />
      {/* Ripple rings */}
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          className="absolute inset-0 rounded-full border-2 border-emerald-400 opacity-0 animate-[radar-ping_2s_ease-out_infinite]"
          style={{ animationDelay: `${i * 0.6}s` }}
        />
      ))}
    </div>
  )
}

// Status variants for the toast
const STATUS = {
  DISCOVERING: 'discovering',
  COMPLETE: 'complete',
  PARTIAL: 'partial',
  EMPTY: 'empty',
  ERROR: 'error',
}

function getStatus({ isDiscovering, discoveryDone, progress, error }) {
  if (isDiscovering) return STATUS.DISCOVERING
  if (!discoveryDone) return null
  if (error) return STATUS.ERROR
  if (progress.succeeded === 0 && progress.failed === 0) return STATUS.EMPTY
  if (progress.succeeded === 0 && progress.failed > 0) return STATUS.PARTIAL
  return STATUS.COMPLETE
}

/**
 * Discovery map overlay — floats on the map area during/after discovery.
 *
 * Props:
 * - isDiscovering: boolean
 * - discoveryDone: boolean (true after discovery finishes, until dismissed)
 * - progress: { found, total, failed, succeeded }
 * - error: string | null
 * - query: string (location name)
 * - onCancel: callback to cancel discovery
 * - onDismiss: callback to dismiss the result toast
 * - onRetry: callback to retry (for partial failures)
 */
export default function DiscoveryOverlay({
  isDiscovering,
  discoveryDone,
  progress,
  error,
  query,
  onCancel,
  onDismiss,
  onRetry,
}) {
  const reducedMotion = useReducedMotion()
  const status = getStatus({ isDiscovering, discoveryDone, progress, error })

  // Auto-dismiss success toast after 5 seconds
  const [autoDismissed, setAutoDismissed] = useState(false)
  useEffect(() => {
    if (status === STATUS.COMPLETE) {
      setAutoDismissed(false)
      const timer = setTimeout(() => {
        setAutoDismissed(true)
        onDismiss?.()
      }, 5000)
      return () => clearTimeout(timer)
    }
    setAutoDismissed(false)
  }, [status]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!status || autoDismissed) return null

  return (
    <>
      {/* ── Desktop: floating card on top of map ── */}
      <AnimatePresence>
        {status === STATUS.DISCOVERING && (
          <motion.div
            initial={reducedMotion ? { opacity: 1 } : { opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reducedMotion ? { opacity: 0 } : { opacity: 0, y: -20 }}
            transition={{ duration: 0.3 }}
            className="hidden sm:flex absolute top-4 left-1/2 -translate-x-1/2 z-30 items-center gap-4 px-5 py-3 bg-white/95 backdrop-blur-sm rounded-2xl shadow-xl border border-emerald-100"
            data-testid="discovery-loader"
            role="status"
            aria-live="polite"
          >
            <RadarPulse reducedMotion={reducedMotion} />
            <div className="text-sm">
              <p className="font-medium text-zinc-900" data-testid="discovery-location">
                Discovering pantries{query ? ` in ${query}` : ''}...
              </p>
              {progress.succeeded > 0 && (
                <p className="text-emerald-600 text-xs mt-0.5" data-testid="discovery-count">
                  Found {progress.succeeded} so far...
                </p>
              )}
              {progress.total > 0 && (
                <div className="mt-1.5 h-1 w-40 bg-emerald-100 rounded-full overflow-hidden">
                  <motion.div
                    className="h-full bg-emerald-500 rounded-full"
                    initial={{ width: 0 }}
                    animate={{
                      width: `${Math.round(((progress.succeeded + progress.failed) / progress.total) * 100)}%`,
                    }}
                    transition={{ duration: 0.4, ease: 'easeOut' }}
                  />
                </div>
              )}
            </div>
            <button
              onClick={onCancel}
              className="p-1.5 hover:bg-zinc-100 rounded-lg transition-colors"
              aria-label="Cancel discovery"
              data-testid="discovery-cancel"
            >
              <X className="w-4 h-4 text-zinc-400" />
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Mobile: bottom bar for in-progress ── */}
      <AnimatePresence>
        {status === STATUS.DISCOVERING && (
          <motion.div
            initial={reducedMotion ? { opacity: 1 } : { opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reducedMotion ? { opacity: 0 } : { opacity: 0, y: 20 }}
            transition={{ duration: 0.25 }}
            className="sm:hidden fixed bottom-0 inset-x-0 z-40 px-4 py-3 bg-white/95 backdrop-blur-sm border-t border-emerald-100 shadow-[0_-2px_10px_rgba(0,0,0,0.08)]"
            data-testid="discovery-mobile-bar"
            role="status"
            aria-live="polite"
          >
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 min-w-0">
                {reducedMotion ? (
                  <div className="w-2 h-2 rounded-full bg-emerald-500 flex-shrink-0" />
                ) : (
                  <Loader2 className="w-4 h-4 text-emerald-600 animate-spin flex-shrink-0" />
                )}
                <span className="text-sm text-zinc-800 truncate">
                  Discovering{query ? ` in ${query}` : ''}...
                  {progress.succeeded > 0 && (
                    <span className="text-emerald-600"> ({progress.succeeded} found)</span>
                  )}
                </span>
              </div>
              <button
                onClick={onCancel}
                className="text-xs text-zinc-500 hover:text-zinc-700 flex-shrink-0"
                aria-label="Cancel discovery"
              >
                Cancel
              </button>
            </div>
            {progress.total > 0 && (
              <div className="mt-2 h-1 bg-emerald-100 rounded-full overflow-hidden">
                <div
                  className="h-full bg-emerald-500 rounded-full transition-all duration-300"
                  style={{
                    width: `${Math.round(((progress.succeeded + progress.failed) / progress.total) * 100)}%`,
                  }}
                />
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Toast for completion / error / empty states ── */}
      <AnimatePresence>
        {status && status !== STATUS.DISCOVERING && (
          <motion.div
            initial={reducedMotion ? { opacity: 1 } : { opacity: 0, y: -20, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={reducedMotion ? { opacity: 0 } : { opacity: 0, y: -20, scale: 0.95 }}
            transition={{ duration: 0.3, type: 'spring', damping: 25 }}
            className={clsx(
              'absolute top-4 left-1/2 -translate-x-1/2 z-30 flex items-center gap-3 px-5 py-3 rounded-2xl shadow-xl border backdrop-blur-sm',
              // Mobile: fixed bottom bar instead
              'max-sm:fixed max-sm:bottom-0 max-sm:top-auto max-sm:left-0 max-sm:translate-x-0 max-sm:w-full max-sm:rounded-none max-sm:border-x-0 max-sm:border-b-0',
              status === STATUS.COMPLETE && 'bg-emerald-50/95 border-emerald-200',
              status === STATUS.PARTIAL && 'bg-amber-50/95 border-amber-200',
              status === STATUS.EMPTY && 'bg-zinc-50/95 border-zinc-200',
              status === STATUS.ERROR && 'bg-red-50/95 border-red-200',
            )}
            data-testid="discovery-toast"
            role="alert"
          >
            {/* Icon */}
            {status === STATUS.COMPLETE && (
              <CheckCircle className="w-5 h-5 text-emerald-600 flex-shrink-0" />
            )}
            {status === STATUS.PARTIAL && (
              <AlertTriangle className="w-5 h-5 text-amber-600 flex-shrink-0" />
            )}
            {status === STATUS.EMPTY && (
              <Search className="w-5 h-5 text-zinc-500 flex-shrink-0" />
            )}
            {status === STATUS.ERROR && (
              <AlertTriangle className="w-5 h-5 text-red-600 flex-shrink-0" />
            )}

            {/* Message */}
            <div className="text-sm min-w-0">
              {status === STATUS.COMPLETE && (
                <p className="text-emerald-800" data-testid="toast-message">
                  Found {progress.succeeded} pantries{query ? ` near ${query}` : ''}
                </p>
              )}
              {status === STATUS.PARTIAL && (
                <>
                  <p className="text-amber-800" data-testid="toast-message">
                    Some pantries couldn't be loaded
                  </p>
                  {progress.succeeded > 0 && (
                    <p className="text-amber-600 text-xs mt-0.5">
                      {progress.succeeded} loaded, {progress.failed} failed
                    </p>
                  )}
                </>
              )}
              {status === STATUS.EMPTY && (
                <p className="text-zinc-700" data-testid="toast-message">
                  No pantries found{query ? ` in ${query}` : ' in this area'}
                </p>
              )}
              {status === STATUS.ERROR && (
                <p className="text-red-700" data-testid="toast-message">
                  {error || 'Discovery failed'}
                </p>
              )}
            </div>

            {/* Actions */}
            <div className="flex items-center gap-2 flex-shrink-0">
              {(status === STATUS.PARTIAL || status === STATUS.ERROR) && onRetry && (
                <button
                  onClick={onRetry}
                  className="text-xs font-medium text-emerald-600 hover:text-emerald-700 hover:underline"
                  data-testid="toast-retry"
                >
                  Retry
                </button>
              )}
              <button
                onClick={onDismiss}
                className="p-1 hover:bg-black/5 rounded-lg transition-colors"
                aria-label="Dismiss"
                data-testid="toast-dismiss"
              >
                <X className="w-3.5 h-3.5 text-zinc-400" />
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}
