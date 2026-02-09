import { clsx } from 'clsx'

/**
 * StatsCard - A glassmorphic stat display card
 *
 * Props:
 * - label: The stat label (e.g., "Active Pantries")
 * - value: The stat value (e.g., "15")
 * - icon: A Lucide icon component
 * - trend: Optional trend indicator ("up" | "down" | null)
 */
export default function StatsCard({ label, value, icon: Icon, trend, className }) {
  return (
    <div
      className={clsx(
        // Glassmorphism base
        'relative overflow-hidden rounded-2xl',
        'bg-zinc-900/60 backdrop-blur-xl',
        'border border-zinc-800/50',
        // Hover glow effect
        'hover:border-emerald-500/30 hover:shadow-[0_0_30px_rgba(52,211,153,0.1)]',
        'transition-all duration-300',
        'p-5',
        className
      )}
    >
      {/* Subtle gradient overlay */}
      <div className="absolute inset-0 bg-gradient-to-br from-emerald-500/5 to-transparent pointer-events-none" />

      <div className="relative flex items-start justify-between">
        <div className="space-y-2">
          <p className="text-xs font-medium uppercase tracking-wider text-zinc-500">
            {label}
          </p>
          <p className="text-3xl font-bold tracking-tight text-white">
            {value}
          </p>
          {trend && (
            <p
              className={clsx(
                'text-xs font-medium',
                trend === 'up' ? 'text-emerald-400' : 'text-red-400'
              )}
            >
              {trend === 'up' ? '↑' : '↓'} Updated live
            </p>
          )}
        </div>

        {Icon && (
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-400">
            <Icon className="h-5 w-5" />
          </div>
        )}
      </div>
    </div>
  )
}
